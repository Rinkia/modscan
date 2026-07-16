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

"""Versioned prompt templates for the doc generator.

The system prompt encodes the grounding contract: the model may only use the
facts it is given and must not invent APIs, parameters, or names. All target
knowledge reaches the model as rendered fact blocks (see factblocks.py).
"""

from __future__ import annotations

from modscan.factblocks import FactBlock, render_fact_block

PROMPTS_VERSION = "1.0"

SYSTEM = (
    "You are MODScan's documentation writer. You help developers write plugins "
    "and mods for a target codebase. You are given STRUCTURED FACTS about an "
    "extension point (a place the codebase can be extended). Rules:\n"
    "- Use ONLY the facts provided. Never invent classes, functions, parameters, "
    "module paths, or behavior that is not stated in the facts.\n"
    "- If a detail is not in the facts, do not state it. Do not guess.\n"
    "- Be concise, concrete, and practical. Prefer short paragraphs and lists.\n"
    "- When asked for code, output a single valid Python code block and nothing "
    "else."
)


def architecture_prompt(fact_texts: list[str], dependency_summary: str) -> str:
    joined = "\n\n---\n\n".join(fact_texts)
    return (
        "Write a short 'Architecture Overview' for modders of this codebase. "
        "Summarize how it can be extended, grouping by the kinds of extension "
        "points below. Do not invent anything beyond these facts.\n\n"
        f"Module dependency summary:\n{dependency_summary}\n\n"
        f"Extension points (facts):\n\n{joined}"
    )


def guide_prompt(fb: FactBlock) -> str:
    return (
        "Write a short 'How to extend this' section for the single extension "
        "point below. Explain what it is, when a modder would use it, and the "
        "steps to plug in — grounded strictly in these facts.\n\n"
        f"{render_fact_block(fb)}"
    )


def example_prompt(fb: FactBlock) -> str:
    return (
        "Write a minimal EXAMPLE plugin for the extension point below. "
        "Output ONLY one Python code block, no prose. The example must import "
        f"the target symbol from module '{fb.module}' and, for a class, subclass "
        "it and implement every listed abstract method with a trivial body. Use "
        "only names present in the facts.\n\n"
        f"{render_fact_block(fb)}"
    )
