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

"""Layer 2: extension graph.

Aggregates the per-module facts from layer 1 into a codebase-wide view:
  * a module dependency graph (which internal modules import which), and
  * a flat seam inventory (public functions/classes, subclassable/abstract
    classes, and dynamic-import sites) that layer 3 will rank for moddability.

Still deterministic — no LLM. Function-level call resolution is intentionally
out of scope here.
ponytail: module-level dependency edges only; per-function call graph deferred
until a detector actually needs it (name resolution across scopes is a lot of
code for value we can't yet use).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modscan.models import Codebase, DynamicImport


@dataclass(frozen=True)
class Seam:
    """A single candidate extension point, flattened across the codebase."""

    kind: str  # "function" | "class" | "abstract_class" | "dynamic_import"
    module: str  # owning module qualname
    name: str  # symbol name (or dynamic-import kind)
    lineno: int
    detail: str = ""  # bases for classes, decorators, dynamic arg, etc.


@dataclass
class ExtensionGraph:
    root: str
    # module qualname -> set of internal module qualnames it imports
    dependencies: dict[str, set[str]] = field(default_factory=dict)
    seams: list[Seam] = field(default_factory=list)

    @property
    def dynamic_import_sites(self) -> list[Seam]:
        return [s for s in self.seams if s.kind == "dynamic_import"]

    @property
    def subclassable(self) -> list[Seam]:
        return [s for s in self.seams if s.kind == "abstract_class"]


def _resolve_internal(imp_module: str, known: set[str]) -> str | None:
    """Best-effort map an imported module string to a known internal qualname.

    Handles exact matches and dotted prefixes. Relative imports (leading dots)
    are matched by suffix, which is coarse but good enough for a dependency view.
    ponytail: no full package-relative resolution; suffix match covers the common
    case, tighten if a detector needs precise edges.
    """
    name = imp_module.lstrip(".")
    if not name:
        return None
    if name in known:
        return name
    # `from pkg.sub import mod` where "pkg.sub.mod" is internal
    for k in known:
        if k == name or k.endswith("." + name) or k.startswith(name + "."):
            return k
    return None


def _dynamic_detail(d: DynamicImport) -> str:
    return f"{d.kind}({d.argument!r})" if d.argument else d.kind


def build_graph(codebase: Codebase) -> ExtensionGraph:
    graph = ExtensionGraph(root=codebase.root)
    known = {m.qualname for m in codebase.ok_modules if m.qualname}

    for mod in codebase.ok_modules:
        # dependency edges
        edges: set[str] = set()
        for imp in mod.imports:
            target = _resolve_internal(imp.module, known)
            if target and target != mod.qualname:
                edges.add(target)
        graph.dependencies[mod.qualname] = edges

        # seams: public functions
        for fn in mod.public_functions:
            deco = ",".join(fn.decorators)
            graph.seams.append(
                Seam("function", mod.qualname, fn.name, fn.lineno, detail=deco)
            )
        # seams: public classes (abstract ones flagged separately as subclassable)
        for cls in mod.public_classes:
            kind = "abstract_class" if cls.is_abstract else "class"
            graph.seams.append(
                Seam(kind, mod.qualname, cls.name, cls.lineno, detail=",".join(cls.bases))
            )
        # seams: dynamic-import sites
        for dyn in mod.dynamic_imports:
            graph.seams.append(
                Seam("dynamic_import", mod.qualname, dyn.kind, dyn.lineno, detail=_dynamic_detail(dyn))
            )

    return graph
