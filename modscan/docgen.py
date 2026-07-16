# Copyright 2026 Rinkia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Layer 4: doc generator — turn validated seams into modding docs.

Pipeline: parse -> graph -> detect -> validate -> keep only confirmed points ->
build fact blocks -> ask the LLM (per section) for prose and an example plugin ->
re-validate each generated example (retry 3-5x) -> write modding-docs/ (Markdown
for humans + extension-points.json for tooling).

Facts come from the parser; prose comes from the LLM; correctness comes from the
validator. The model only ever sees fact blocks, never raw source.

SECURITY / TRUST BOUNDARY
-------------------------
Example validation EXECUTES generated code (and imports the target) to confirm a
concrete plugin really loads. Same trust boundary as the validator: run only on
code you trust. Disable with `validate_examples=False` to skip execution.
ponytail: in-process exec, no sandbox — matches validator.py. Subprocess/sandbox
is the upgrade path for untrusted targets; out of scope for the MVP.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Iterator

from modscan.detector import detect_extension_points
from modscan.factblocks import FactBlock, build_fact_block, render_fact_block
from modscan.graph import build_graph
from modscan.manifest import build_manifest, write_manifest
from modscan.parser import parse_codebase
from modscan.prompts import SYSTEM, architecture_prompt, example_prompt, guide_prompt
from modscan.providers.base import Provider
from modscan.validator import validate_points

# Example-validation retry bounds (locked in the Task 4 plan).
_MIN_RETRIES = 3
_MAX_RETRIES = 5
_DEFAULT_RETRIES = 4

# Example statuses, strongest first. "verified" = subclass executed &
# instantiated; "executed" = non-subclass example imported/ran clean; "compiled"
# = syntactically valid only (used when validation is disabled); "unverified" =
# none held after all retries.
_OK_STATUSES = ("verified", "executed", "compiled")


@dataclass
class GeneratedPoint:
    fact: FactBlock
    guide: str
    example_code: str
    example_status: str
    example_path: str


@dataclass
class DocReport:
    out_dir: str
    overview: str
    points: list[GeneratedPoint] = field(default_factory=list)
    manifest_path: str = ""

    @property
    def verified_count(self) -> int:
        return sum(1 for p in self.points if p.example_status == "verified")


@contextlib.contextmanager
def _sys_path(entry: str) -> Iterator[None]:
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(entry)


def _extract_code(raw: str) -> str:
    """Pull the body out of a ```python ...``` fence, else return as-is."""
    text = raw.strip()
    if "```" not in text:
        return text
    parts = text.split("```")
    # parts[1] is the first fenced block; drop a leading language tag line.
    block = parts[1] if len(parts) >= 2 else text
    lines = block.splitlines()
    if lines and lines[0].strip().lower() in ("python", "py"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _exec_and_instantiate(root: str, fb: FactBlock, code: str) -> bool:
    """Exec the example, find a concrete subclass of the seam, instantiate it."""
    try:
        with _sys_path(root):
            base = getattr(importlib.import_module(fb.module), fb.symbol)
            namespace: dict = {}
            exec(compile(code, "<modscan-example>", "exec"), namespace)  # noqa: S102
    except Exception:  # noqa: BLE001 — any failure means the example didn't load
        return False
    if not isinstance(base, type):
        return False
    try:
        for value in namespace.values():
            # issubclass can raise on some bases (e.g. a typing.Protocol with
            # data members), so guard the whole search.
            if isinstance(value, type) and value is not base and issubclass(value, base):
                value()
                return True
    except Exception:  # noqa: BLE001 — any failure means the example didn't load
        return False
    return False


def _exec_module(root: str, code: str) -> bool:
    """Exec the example so imports resolve and module-level code runs clean."""
    try:
        with _sys_path(root):
            exec(compile(code, "<modscan-example>", "exec"), {})  # noqa: S102
    except Exception:  # noqa: BLE001 — any failure means the example didn't load
        return False
    return True


def _verify_example(root: str, fb: FactBlock, code: str, validate: bool) -> str:
    """Return an example status: verified | executed | compiled | invalid."""
    try:
        compile(code, "<modscan-example>", "exec")
    except SyntaxError:
        return "invalid"
    if not validate:
        return "compiled"
    if fb.kind in ("class", "abstract_class"):
        return "verified" if _exec_and_instantiate(root, fb, code) else "invalid"
    # hook/registration/api: no subclass to instantiate, but we can still load
    # the example to catch bad imports and module-level errors.
    return "executed" if _exec_module(root, code) else "invalid"


def _make_example(
    provider: Provider, root: str, fb: FactBlock, retries: int, validate: bool
) -> tuple[str, str]:
    """Generate and validate an example plugin, retrying up to `retries` times."""
    code = ""
    for _ in range(retries):
        code = _extract_code(provider.generate(SYSTEM, example_prompt(fb)))
        status = _verify_example(root, fb, code, validate)
        if status in _OK_STATUSES:
            return code, status
    return code, "unverified"


def _dependency_summary(dependencies: dict[str, set[str]]) -> str:
    edges = sum(len(v) for v in dependencies.values())
    return f"{len(dependencies)} internal modules, {edges} dependency edges"


def _example_filename(point_id: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in point_id)
    return f"{safe}.py"


def generate_docs(
    root: str,
    provider: Provider,
    out_dir: str,
    *,
    min_score: float = 0.5,
    limit: int | None = None,
    max_example_retries: int = _DEFAULT_RETRIES,
    validate_examples: bool = True,
) -> DocReport:
    """Generate modding docs (Markdown + JSON) for the codebase at `root`."""
    retries = max(_MIN_RETRIES, min(_MAX_RETRIES, max_example_retries))

    codebase = parse_codebase(root)
    graph = build_graph(codebase)
    points = detect_extension_points(graph, min_score=min_score)

    # Keep only points the validator confirmed; carry its method into the facts.
    validations = validate_points(root, points, limit=limit)
    confirmed = [(p, v) for p, v in zip(points, validations) if v.ok]

    facts = [build_fact_block(codebase, p, v.method) for p, v in confirmed]

    overview = provider.generate(
        SYSTEM,
        architecture_prompt(
            [render_fact_block(f) for f in facts], _dependency_summary(graph.dependencies)
        ),
    )

    generated: list[GeneratedPoint] = []
    for fb in facts:
        guide = provider.generate(SYSTEM, guide_prompt(fb))
        code, status = _make_example(provider, root, fb, retries, validate_examples)
        generated.append(
            GeneratedPoint(
                fact=fb,
                guide=guide,
                example_code=code,
                example_status=status,
                example_path=f"examples/{_example_filename(fb.point_id)}",
            )
        )

    manifest_path = _write_outputs(out_dir, root, overview, generated)
    return DocReport(
        out_dir=out_dir, overview=overview, points=generated, manifest_path=manifest_path
    )


def _write_outputs(
    out_dir: str, root: str, overview: str, generated: list[GeneratedPoint]
) -> str:
    os.makedirs(os.path.join(out_dir, "examples"), exist_ok=True)

    _write(os.path.join(out_dir, "index.md"), _render_index(overview, generated))
    _write(os.path.join(out_dir, "plugin-guide.md"), _render_guide(generated))
    for gp in generated:
        _write(os.path.join(out_dir, gp.example_path), gp.example_code + "\n")

    manifest_path = os.path.join(out_dir, "extension-points.json")
    write_manifest(manifest_path, build_manifest(root, generated))
    return manifest_path


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _render_index(overview: str, generated: list[GeneratedPoint]) -> str:
    lines = [
        "# Modding Guide",
        "",
        "> Generated by MODScan. Facts from static analysis; prose from an LLM; "
        "examples validated by loading them.",
        "",
        "## Architecture Overview",
        "",
        overview.strip(),
        "",
        "## Extension Points",
        "",
        "| Point | Category | Location | Example |",
        "| --- | --- | --- | --- |",
    ]
    for gp in generated:
        badge = "UNVERIFIED" if gp.example_status == "unverified" else gp.example_status
        lines.append(
            f"| `{gp.fact.point_id}` | {gp.fact.category} | "
            f"{gp.fact.module}:{gp.fact.lineno} | {badge} |"
        )
    lines += ["", "See [plugin-guide.md](plugin-guide.md) for how to build each one."]
    return "\n".join(lines) + "\n"


def _render_guide(generated: list[GeneratedPoint]) -> str:
    lines = ["# Plugin Guide", ""]
    for gp in generated:
        lines += [
            f"## `{gp.fact.point_id}`",
            "",
            f"- **Category:** {gp.fact.category}",
            f"- **Location:** {gp.fact.module}:{gp.fact.lineno}",
            f"- **Example status:** {gp.example_status}",
            "",
            gp.guide.strip(),
            "",
            "### Example",
            "",
        ]
        if gp.example_status == "unverified":
            lines.append("> WARNING: this example could not be validated automatically.")
            lines.append("")
        lines += ["```python", gp.example_code.strip(), "```", ""]
    return "\n".join(lines) + "\n"
