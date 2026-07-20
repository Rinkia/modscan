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

"""Fact blocks — the grounding join between a detected point and the LLM.

A FactBlock is the ONLY thing the doc generator (layer 4) tells the model about
the target. It carries structured facts pulled straight from the parser model
(signature, base classes, decorators, abstract methods to implement) plus the
detector's signals and the validator's result — never raw free-form source. This
is what keeps generated docs grounded: the model describes these facts, it does
not read and paraphrase arbitrary code.
"""

from __future__ import annotations

from dataclasses import dataclass

from modscan.detector import ExtensionPoint
from modscan.models import ClassInfo, Codebase, FunctionInfo, ModuleInfo


@dataclass(frozen=True)
class FactBlock:
    module: str
    symbol: str
    kind: str  # "function" | "class" | "abstract_class" | "dynamic_import"
    category: str
    lineno: int
    signature: str  # rendered def line for functions; "class X(bases)" for classes
    bases: tuple[str, ...]
    decorators: tuple[str, ...]
    implement: tuple[str, ...]  # abstract method signatures a subclass must define
    signals: tuple[str, ...]  # why the detector flagged it
    validation_method: str  # how the validator confirmed it

    @property
    def point_id(self) -> str:
        return f"{self.module}:{self.symbol}"


def _render_func_sig(fn: FunctionInfo) -> str:
    return f"def {fn.name}({', '.join(fn.args)})"


def _is_abstract_method(fn: FunctionInfo) -> bool:
    return any("abstractmethod" in d for d in fn.decorators)


def build_module_index(codebase: Codebase) -> dict[str, ModuleInfo]:
    """Map qualname -> module once, so callers building many fact blocks do not
    re-scan the whole module list for each one (was O(points x modules))."""
    return {m.qualname: m for m in codebase.modules}


def _find_module(codebase: Codebase, qualname: str) -> ModuleInfo | None:
    for module in codebase.modules:
        if module.qualname == qualname:
            return module
    return None


def _class_facts(cls: ClassInfo) -> tuple[str, tuple[str, ...]]:
    """Return (signature line, abstract-method signatures to implement)."""
    sig = f"class {cls.name}({', '.join(cls.bases)})" if cls.bases else f"class {cls.name}"
    implement = tuple(
        _render_func_sig(m) for m in cls.methods if _is_abstract_method(m)
    )
    return sig, implement


def build_fact_block(
    codebase: Codebase,
    point: ExtensionPoint,
    validation_method: str = "",
    module_index: dict[str, ModuleInfo] | None = None,
) -> FactBlock:
    """Join an extension point back to the rich parser model into a FactBlock.

    Falls back to the lean seam data if the symbol can't be located (e.g. a
    dynamic-import site, which is a call, not a named definition).
    """
    seam = point.seam
    module = (
        module_index.get(seam.module)
        if module_index is not None
        else _find_module(codebase, seam.module)
    )

    signature = ""
    bases: tuple[str, ...] = ()
    decorators: tuple[str, ...] = ()
    implement: tuple[str, ...] = ()

    if module is not None and seam.kind in ("class", "abstract_class"):
        cls = next((c for c in module.classes if c.name == seam.name), None)
        if cls is not None:
            signature, implement = _class_facts(cls)
            bases = cls.bases
            decorators = cls.decorators
    elif module is not None and seam.kind == "function":
        fn = next((f for f in module.functions if f.name == seam.name), None)
        if fn is not None:
            signature = _render_func_sig(fn)
            decorators = fn.decorators

    return FactBlock(
        module=seam.module,
        symbol=seam.name,
        kind=seam.kind,
        category=point.category,
        lineno=seam.lineno,
        signature=signature,
        bases=bases,
        decorators=decorators,
        implement=implement,
        signals=point.signals,
        validation_method=validation_method,
    )


def render_fact_block(fb: FactBlock) -> str:
    """Render a FactBlock as compact text for an LLM prompt (facts only)."""
    lines = [
        f"module: {fb.module}",
        f"symbol: {fb.symbol}",
        f"kind: {fb.kind}",
        f"category: {fb.category}",
        f"location: {fb.module}:{fb.lineno}",
    ]
    if fb.signature:
        lines.append(f"signature: {fb.signature}")
    if fb.bases:
        lines.append(f"bases: {', '.join(fb.bases)}")
    if fb.decorators:
        lines.append(f"decorators: {', '.join(fb.decorators)}")
    if fb.implement:
        lines.append("must implement:")
        lines.extend(f"  - {sig}" for sig in fb.implement)
    if fb.signals:
        lines.append("detector signals:")
        lines.extend(f"  - {s}" for s in fb.signals)
    if fb.validation_method:
        lines.append(f"validated via: {fb.validation_method}")
    return "\n".join(lines)
