"""Data model for a scanned codebase.

Plain dataclasses, no behavior. The parser (layer 1) fills these in; the
extension graph (layer 2) and detector (layer 3) read them. Everything here is
a deterministic fact extracted from the AST — no inference, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportInfo:
    """A static `import x` or `from x import y`."""

    module: str  # imported module, e.g. "os.path"
    name: str  # bound local name
    fromlist: bool  # True if `from ... import ...`


@dataclass(frozen=True)
class DynamicImport:
    """A runtime import call — a strong signal of a plugin-loading seam.

    e.g. importlib.import_module(...), __import__(...), pkgutil.iter_modules(...),
    or importlib.metadata.entry_points(...).
    """

    kind: str  # "import_module" | "__import__" | "iter_modules" | "entry_points"
    lineno: int
    # The literal argument if it was a constant string, else None (dynamic).
    argument: str | None = None


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    lineno: int
    is_public: bool
    decorators: tuple[str, ...] = ()
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClassInfo:
    name: str
    lineno: int
    is_public: bool
    bases: tuple[str, ...] = ()  # dotted base names as written
    decorators: tuple[str, ...] = ()
    methods: tuple[FunctionInfo, ...] = ()
    is_abstract: bool = False  # inherits ABC / uses @abstractmethod


@dataclass
class ModuleInfo:
    """One parsed .py file."""

    qualname: str  # dotted module path relative to scan root, e.g. "pkg.sub.mod"
    path: str  # filesystem path
    imports: list[ImportInfo] = field(default_factory=list)
    dynamic_imports: list[DynamicImport] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    all_exports: tuple[str, ...] | None = None  # value of __all__ if defined
    parse_error: str | None = None  # set if the file failed to parse

    @property
    def public_functions(self) -> list[FunctionInfo]:
        return [f for f in self.functions if self._exported(f.name, f.is_public)]

    @property
    def public_classes(self) -> list[ClassInfo]:
        return [c for c in self.classes if self._exported(c.name, c.is_public)]

    def _exported(self, name: str, is_public: bool) -> bool:
        # __all__ is authoritative when present; otherwise underscore convention.
        if self.all_exports is not None:
            return name in self.all_exports
        return is_public


@dataclass
class Codebase:
    """Whole scanned tree."""

    root: str
    modules: list[ModuleInfo] = field(default_factory=list)

    @property
    def ok_modules(self) -> list[ModuleInfo]:
        return [m for m in self.modules if m.parse_error is None]

    @property
    def failed_modules(self) -> list[ModuleInfo]:
        return [m for m in self.modules if m.parse_error is not None]
