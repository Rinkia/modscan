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

"""Locate risk sinks in a TypeScript / JavaScript tree.

Reuses the tree-sitter front-end the moddability side already ships, then walks
each file for call and `new` expressions. Enumeration only, like the Python
detector: it records where a sink is, never whether attacker-controlled data
reaches it.

Why bindings are tracked
------------------------
Idiomatic JS rarely writes ``child_process.exec(...)``. It writes
``const {exec} = require('child_process')`` and then ``exec(...)``, or
``const cp = require('child_process')`` and then ``cp.exec(...)``. Matching only
the qualified form would miss almost all real code; matching the bare name
``exec`` would collide with ``someRegex.exec(str)``, which is everywhere and
harmless.

So each file's ``require``/``import`` bindings of the sink-bearing modules are
resolved first, and calls are matched against those. This is deliberately
**file-local**: no cross-file or scope-aware resolution. A binding re-assigned or
passed through another module is not followed, which is a known limit, not an
oversight.
"""

from __future__ import annotations

import os

from modscan.fsutil import walk_source_files
from modscan.security.sinks import SinkSpec
from modscan.security.sinks_ts import (
    DYNAMIC_LOADERS,
    GLOBAL_SINKS,
    MODULE_SINKS,
    STRING_TIMERS,
)
from modscan.security.sinks import RiskSink

_TS_EXTS = (".ts", ".mts", ".cts", ".js", ".mjs", ".cjs")
_TSX_EXTS = (".tsx", ".jsx")
_ALL_EXTS = _TS_EXTS + _TSX_EXTS

_STRING_NODES = {"string", "template_string"}


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _qualname(root: str, path: str) -> str:
    rel = os.path.relpath(path, root)
    stem = os.path.splitext(rel)[0]
    return stem.replace(os.sep, "/")


def _args(call):
    """The real argument nodes of a call/new expression (punctuation dropped)."""
    node = call.child_by_field_name("arguments")
    return list(node.named_children) if node is not None else []


def _string_literal(node) -> bool:
    return node is not None and node.type in _STRING_NODES


def _unquote(node, src: bytes) -> str:
    return _text(node, src).strip("'\"`")


# --- binding resolution ------------------------------------------------------


class _Bindings:
    """Per-file view of which names refer to a sink-bearing module."""

    def __init__(self) -> None:
        self.alias: dict[str, str] = {}   # cp   -> "child_process"
        self.member: dict[str, str] = {}  # exec -> "child_process"

    def spec_for_member(self, module: str, name: str) -> SinkSpec | None:
        return MODULE_SINKS.get(module, {}).get(name)

    def bare(self, name: str) -> SinkSpec | None:
        """A destructured member called without a qualifier: ``exec(...)``."""
        module = self.member.get(name)
        return self.spec_for_member(module, name) if module else None

    def qualified(self, obj: str, prop: str) -> SinkSpec | None:
        """``cp.exec(...)`` where ``cp`` is a bound module."""
        module = self.alias.get(obj)
        return self.spec_for_member(module, prop) if module else None


def _bind_pattern(target, module: str, src: bytes, out: _Bindings) -> None:
    """Record what a declaration binds: an alias, or destructured members."""
    if target is None:
        return
    if target.type == "identifier":
        out.alias[_text(target, src)] = module
    elif target.type == "object_pattern":
        for child in target.named_children:
            # {exec} -> shorthand_property_identifier_pattern
            # {exec: run} -> pair_pattern (value is the local name)
            if child.type.endswith("identifier_pattern"):
                out.member[_text(child, src)] = module
            elif child.type == "pair_pattern":
                value = child.child_by_field_name("value")
                if value is not None:
                    out.member[_text(value, src)] = module


def _collect_bindings(tree, src: bytes) -> _Bindings:
    """Find require()/import bindings of the modules that carry sinks."""
    bindings = _Bindings()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)

        # const X = require('child_process')  /  const {exec} = require(...)
        if node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value is not None and value.type == "call_expression":
                callee = value.child_by_field_name("function")
                args = _args(value)
                if (
                    callee is not None
                    and _text(callee, src) == "require"
                    and args
                    and _string_literal(args[0])
                ):
                    module = _unquote(args[0], src)
                    if module in MODULE_SINKS:
                        _bind_pattern(node.child_by_field_name("name"), module, src, bindings)

        # import cp from 'child_process' / import {exec} from 'child_process'
        elif node.type == "import_statement":
            source = node.child_by_field_name("source")
            if source is None:
                continue
            module = _unquote(source, src)
            if module not in MODULE_SINKS:
                continue
            for child in node.named_children:
                if child.type != "import_clause":
                    continue
                for spec in child.named_children:
                    if spec.type == "identifier":                 # default import
                        bindings.alias[_text(spec, src)] = module
                    elif spec.type == "namespace_import":         # * as cp
                        name = spec.child_by_field_name("name") or spec.named_children[-1]
                        bindings.alias[_text(name, src)] = module
                    elif spec.type == "named_imports":            # {exec, spawn}
                        for item in spec.named_children:
                            alias = item.child_by_field_name("alias")
                            name = alias or item.child_by_field_name("name")
                            if name is not None:
                                bindings.member[_text(name, src)] = module
    return bindings


# --- sink matching -----------------------------------------------------------


def _match(call, src: bytes, bindings: _Bindings, is_new: bool) -> SinkSpec | None:
    field = "constructor" if is_new else "function"
    callee = call.child_by_field_name(field)
    if callee is None:
        return None

    if callee.type == "member_expression":
        obj = callee.child_by_field_name("object")
        prop = callee.child_by_field_name("property")
        if obj is None or prop is None:
            return None
        # `cp.exec(...)` / `vm.runInThisContext(...)` on a bound module, or the
        # fully-written `child_process.exec(...)`.
        obj_text, prop_text = _text(obj, src), _text(prop, src)
        return bindings.qualified(obj_text, prop_text) or MODULE_SINKS.get(
            obj_text, {}
        ).get(prop_text)

    if callee.type != "identifier":
        return None
    name = _text(callee, src)

    spec = GLOBAL_SINKS.get(name) or bindings.bare(name)
    if spec is not None:
        return spec

    args = _args(call)
    # A dynamic loader is a sink only with a computed argument: require('fs') is
    # a static import (eslint-plugin-security's detect-non-literal-require).
    if name in DYNAMIC_LOADERS:
        return None if (not args or _string_literal(args[0])) else DYNAMIC_LOADERS[name]
    # Timers evaluate only a *string* first argument; a function is the safe form.
    if name in STRING_TIMERS and args and _string_literal(args[0]):
        return STRING_TIMERS[name]
    return None


def _sinks_in_file(path: str, root: str, parser) -> list[RiskSink]:
    try:
        with open(path, "rb") as fh:
            src = fh.read()
    except OSError:
        return []
    tree = parser.parse(src)
    bindings = _collect_bindings(tree, src)
    module = _qualname(root, path)

    found: list[RiskSink] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type not in ("call_expression", "new_expression"):
            continue
        spec = _match(node, src, bindings, is_new=node.type == "new_expression")
        if spec is None:
            continue
        field = "constructor" if node.type == "new_expression" else "function"
        callee = node.child_by_field_name(field)
        found.append(
            RiskSink(
                id=spec.id, category=spec.category, severity=spec.severity,
                confidence=spec.confidence, module=module,
                dotted=_text(callee, src) if callee is not None else "",
                lineno=node.start_point[0] + 1, detail=None,
            )
        )
    return found


def find_ts_risk_sinks(root: str, exclude: tuple[str, ...] = ()) -> list[RiskSink]:
    """Every risk sink in the TS/JS tree under ``root``, sorted by location."""
    # The moddability front-end owns the tree-sitter bootstrap (and its clear
    # error when the optional dependency is missing); reuse it rather than
    # duplicating parser construction here.
    from modscan.languages.typescript import _load_parsers

    ts_parser, tsx_parser = _load_parsers()
    root = os.path.abspath(root)
    sinks: list[RiskSink] = []
    for path in walk_source_files(root, _ALL_EXTS, skip_paths=exclude):
        parser = tsx_parser if os.path.splitext(path)[1] in _TSX_EXTS else ts_parser
        sinks += _sinks_in_file(path, root, parser)
    sinks.sort(key=lambda s: (s.module, s.lineno, s.dotted))
    return sinks
