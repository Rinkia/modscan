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

"""Locate risk sinks in a Java tree.

Reuses the tree-sitter front-end the moddability side already ships, then walks
each file for method invocations, constructors and deserialization-hook
definitions. Enumeration only, like the Python and TS detectors: it records where
a sink is, never whether attacker-controlled data reaches it.

Why the receiver's *type* is resolved
-------------------------------------
Java has no bare ``eval``. Every sink here is a method on some object, and the
same method name is harmless on a different type — ``x.load(...)`` is a sink on
SnakeYAML's ``Yaml`` and nothing at all on a ``Properties``. Matching by method
name alone would flood the report; matching only the fully-written
``javax.script.ScriptEngine.eval`` would find nothing, because real code declares
a variable and calls through it.

So each file's variable and field declarations are read first, giving
``engine -> ScriptEngine``, and calls are matched on the declared type. Three
further shapes are resolved because they are the idioms that actually appear:

* ``new ObjectInputStream(in).readObject()`` — the receiver is a constructor, so
  the created type is the receiver type.
* ``Runtime.getRuntime().exec(...)`` — the receiver is itself a call; its own
  receiver (``Runtime``) is the type.
* ``Class.forName(...)`` — a static call, where the receiver identifier *is* the
  type name.

This is deliberately **file-local**, like the TS detector: no cross-file
resolution, no import following, no scope analysis. A receiver whose type comes
from a method return or a field on another class is not resolved, and that is a
stated limit rather than an oversight — an unresolved receiver yields no finding,
so the failure mode is a miss, never a false alarm.
"""

from __future__ import annotations

import os

from modscan.fsutil import walk_source_files
from modscan.security.sinks import RiskSink, SinkSpec
from modscan.security.sinks_java import (
    SHELL_LITERALS,
    match_constructor,
    match_deserialization_hook,
    match_typed_call,
)

_JAVA_EXTS = (".java",)


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _qualname(root: str, path: str) -> str:
    """Dotted, package-style — the same convention the Java front-end uses."""
    rel = os.path.relpath(path, root)
    base, _ext = os.path.splitext(rel)
    return base.replace(os.sep, ".").replace("/", ".")


def _bare_type(text: str) -> str:
    """`java.io.ObjectInputStream<T>` -> `ObjectInputStream`."""
    return text.split("<")[0].strip().rsplit(".", 1)[-1]


# --- file-local type bindings ------------------------------------------------


def _collect_types(root_node, src: bytes) -> dict[str, str]:
    """Variable/field name -> the set of types bound to it anywhere in the file.

    A *set*, not one type, because a file reuses a name: commons-lang3's
    SerializationUtils binds `in` to both `ClassLoaderAwareObjectInputStream` and
    `ObjectInputStream`, and a last-write-wins map silently drops one, so the
    `in.readObject()` under the losing binding goes unreported. This was the miss
    the Semgrep cross-check caught. Tracking every bound type over-approximates
    only for a reused name, and the failure mode is then over-reporting a sink to
    review rather than hiding one — the side the lens deliberately errs on. Full
    scope analysis would disambiguate, at a cost this catalog does not need.
    """
    types: dict[str, set[str]] = {}

    def bind(name_node, type_node) -> None:
        if name_node is not None and type_node is not None:
            types.setdefault(_text(name_node, src), set()).add(_bare_type(_text(type_node, src)))

    stack = [root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        # A try-with-resources header binds a typed variable too
        # (`try (ObjectInputStream in = ...)`) but as a `resource` node carrying
        # its own type+name fields, not a variable_declarator — miss it and every
        # sink called on a resource (the idiomatic way to use ObjectInputStream)
        # goes unresolved. Found by the Semgrep cross-check on commons-lang3.
        if node.type == "resource":
            bind(node.child_by_field_name("name"), node.child_by_field_name("type"))
            continue
        if node.type not in ("local_variable_declaration", "field_declaration"):
            continue
        type_node = node.child_by_field_name("type")
        for child in node.children:
            if child.type == "variable_declarator":
                bind(child.child_by_field_name("name"), type_node)
    return types


def _receiver_types(node, src: bytes, types: dict[str, set[str]]) -> set[str]:
    """Candidate types of a call's receiver, or empty when unresolved file-locally.

    A set because a reused variable name may carry several declared types (see
    `_collect_types`). The caller matches the catalog against each candidate.
    """
    if node is None:
        return set()
    if node.type == "identifier":
        name = _text(node, src)
        # A declared variable resolves to its bound type(s); otherwise the
        # identifier is itself a type name, which is how a static call reads
        # (`Class.forName`).
        return types.get(name) or {name}
    if node.type == "object_creation_expression":
        created = node.child_by_field_name("type")
        return {_bare_type(_text(created, src))} if created is not None else set()
    if node.type == "method_invocation":
        # `Runtime.getRuntime().exec(...)`: the chain's own receiver is the type.
        return _receiver_types(node.child_by_field_name("object"), src, types)
    if node.type in ("field_access", "scoped_identifier"):
        return {_bare_type(_text(node, src))}
    return set()


# --- shell elevation ---------------------------------------------------------


def _names_a_shell(call, src: bytes) -> bool:
    """True when a process call's arguments literally name a shell.

    Java's process API does not use a shell unless the command array says so, so
    `exec(new String[]{"sh", "-c", cmd})` is the analogue of Python's
    `shell=True`. Matching whole quoted literals rather than substrings keeps a
    path like "/usr/bin/pushd" from reading as a shell.
    """
    args = call.child_by_field_name("arguments")
    if args is None:
        return False
    stack = [args]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "string_literal":
            if _text(node, src).strip("\"'") in SHELL_LITERALS:
                return True
    return False


# --- deserialization hooks ---------------------------------------------------


def _deserialization_hook(node, src: bytes) -> SinkSpec | None:
    """A `readObject`/`readResolve`/`readExternal` *definition*, signature-checked.

    Java's `__reduce__`. The signature check is what keeps it precise: a method
    called `readObject` that takes no `ObjectInput` is somebody's own reader, not
    the serialization hook.
    """
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _text(name_node, src)
    spec = match_deserialization_hook(name)
    if spec is None:
        return None
    params = node.child_by_field_name("parameters")
    params_text = _text(params, src) if params is not None else "()"
    if name == "readResolve":
        return spec if params_text.replace(" ", "") == "()" else None
    return spec if "ObjectInput" in params_text else None


# --- the walk ----------------------------------------------------------------


def _sinks_in_file(path: str, root: str, parser) -> list[RiskSink]:
    try:
        with open(path, "rb") as fh:
            src = fh.read()
    except OSError:
        return []
    tree = parser.parse(src)
    types = _collect_types(tree.root_node, src)
    module = _qualname(root, path)

    found: list[RiskSink] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)

        if node.type == "method_declaration":
            spec = _deserialization_hook(node, src)
            if spec is not None:
                found.append(_sink(spec, module, _text(node.child_by_field_name("name"), src), node))
            continue

        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            method = _text(name_node, src)
            spec = matched = None
            for receiver in _receiver_types(node.child_by_field_name("object"), src, types):
                spec = match_typed_call(receiver, method)
                if spec is not None:
                    matched = receiver
                    break
            if spec is None:
                continue
            if spec.elevate_on_shell and _names_a_shell(node, src):
                spec = spec.elevated()
            found.append(_sink(spec, module, f"{matched}.{method}", node))
            continue

        if node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node is None:
                continue
            created = _bare_type(_text(type_node, src))
            spec = match_constructor(created)
            if spec is None:
                continue
            if spec.elevate_on_shell and _names_a_shell(node, src):
                spec = spec.elevated()
            found.append(_sink(spec, module, f"new {created}", node))

    # `new ProcessBuilder(cmd).start()` is one act of process spawning written as
    # two nodes on one line; report it once.
    return _dedupe(found)


def _sink(spec: SinkSpec, module: str, dotted: str, node) -> RiskSink:
    return RiskSink(
        id=spec.id,
        category=spec.category,
        severity=spec.severity,
        confidence=spec.confidence,
        module=module,
        dotted=dotted,
        lineno=node.start_point[0] + 1,
        detail=None,
    )


def _dedupe(sinks: list[RiskSink]) -> list[RiskSink]:
    seen: set[tuple[str, int, str]] = set()
    out: list[RiskSink] = []
    for sink in sinks:
        key = (sink.module, sink.lineno, sink.id)
        if key in seen:
            continue
        seen.add(key)
        out.append(sink)
    return out


def find_java_risk_sinks(root: str, exclude: tuple[str, ...] = ()) -> list[RiskSink]:
    """Every risk sink in the Java tree under ``root``, sorted by location."""
    # The moddability front-end owns the tree-sitter bootstrap (and its clear
    # error when the optional dependency is missing); reuse it rather than
    # duplicating parser construction here.
    from modscan.languages.java import _load_parser

    parser = _load_parser()
    root = os.path.abspath(root)
    sinks: list[RiskSink] = []
    for path in walk_source_files(root, _JAVA_EXTS, skip_paths=exclude):
        sinks += _sinks_in_file(path, root, parser)
    sinks.sort(key=lambda s: (s.module, s.lineno, s.dotted))
    return sinks
