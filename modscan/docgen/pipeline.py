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

"""Layer 4 orchestration: source tree in, documented extension points out.

parse -> graph -> detect -> validate -> keep confirmed points -> build fact
blocks -> ask the LLM for prose and an example -> re-validate the example ->
write Markdown + JSON.

Facts come from the parser; prose comes from the LLM; correctness comes from the
validator. The model only ever sees fact blocks, never raw source.

SECURITY / TRUST BOUNDARY
-------------------------
Example validation EXECUTES generated code (and imports the target) to confirm a
concrete plugin really loads. Same trust boundary as the validator: run only on
code you trust. Pass `validate_examples=False` to skip execution, or
`sandbox=True` to contain it in a child process.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from modscan.detector import detect_extension_points
from modscan.docgen import examples as ex
from modscan.docgen import render
from modscan.docgen.types import DocReport, DroppedPoint, GeneratedPoint
from modscan.factblocks import build_fact_block, build_module_index, render_fact_block
from modscan.graph import build_graph
from modscan.languages import get_language_parser
from modscan.execution import preserve_sys_modules
from modscan.models import Codebase, ExampleStatus, ExtensionPoint
from modscan.preflight import PreflightError, probe_target
from modscan.prompts import SYSTEM, architecture_prompt, example_prompt, guide_prompt
from modscan.providers.base import Provider
from modscan.validator import validate_points

# Validation method recorded for languages that cannot be executed in-process.
_STATIC_METHOD = "static"


def _dependency_summary(dependencies: dict[str, set[str]]) -> str:
    edges = sum(len(v) for v in dependencies.values())
    return f"{len(dependencies)} internal modules, {edges} dependency edges"


def _drop_reason(detail: str) -> str:
    """Classify why validation failed, from its detail string. An import failure
    is often a missing dependency; anything else imported but could not be
    exercised (not a class, not callable, could not instantiate)."""
    return "import_failed" if detail.startswith("import failed") else "validation_failed"


def _collect_facts(
    codebase: Codebase,
    points: list[ExtensionPoint],
    root: str,
    runtime_validated: bool,
    limit: int | None,
):
    """Select the points to document and turn them into grounded fact blocks.

    Python seams are proven by actually loading them, so only confirmed points
    get documented. Languages we cannot execute document every detected point
    statically instead.

    Returns ``(facts, dropped)``: the fact blocks to document, and the points
    that failed validation with a classified reason, so the run can explain why
    it is thinner than the detection rather than filtering silently.
    """
    considered = points[:limit] if limit is not None else points
    index = build_module_index(codebase)
    if not runtime_validated:
        facts = [build_fact_block(codebase, p, _STATIC_METHOD, index) for p in considered]
        return facts, []

    validations = validate_points(root, considered)
    facts = []
    dropped = []
    # strict=True: a length mismatch here is a bug, not something to silently
    # truncate away (this used to rely on zip's implicit truncation).
    for p, v in zip(considered, validations, strict=True):
        if v.ok:
            facts.append(build_fact_block(codebase, p, v.method, index))
        else:
            dropped.append(
                DroppedPoint(
                    point_id=f"{p.seam.module}:{p.seam.name}",
                    category=p.category,
                    location=f"{p.seam.module}:{p.seam.lineno}",
                    reason=_drop_reason(v.detail),
                    detail=v.detail,
                )
            )
    return facts, dropped


def generate_docs(
    root: str,
    provider: Provider,
    out_dir: str,
    *,
    min_score: float = 0.5,
    limit: int | None = None,
    max_example_retries: int = ex.DEFAULT_RETRIES,
    validate_examples: bool = True,
    sandbox: bool = False,
    language: str = "python",
    concurrency: int = 1,
) -> DocReport:
    """Generate modding docs (Markdown + JSON) for the codebase at `root`.

    `language` selects the front-end (python, typescript, javascript). Only
    languages whose parser reports `validates=True` (Python) run runtime example
    validation; others produce static docs with example status "generated".
    Set `sandbox=True` to validate Python examples in an isolated child process
    instead of the host interpreter (see sandbox.py).

    `concurrency` fans the per-point LLM calls out across threads. The run is
    dominated by sequential network round-trips (1 + points x (1..retries)), so
    this is where the wall-clock time is. Output is unaffected: results are
    collected in input order and in-process validation is serialised. Defaults
    to 1 (fully sequential) — raise it deliberately.
    """
    retries = ex.clamp_retries(max_example_retries)

    parser = get_language_parser(language)
    # Keep this run's own output out of the scan: if out_dir sits inside the
    # scanned tree, a re-run would otherwise parse the files this run generated.
    codebase = parser.parse_codebase(root, exclude=(out_dir,))
    graph = build_graph(codebase)
    points = detect_extension_points(graph, min_score=min_score)

    runtime_validated = getattr(parser, "validates", language == "python")

    ext = render.example_ext(language)
    # In-process validation mutates sys.path/sys.modules, so it is serialised
    # across workers; the LLM calls (the actual bottleneck) still overlap.
    validation_lock = threading.Lock()

    def build(fb) -> GeneratedPoint:
        guide = provider.generate(SYSTEM, guide_prompt(fb))
        if runtime_validated:
            code, status = ex.make_example(
                provider, root, fb, retries, validate_examples, sandbox, validation_lock
            )
        else:
            code = ex.extract_code(provider.generate(SYSTEM, example_prompt(fb)))
            status = ExampleStatus.GENERATED  # written by the LLM, not executed
        return GeneratedPoint(
            fact=fb,
            guide=guide,
            example_code=code,
            example_status=status,
            example_path=render.example_path(fb.point_id, ext),
        )

    # Everything that imports target code runs inside preserve_sys_modules, so the
    # target's modules do not leak into the next run in the same process — two
    # consecutive runs against different trees stay independent.
    with preserve_sys_modules():
        # Fail fast if the target cannot be imported at all — otherwise every
        # example fails to load and the run spends LLM calls producing empty docs.
        # Only probe when we would execute target code anyway (validation
        # enabled); it never adds an execution path the caller has not consented to.
        if runtime_validated and validate_examples:
            result = probe_target(codebase, root)
            if not result.ok:
                raise PreflightError(result)

        facts, dropped = _collect_facts(codebase, points, root, runtime_validated, limit)

        overview = provider.generate(
            SYSTEM,
            architecture_prompt(
                [render_fact_block(f) for f in facts],
                _dependency_summary(graph.dependencies),
            ),
        )

        if concurrency > 1 and len(facts) > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                # `map` yields in input order, so output is identical to serial.
                generated = list(pool.map(build, facts))
        else:
            generated = [build(fb) for fb in facts]

    manifest_path = render.write_outputs(out_dir, root, overview, generated, dropped)
    return DocReport(
        out_dir=out_dir, overview=overview, points=generated,
        manifest_path=manifest_path, dropped=dropped,
    )
