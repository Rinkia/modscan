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

import os
from dataclasses import dataclass, field

from modscan.detector import detect_extension_points
from modscan.execution import (
    SUBCLASS_KINDS,
    example_defines_working_subclass,
    example_loads,
)
from modscan.factblocks import FactBlock, build_fact_block, render_fact_block
from modscan.fsutil import slugify
from modscan.graph import build_graph
from modscan.languages import get_language_parser
from modscan.manifest import build_manifest, write_manifest
from modscan.models import ExampleStatus
from modscan.prompts import SYSTEM, architecture_prompt, example_prompt, guide_prompt
from modscan.providers.base import Provider
from modscan.sandbox import validate_in_sandbox
from modscan.validator import validate_points

# Example-validation retry bounds (locked in the Task 4 plan).
_MIN_RETRIES = 3
_MAX_RETRIES = 5
_DEFAULT_RETRIES = 4

# Statuses that end the retry loop, strongest first. See models.ExampleStatus
# for what each one means.
_OK_STATUSES = (
    ExampleStatus.VERIFIED,
    ExampleStatus.EXECUTED,
    ExampleStatus.COMPILED,
)


@dataclass
class GeneratedPoint:
    fact: FactBlock
    guide: str
    example_code: str
    example_status: ExampleStatus
    example_path: str


@dataclass
class DocReport:
    out_dir: str
    overview: str
    points: list[GeneratedPoint] = field(default_factory=list)
    manifest_path: str = ""

    @property
    def verified_count(self) -> int:
        return sum(1 for p in self.points if p.example_status == ExampleStatus.VERIFIED)


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


def _verify_example(
    root: str, fb: FactBlock, code: str, validate: bool, sandbox: bool
) -> ExampleStatus:
    """Return an example status: verified | executed | compiled | invalid.

    Loading/execution is delegated to `execution.py` (or, with `sandbox` set, to
    a child process running that same code) so the in-process and sandboxed
    paths can never disagree.
    """
    try:
        compile(code, "<modscan-example>", "exec")
    except SyntaxError:
        return ExampleStatus.INVALID
    if not validate:
        return ExampleStatus.COMPILED

    is_subclass_seam = fb.kind in SUBCLASS_KINDS
    if sandbox:
        ok = validate_in_sandbox(root, fb.module, fb.symbol, code, fb.kind)
    elif is_subclass_seam:
        ok = example_defines_working_subclass(root, fb.module, fb.symbol, code)
    else:
        # hook/registration/api: no subclass to instantiate, but we can still
        # load the example to catch bad imports and module-level errors.
        ok = example_loads(root, code)

    if not ok:
        return ExampleStatus.INVALID
    return ExampleStatus.VERIFIED if is_subclass_seam else ExampleStatus.EXECUTED


def _make_example(
    provider: Provider,
    root: str,
    fb: FactBlock,
    retries: int,
    validate: bool,
    sandbox: bool,
) -> tuple[str, ExampleStatus]:
    """Generate and validate an example plugin, retrying up to `retries` times."""
    code = ""
    for _ in range(retries):
        code = _extract_code(provider.generate(SYSTEM, example_prompt(fb)))
        status = _verify_example(root, fb, code, validate, sandbox)
        if status in _OK_STATUSES:
            return code, status
    return code, ExampleStatus.UNVERIFIED


def _dependency_summary(dependencies: dict[str, set[str]]) -> str:
    edges = sum(len(v) for v in dependencies.values())
    return f"{len(dependencies)} internal modules, {edges} dependency edges"


def _example_filename(point_id: str, ext: str) -> str:
    return f"{slugify(point_id)}{ext}"


_LANGUAGE_EXT = {"python": ".py", "javascript": ".js", "typescript": ".ts"}


def _example_ext(language: str) -> str:
    return _LANGUAGE_EXT.get(language, ".ts")


def generate_docs(
    root: str,
    provider: Provider,
    out_dir: str,
    *,
    min_score: float = 0.5,
    limit: int | None = None,
    max_example_retries: int = _DEFAULT_RETRIES,
    validate_examples: bool = True,
    sandbox: bool = False,
    language: str = "python",
) -> DocReport:
    """Generate modding docs (Markdown + JSON) for the codebase at `root`.

    `language` selects the front-end (python, typescript, javascript). Only
    languages whose parser reports `validates=True` (Python) run runtime example
    validation; others produce static docs with example status "generated".
    Set `sandbox=True` to validate Python examples in an isolated child process
    instead of the host interpreter (see sandbox.py).
    """
    retries = max(_MIN_RETRIES, min(_MAX_RETRIES, max_example_retries))

    parser = get_language_parser(language)
    codebase = parser.parse_codebase(root)
    graph = build_graph(codebase)
    points = detect_extension_points(graph, min_score=min_score)

    runtime_validated = getattr(parser, "validates", language == "python")
    if runtime_validated:
        # Keep only points the validator confirmed; carry its method into facts.
        validations = validate_points(root, points, limit=limit)
        confirmed = [(p, v) for p, v in zip(points, validations) if v.ok]
        facts = [build_fact_block(codebase, p, v.method) for p, v in confirmed]
    else:
        # No in-process execution for this language: document all detected points
        # statically (the LLM example is generated but not run).
        chosen = points[:limit] if limit is not None else points
        facts = [build_fact_block(codebase, p, "static") for p in chosen]

    overview = provider.generate(
        SYSTEM,
        architecture_prompt(
            [render_fact_block(f) for f in facts], _dependency_summary(graph.dependencies)
        ),
    )

    ext = _example_ext(language)
    generated: list[GeneratedPoint] = []
    for fb in facts:
        guide = provider.generate(SYSTEM, guide_prompt(fb))
        if runtime_validated:
            code, status = _make_example(
                provider, root, fb, retries, validate_examples, sandbox
            )
        else:
            code = _extract_code(provider.generate(SYSTEM, example_prompt(fb)))
            status = ExampleStatus.GENERATED  # written by the LLM, not executed
        generated.append(
            GeneratedPoint(
                fact=fb,
                guide=guide,
                example_code=code,
                example_status=status,
                example_path=f"examples/{_example_filename(fb.point_id, ext)}",
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
        badge = (
            "UNVERIFIED"
            if gp.example_status == ExampleStatus.UNVERIFIED
            else gp.example_status
        )
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
        if gp.example_status == ExampleStatus.UNVERIFIED:
            lines.append("> WARNING: this example could not be validated automatically.")
            lines.append("")
        if gp.example_path.endswith(".py"):
            fence = "python"
        elif gp.example_path.endswith(".js"):
            fence = "javascript"
        else:
            fence = "typescript"
        lines += [f"```{fence}", gp.example_code.strip(), "```", ""]
    return "\n".join(lines) + "\n"
