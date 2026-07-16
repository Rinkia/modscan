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

"""TypeScript / JavaScript language front-end (tree-sitter).

Parses .ts/.tsx/.js/.jsx into the shared `Codebase` model so the graph, detector
and doc generator work on JS/TS the same way they do on Python. `export` marks a
symbol public; `interface` and `abstract class` are subclassable seams;
`extends`/`implements` become bases; decorators are captured for the detector's
registration heuristics.

tree-sitter is an OPTIONAL dependency (like the LLM SDKs), imported lazily.
Install with `pip install modscan[typescript]`.

ponytail: static structure only (classes, functions, interfaces, imports,
decorators). Arrow-function consts and dynamic require()/import() are not mapped
yet — the common plugin seams (interfaces, classes, registration functions) are
covered; the rest is a follow-up if a real target needs it.
"""

from __future__ import annotations

import os

from modscan.languages.base import register_language
from modscan.models import ClassInfo, Codebase, FunctionInfo, ImportInfo, ModuleInfo

_TS_EXTS = (".ts", ".mts", ".cts", ".js", ".mjs", ".cjs")
_TSX_EXTS = (".tsx", ".jsx")
_ALL_EXTS = _TS_EXTS + _TSX_EXTS
_SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "__pycache__"}


def _load_parsers():
    """Lazy-build (typescript, tsx) tree-sitter parsers; clear error if missing."""
    try:
        import tree_sitter_typescript as tsts
        from tree_sitter import Language, Parser
    except ImportError as exc:  # pragma: no cover - trivial guard
        raise RuntimeError(
            "the 'tree-sitter' and 'tree-sitter-typescript' packages are required "
            "for the TypeScript/JavaScript front-end; install with: "
            "pip install modscan[typescript]"
        ) from exc

    return (
        Parser(Language(tsts.language_typescript())),
        Parser(Language(tsts.language_tsx())),
    )


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _name(node, src: bytes) -> str:
    field = node.child_by_field_name("name")
    return _text(field, src) if field is not None else ""


def _decorators(node, src: bytes) -> tuple[str, ...]:
    out = []
    for child in node.children:
        if child.type == "decorator":
            # "@name" or "@name(...)" -> keep the identifier
            raw = _text(child, src).lstrip("@").strip()
            out.append(raw.split("(", 1)[0].strip())
    return tuple(out)


def _params(node, src: bytes) -> tuple[str, ...]:
    params = node.child_by_field_name("parameters")
    if params is None:
        return ()
    out = []
    for child in params.named_children:
        ident = child.child_by_field_name("pattern") or child
        # required_parameter/optional_parameter wrap an identifier
        name = _text(ident, src).split(":", 1)[0].strip()
        if name and name not in ("(", ")"):
            out.append(name)
    return tuple(out)


def _bases(class_node, src: bytes) -> tuple[str, ...]:
    bases: list[str] = []
    for child in class_node.children:
        if child.type == "class_heritage":
            for clause in child.children:
                if clause.type in ("extends_clause", "implements_clause"):
                    for ident in clause.named_children:
                        bases.append(_text(ident, src))
    return tuple(bases)


def _method(node, src: bytes) -> FunctionInfo:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, src) if name_node is not None else ""
    return FunctionInfo(
        name=name,
        lineno=node.start_point[0] + 1,
        is_public=True,
        decorators=_decorators(node, src),
        args=_params(node, src),
    )


def _class(node, src: bytes, exported: bool, abstract: bool) -> ClassInfo:
    methods = []
    body = node.child_by_field_name("body")
    if body is not None:
        for child in body.named_children:
            if child.type in ("method_definition", "method_signature", "abstract_method_signature"):
                methods.append(_method(child, src))
    return ClassInfo(
        name=_name(node, src),
        lineno=node.start_point[0] + 1,
        is_public=exported,
        bases=_bases(node, src),
        decorators=_decorators(node, src),
        methods=tuple(methods),
        is_abstract=abstract,
    )


def _function(node, src: bytes, exported: bool) -> FunctionInfo:
    return FunctionInfo(
        name=_name(node, src),
        lineno=node.start_point[0] + 1,
        is_public=exported,
        decorators=_decorators(node, src),
        args=_params(node, src),
    )


def _import(node, src: bytes) -> ImportInfo | None:
    source = node.child_by_field_name("source")
    if source is None:
        return None
    module = _text(source, src).strip("'\"")
    return ImportInfo(module=module, name=module, fromlist=True)


def _handle_decl(node, src: bytes, module: ModuleInfo, exported: bool) -> None:
    if node.type == "class_declaration":
        module.classes.append(_class(node, src, exported, abstract=False))
    elif node.type == "abstract_class_declaration":
        module.classes.append(_class(node, src, exported, abstract=True))
    elif node.type == "interface_declaration":
        # an interface is a pure contract to implement — a subclassable seam
        module.classes.append(_class(node, src, exported, abstract=True))
    elif node.type == "function_declaration":
        module.functions.append(_function(node, src, exported))
    elif node.type == "import_statement":
        imp = _import(node, src)
        if imp is not None:
            module.imports.append(imp)


def _qualname(root: str, path: str) -> str:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    base, _ext = os.path.splitext(rel)
    return base


def _parse_file(path: str, root: str, parser) -> ModuleInfo:
    module = ModuleInfo(qualname=_qualname(root, path), path=path)
    try:
        with open(path, "rb") as fh:
            src = fh.read()
        tree = parser.parse(src)
    except (OSError, ValueError) as exc:
        module.parse_error = f"{type(exc).__name__}: {exc}"
        return module

    for child in tree.root_node.children:
        if child.type == "export_statement":
            # unwrap: the exported declaration is a named child
            for inner in child.named_children:
                _handle_decl(inner, src, module, exported=True)
        else:
            _handle_decl(child, src, module, exported=False)
    return module


class TypeScriptLanguageParser:
    name = "typescript"
    extensions = _ALL_EXTS

    def parse_codebase(self, root: str) -> Codebase:
        ts_parser, tsx_parser = _load_parsers()
        root = os.path.abspath(root)
        codebase = Codebase(root=root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext not in _ALL_EXTS:
                    continue
                parser = tsx_parser if ext in _TSX_EXTS else ts_parser
                codebase.modules.append(
                    _parse_file(os.path.join(dirpath, fn), root, parser)
                )
        codebase.modules.sort(key=lambda m: m.qualname)
        return codebase


_parser = TypeScriptLanguageParser()
register_language(_parser)
# JavaScript uses the same front-end (the TS grammar is a superset).
register_language(type("_JsAlias", (), {"name": "javascript", "parse_codebase": _parser.parse_codebase})())
