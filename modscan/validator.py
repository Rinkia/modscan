"""Layer 5: validator — close the loop by loading a plugin against a seam.

A detected extension point is only a hypothesis until something actually hooks
into it. This layer takes an ExtensionPoint, builds a minimal probe plugin
(e.g. a concrete subclass of an abstract seam), imports the target, and confirms
the probe loads — instantiates, or is importable and callable. If it does, the
seam is real and the docs generated for it (layer 4) can be trusted.

SECURITY / TRUST BOUNDARY
-------------------------
Validation IMPORTS the target codebase, which executes its module-level code.
Only run it on code you trust. It is a deliberate, explicit call — never invoked
automatically by parsing/scanning. Do not point it at untrusted third-party
source.
ponytail: in-process import, no sandbox. A subprocess/sandbox is the upgrade
path if MODScan ever validates untrusted code; out of scope for the MVP, which
targets source the operator already trusts.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from dataclasses import dataclass
from typing import Iterator

from modscan.detector import ExtensionPoint


@dataclass(frozen=True)
class ValidationResult:
    point: ExtensionPoint
    ok: bool
    method: str  # "subclass_instantiation" | "importable_callable" | "error" | "skipped"
    detail: str  # what happened, or the error message

    @property
    def location(self) -> str:
        return self.point.location


@contextlib.contextmanager
def _sys_path(entry: str) -> Iterator[None]:
    """Temporarily prepend `entry` to sys.path so target modules import."""
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(entry)


def _load_symbol(root: str, module_qualname: str, name: str):
    """Import the target module and return the named attribute.

    Raises on import failure or missing attribute; callers translate that into a
    failed ValidationResult rather than letting it propagate.
    """
    with _sys_path(root):
        module = importlib.import_module(module_qualname)
    return getattr(module, name)


def _validate_subclass(root: str, point: ExtensionPoint) -> ValidationResult:
    """Build a concrete subclass implementing all abstract methods, instantiate it."""
    try:
        cls = _load_symbol(root, point.seam.module, point.seam.name)
    except Exception as exc:  # noqa: BLE001 — import of target can fail many ways
        return ValidationResult(point, False, "error", f"import failed: {exc!r}")

    if not isinstance(cls, type):
        return ValidationResult(point, False, "error", f"{point.seam.name} is not a class")

    abstract = getattr(cls, "__abstractmethods__", frozenset())
    # Stub out every abstract method so the subclass is concrete.
    namespace = {m: (lambda self, *a, **k: None) for m in abstract}
    probe = type(f"_ModScanProbe_{cls.__name__}", (cls,), namespace)

    try:
        probe()  # raises TypeError if still abstract, or if __init__ needs args
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(
            point, False, "error", f"subclass did not instantiate: {exc!r}"
        )
    return ValidationResult(
        point,
        True,
        "subclass_instantiation",
        f"probe subclass of {point.seam.name} instantiated"
        + (f" (stubbed {len(abstract)} abstract method(s))" if abstract else ""),
    )


def _validate_importable(root: str, point: ExtensionPoint) -> ValidationResult:
    """Weakest check: the seam symbol imports and is callable/usable.

    No side-effectful call — we confirm the hook exists and is reachable, not
    that invoking it works (that needs real arguments the tool can't invent).
    """
    try:
        obj = _load_symbol(root, point.seam.module, point.seam.name)
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(point, False, "error", f"import failed: {exc!r}")

    if callable(obj):
        return ValidationResult(
            point, True, "importable_callable", f"{point.seam.name} imports and is callable"
        )
    return ValidationResult(
        point, False, "error", f"{point.seam.name} imports but is not callable"
    )


def validate_point(root: str, point: ExtensionPoint) -> ValidationResult:
    """Validate one extension point against the real target code.

    `root` is the scan root (added to sys.path so target modules import).
    Dispatches by category: subclass seams get an instantiation probe; hook /
    registration / api seams get the lighter importable-callable check;
    plugin_loader (dynamic import) sites are skipped — validating them needs a
    real plugin-discovery run, which is future work.
    """
    if point.category == "subclass":
        return _validate_subclass(root, point)
    if point.category == "plugin_loader":
        return ValidationResult(
            point, False, "skipped", "plugin_loader validation not implemented yet"
        )
    return _validate_importable(root, point)


def validate_points(
    root: str, points: list[ExtensionPoint], limit: int | None = None
) -> list[ValidationResult]:
    """Validate an ordered list of extension points (already ranked by detector).

    `limit` caps how many are validated (they arrive most-moddable first).
    """
    chosen = points[:limit] if limit is not None else points
    return [validate_point(root, p) for p in chosen]
