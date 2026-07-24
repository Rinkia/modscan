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

"""Locate risk sinks in a Python tree.

Reuses MODScan's public ``parse_codebase`` for file discovery and module
qualnames — its only dependency on the moddability side — then makes one AST
pass per module to find sink calls and ``__reduce__`` definitions. Detection is
enumeration only: it records where a sink is, never whether attacker-controlled
data reaches it. Deterministic, offline, no LLM.
"""

from __future__ import annotations

import ast

from modscan.parser import parse_codebase
from modscan.security.sinks import RiskSink, match_call, match_reduce


def _dotted(node: ast.AST) -> str:
    """Render a Name/Attribute chain as a dotted string; '' if not a name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _first_string_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _has_shell_true(call: ast.Call) -> bool:
    """True if the call passes a literal ``shell=True``.

    Only a literal counts: a variable could be either, and guessing would inflate
    the severity on evidence the parser does not have.
    """
    return any(
        kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in call.keywords
    )


def _sink_from_call(call: ast.Call, module: str) -> RiskSink | None:
    dotted = _dotted(call.func)
    spec = match_call(dotted)
    if spec is None:
        return None
    if spec.elevate_on_shell and _has_shell_true(call):
        spec = spec.elevated()
    return RiskSink(
        id=spec.id, category=spec.category, severity=spec.severity,
        confidence=spec.confidence, module=module, dotted=dotted,
        lineno=call.lineno, detail=_first_string_arg(call),
    )


def _sink_from_reduce(node: ast.AST, module: str) -> RiskSink | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    spec = match_reduce(node.name)
    if spec is None:
        return None
    return RiskSink(
        id=spec.id, category=spec.category, severity=spec.severity,
        confidence=spec.confidence, module=module, dotted=node.name,
        lineno=node.lineno, detail=None,
    )


def find_risk_sinks(
    root: str, exclude: tuple[str, ...] = (), language: str = "python"
) -> list[RiskSink]:
    """Every risk sink under ``root``, sorted by (module, line, name).

    Uses ``parse_codebase`` for file discovery + qualnames (skipping files it
    could not parse), then re-parses each to walk for sinks.

    ``language`` selects the front-end; "typescript"/"javascript" share the
    tree-sitter detector and "java" has its own. Python is the default, so the
    released call signature is unchanged.
    """
    if language in ("typescript", "javascript"):
        from modscan.security.detect_ts import find_ts_risk_sinks

        return find_ts_risk_sinks(root, exclude=exclude)
    if language == "java":
        from modscan.security.detect_java import find_java_risk_sinks

        return find_java_risk_sinks(root, exclude=exclude)
    if language != "python":
        raise ValueError(
            f"unknown language {language!r}; expected 'python', 'typescript', "
            "'javascript' or 'java'"
        )

    codebase = parse_codebase(root, exclude=exclude)
    sinks: list[RiskSink] = []
    for mod in codebase.ok_modules:
        try:
            with open(mod.path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=mod.path)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            found = (
                _sink_from_call(node, mod.qualname)
                if isinstance(node, ast.Call)
                else _sink_from_reduce(node, mod.qualname)
            )
            if found is not None:
                sinks.append(found)
    sinks.sort(key=lambda s: (s.module, s.lineno, s.dotted))
    return sinks
