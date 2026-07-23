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

"""Java language front-end (tree-sitter).

Java maps onto the shared `Codebase` model more directly than any front-end so
far: `class`, `interface` and `abstract class` are already the model's
vocabulary, `extends`/`implements` are bases, and annotations play the part
decorators do elsewhere. Visibility is read from the explicit `public` modifier
rather than inferred, so it is more reliable here than in TypeScript.

Java is also where the modding audience actually is — Minecraft (Forge/Fabric),
Spring, Maven and Gradle plugins.

tree-sitter is an OPTIONAL dependency, imported lazily. Install with
`pip install modscan[java]`.

Source only: no Maven/Gradle resolution, no transitive dependencies, no
bytecode. Nested and inner classes are deliberately not emitted as top-level
seams — a seam is recorded where a user would extend it, and an inner class is
reached through its outer one.
"""

from __future__ import annotations

import os

from modscan.fsutil import walk_source_files
from modscan.languages.base import register_language
from modscan.models import ClassInfo, Codebase, FunctionInfo, ImportInfo, ModuleInfo

_JAVA_EXTS = (".java",)

# Declarations that become a ClassInfo. An interface is a contract to implement,
# so it is abstract by construction; an enum or record is concrete.
_ABSTRACT_BY_KIND = {
    "class_declaration": False,
    "interface_declaration": True,
    "enum_declaration": False,
    "record_declaration": False,
}


def _load_parser():
    """Lazy-build the Java parser; clear error if the grammar is missing."""
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
    except ImportError as exc:  # pragma: no cover - trivial guard
        raise RuntimeError(
            "the 'tree-sitter' and 'tree-sitter-java' packages are required for "
            "the Java front-end; install with: pip install modscan[java]"
        ) from exc

    return Parser(Language(tsjava.language()))


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _name(node, src: bytes) -> str:
    field = node.child_by_field_name("name")
    return _text(field, src) if field is not None else ""


def _type_name(node, src: bytes) -> str:
    """A base's bare name: `Core<T>` -> `Core`, `a.b.Core` -> `Core`.

    Generic arguments and package qualifiers are noise for the detector's
    role-suffix matching, which compares against names like `Handler`/`Plugin`.
    """
    if node.type == "generic_type":
        for child in node.children:
            if child.type in ("type_identifier", "scoped_type_identifier"):
                return _type_name(child, src)
    if node.type == "scoped_type_identifier":
        return _text(node, src).rsplit(".", 1)[-1]
    return _text(node, src)


def _bases(node, src: bytes) -> tuple[str, ...]:
    """`extends` plus every `implements` entry, generics stripped."""
    bases: list[str] = []
    for child in node.children:
        if child.type == "superclass":
            bases += [
                _type_name(c, src)
                for c in child.children
                if c.type not in ("extends", ",")
            ]
        elif child.type in ("super_interfaces", "extends_interfaces"):
            for lst in child.children:
                if lst.type == "type_list":
                    bases += [
                        _type_name(c, src) for c in lst.children if c.type != ","
                    ]
    return tuple(b for b in bases if b)


def _modifiers(node, src: bytes) -> tuple[bool, bool, tuple[str, ...]]:
    """(is_public, is_abstract, annotation names) from a `modifiers` child."""
    mods = next((c for c in node.children if c.type == "modifiers"), None)
    if mods is None:
        return False, False, ()

    annotations: list[str] = []
    is_public = is_abstract = False
    for child in mods.children:
        if child.type in ("annotation", "marker_annotation"):
            # @Plugin(name="x") -> "Plugin", as the TS front-end reduces decorators
            label = child.child_by_field_name("name")
            annotations.append(
                _text(label, src) if label is not None
                else _text(child, src).lstrip("@").split("(", 1)[0].strip()
            )
        elif child.type == "public":
            is_public = True
        elif child.type == "abstract":
            is_abstract = True
    return is_public, is_abstract, tuple(annotations)


def _method(node, src: bytes) -> FunctionInfo:
    params = node.child_by_field_name("parameters")
    args: tuple[str, ...] = ()
    if params is not None:
        args = tuple(
            _name(p, src) or _text(p, src)
            for p in params.named_children
            if p.type in ("formal_parameter", "spread_parameter")
        )
    _pub, _abs, annotations = _modifiers(node, src)
    return FunctionInfo(
        name=_name(node, src),
        lineno=node.start_point[0] + 1,
        is_public=True,  # a method's own visibility is not the seam signal here
        decorators=annotations,
        args=args,
    )


def _class(node, src: bytes) -> ClassInfo:
    is_public, is_abstract, annotations = _modifiers(node, src)
    body = node.child_by_field_name("body")
    methods = []
    if body is not None:
        methods = [
            _method(c, src) for c in body.named_children if c.type == "method_declaration"
        ]
    return ClassInfo(
        name=_name(node, src),
        lineno=node.start_point[0] + 1,
        is_public=is_public,
        bases=_bases(node, src),
        decorators=annotations,
        methods=tuple(methods),
        is_abstract=is_abstract or _ABSTRACT_BY_KIND.get(node.type, False),
    )


def _import(node, src: bytes) -> ImportInfo | None:
    raw = _text(node, src).strip()
    if not raw.startswith("import"):
        return None
    target = raw[len("import"):].strip().rstrip(";").replace("static ", "").strip()
    if not target:
        return None
    return ImportInfo(module=target, name=target.rsplit(".", 1)[-1], fromlist=True)


def _qualname(root: str, path: str) -> str:
    """Dotted, package-style: `org/junit/.../Extension.java` -> `org.junit....Extension`.

    Dots are Java's own convention, so a label id stays checkable by eye against
    the project's documentation — which is what the benchmark's rule requires.
    """
    rel = os.path.relpath(path, root)
    base, _ext = os.path.splitext(rel)
    return base.replace(os.sep, ".").replace("/", ".")


def _parse_file(path: str, root: str, parser) -> ModuleInfo:
    module = ModuleInfo(qualname=_qualname(root, path), path=path)
    try:
        with open(path, "rb") as fh:
            src = fh.read()
        tree = parser.parse(src)
    except (OSError, ValueError) as exc:
        module.parse_error = f"{type(exc).__name__}: {exc}"
        return module

    # Only top-level declarations: an inner class is reached through its outer
    # one, so emitting it as its own seam would invent an extension point.
    for child in tree.root_node.children:
        if child.type in _ABSTRACT_BY_KIND:
            module.classes.append(_class(child, src))
        elif child.type == "import_declaration":
            imp = _import(child, src)
            if imp is not None:
                module.imports.append(imp)
    return module


class JavaLanguageParser:
    name = "java"
    extensions = _JAVA_EXTS
    validates = False  # no in-process JVM execution; docs are static-only

    def parse_codebase(self, root: str, exclude: tuple[str, ...] = ()) -> Codebase:
        parser = _load_parser()
        root = os.path.abspath(root)
        codebase = Codebase(root=root)
        for path in walk_source_files(root, _JAVA_EXTS, skip_paths=exclude):
            codebase.modules.append(_parse_file(path, root, parser))
        codebase.modules.sort(key=lambda m: m.qualname)
        return codebase


register_language(JavaLanguageParser())
