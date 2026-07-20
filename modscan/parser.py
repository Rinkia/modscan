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

"""Layer 1: deterministic AST parsing of a Python codebase.

Walks a directory of .py files and extracts a factual model: public/private
functions and classes, static imports, dynamic-import calls, decorators, and
base classes. No LLM, no inference beyond what the AST literally states — this
layer must be repeatable and verifiable.
"""

from __future__ import annotations

import ast
import os

from modscan.models import (
    ClassInfo,
    Codebase,
    DynamicImport,
    FunctionInfo,
    ImportInfo,
    ModuleInfo,
)

# Runtime-import call patterns worth flagging as plugin-loading seams.
# Keyed by the trailing attribute/name of the call.
_DYNAMIC_CALLS = {
    "import_module": "import_module",
    "__import__": "__import__",
    "iter_modules": "iter_modules",
    "walk_packages": "iter_modules",
    "entry_points": "entry_points",
    # pkg_resources' pre-importlib.metadata entry-point API — same concept
    # as entry_points(), so it shares that kind rather than inventing a new one.
    "load_entry_point": "entry_points",
    "iter_entry_points": "entry_points",
    # Werkzeug/Django-style "module:attr" string loader.
    "import_string": "import_string",
    # importlib.abc.Loader.load_module(name) — legacy loader API.
    "load_module": "load_module",
    # importlib.util.find_spec(name) — locates (doesn't yet execute) a module.
    "find_spec": "find_spec",
    # pkgutil.get_loader(name) — locates the loader for a dynamically named module.
    "get_loader": "get_loader",
}


def _dotted_name(node: ast.AST) -> str:
    """Render a Name/Attribute chain as a dotted string; '' if not a name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _first_string_arg(call: ast.Call) -> str | None:
    """Return the first positional arg if it is a string literal, else None.

    A constant string means the import target is statically known; anything else
    (a variable, expression) means it is resolved at runtime.
    """
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _parse_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    return FunctionInfo(
        name=node.name,
        lineno=node.lineno,
        is_public=_is_public(node.name),
        decorators=tuple(_dotted_name(d) for d in node.decorator_list),
        args=tuple(a.arg for a in node.args.args),
    )


def _parse_class(node: ast.ClassDef) -> ClassInfo:
    bases = tuple(_dotted_name(b) for b in node.bases)
    decorators = tuple(_dotted_name(d) for d in node.decorator_list)
    methods = tuple(
        _parse_function(child)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    abstract = any(b.split(".")[-1] in {"ABC", "ABCMeta"} for b in bases) or any(
        "abstractmethod" in m.decorators
        or any("abstractmethod" in d for d in m.decorators)
        for m in methods
    )
    return ClassInfo(
        name=node.name,
        lineno=node.lineno,
        is_public=_is_public(node.name),
        bases=bases,
        decorators=decorators,
        methods=methods,
        is_abstract=abstract,
    )


class _ModuleVisitor(ast.NodeVisitor):
    """Collects top-level defs plus dynamic-import calls anywhere in the tree."""

    def __init__(self, module: ModuleInfo) -> None:
        self.module = module

    # -- top-level definitions only (don't descend into nested scopes for defs) --
    def visit_Module(self, node: ast.Module) -> None:
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.module.functions.append(_parse_function(child))
            elif isinstance(child, ast.ClassDef):
                self.module.classes.append(_parse_class(child))
            elif isinstance(child, ast.Import):
                self._add_import(child)
            elif isinstance(child, ast.ImportFrom):
                self._add_import_from(child)
            elif isinstance(child, ast.Assign):
                self._maybe_all(child)
        # Dynamic-import calls can appear at any depth: scan the whole tree.
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                self._maybe_dynamic(sub)

    def _add_import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.module.imports.append(
                ImportInfo(module=alias.name, name=alias.asname or alias.name, fromlist=False)
            )

    def _add_import_from(self, node: ast.ImportFrom) -> None:
        mod = ("." * node.level) + (node.module or "")
        for alias in node.names:
            self.module.imports.append(
                ImportInfo(module=mod, name=alias.asname or alias.name, fromlist=True)
            )

    def _maybe_all(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    names = tuple(
                        e.value
                        for e in node.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    )
                    self.module.all_exports = names

    def _maybe_dynamic(self, call: ast.Call) -> None:
        func = call.func
        trailing = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else ""
        )
        kind = _DYNAMIC_CALLS.get(trailing)
        if kind is None:
            return
        self.module.dynamic_imports.append(
            DynamicImport(kind=kind, lineno=call.lineno, argument=_first_string_arg(call))
        )


def _qualname(root: str, path: str) -> str:
    rel = os.path.relpath(path, root)
    rel = rel[:-3] if rel.endswith(".py") else rel  # strip .py
    parts = [p for p in rel.split(os.sep) if p and p != "__init__"]
    return ".".join(parts)


def parse_file(path: str, root: str | None = None) -> ModuleInfo:
    """Parse a single .py file into a ModuleInfo (never raises on bad source)."""
    root = root or os.path.dirname(path)
    module = ModuleInfo(qualname=_qualname(root, path), path=path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        module.parse_error = f"{type(exc).__name__}: {exc}"
        return module
    _ModuleVisitor(module).visit(tree)
    return module


_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache", "node_modules"}


def parse_codebase(root: str) -> Codebase:
    """Recursively parse every .py file under `root`."""
    root = os.path.abspath(root)
    codebase = Codebase(root=root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                codebase.modules.append(parse_file(os.path.join(dirpath, fn), root))
    codebase.modules.sort(key=lambda m: m.qualname)
    return codebase
