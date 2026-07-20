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

from modscan.detector import detect_extension_points
from modscan.docgen import examples as ex
from modscan.docgen import render
from modscan.docgen.types import DocReport, GeneratedPoint
from modscan.factblocks import build_fact_block, render_fact_block
from modscan.graph import build_graph
from modscan.languages import get_language_parser
from modscan.models import Codebase, ExampleStatus, ExtensionPoint
from modscan.prompts import SYSTEM, architecture_prompt, example_prompt, guide_prompt
from modscan.providers.base import Provider
from modscan.validator import validate_points

# Validation method recorded for languages that cannot be executed in-process.
_STATIC_METHOD = "static"


def _dependency_summary(dependencies: dict[str, set[str]]) -> str:
    edges = sum(len(v) for v in dependencies.values())
    return f"{len(dependencies)} internal modules, {edges} dependency edges"


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
    """
    considered = points[:limit] if limit is not None else points
    if not runtime_validated:
        return [build_fact_block(codebase, p, _STATIC_METHOD) for p in considered]

    validations = validate_points(root, considered)
    # strict=True: a length mismatch here is a bug, not something to silently
    # truncate away (this used to rely on zip's implicit truncation).
    return [
        build_fact_block(codebase, p, v.method)
        for p, v in zip(considered, validations, strict=True)
        if v.ok
    ]


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
) -> DocReport:
    """Generate modding docs (Markdown + JSON) for the codebase at `root`.

    `language` selects the front-end (python, typescript, javascript). Only
    languages whose parser reports `validates=True` (Python) run runtime example
    validation; others produce static docs with example status "generated".
    Set `sandbox=True` to validate Python examples in an isolated child process
    instead of the host interpreter (see sandbox.py).
    """
    retries = ex.clamp_retries(max_example_retries)

    parser = get_language_parser(language)
    codebase = parser.parse_codebase(root)
    graph = build_graph(codebase)
    points = detect_extension_points(graph, min_score=min_score)

    runtime_validated = getattr(parser, "validates", language == "python")
    facts = _collect_facts(codebase, points, root, runtime_validated, limit)

    overview = provider.generate(
        SYSTEM,
        architecture_prompt(
            [render_fact_block(f) for f in facts], _dependency_summary(graph.dependencies)
        ),
    )

    ext = render.example_ext(language)
    generated: list[GeneratedPoint] = []
    for fb in facts:
        guide = provider.generate(SYSTEM, guide_prompt(fb))
        if runtime_validated:
            code, status = ex.make_example(
                provider, root, fb, retries, validate_examples, sandbox
            )
        else:
            code = ex.extract_code(provider.generate(SYSTEM, example_prompt(fb)))
            status = ExampleStatus.GENERATED  # written by the LLM, not executed
        generated.append(
            GeneratedPoint(
                fact=fb,
                guide=guide,
                example_code=code,
                example_status=status,
                example_path=render.example_path(fb.point_id, ext),
            )
        )

    manifest_path = render.write_outputs(out_dir, root, overview, generated)
    return DocReport(
        out_dir=out_dir, overview=overview, points=generated, manifest_path=manifest_path
    )
