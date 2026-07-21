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

"""Layer 3: extension-point detector + moddability ranking.

Takes the flat seam inventory from the extension graph and scores each seam for
how likely it is to be a real, intended extension point a modder would hook
into. Scoring is a transparent sum of named signals — every point of the score
is explainable, which matters because layer 4 (docs) must be grounded.

Still deterministic. Heuristics only; no LLM. False positives are expected and
acceptable at this layer — the ranking pushes the strong candidates to the top,
and layer 5 (validator) is what ultimately confirms a seam is real.
"""

from __future__ import annotations

from modscan.graph import ExtensionGraph
from modscan.models import ExtensionPoint, Seam

# --- signal weights (0..1 contributions, summed then clamped) ---------------
_W_DYNAMIC_IMPORT = 0.9  # runtime import = plugin loader, strongest single signal
_W_ABSTRACT = 0.6  # ABC / abstractmethod = designed to be subclassed
_W_NAME_HOOK = 0.5  # register_/on_/hook_/subscribe... in a function name
_W_NAME_CLASS_ROLE = 0.45  # *Plugin / *Handler / *Backend... class name
_W_REGISTRATION_DECORATOR = 0.4  # decorated with a register/hook-looking decorator
_W_REEXPORT = 0.7  # re-exported from the package's public entry point (top-level __init__)
_W_OVERRIDE_POINT = 0.3  # a method raises NotImplementedError = subclass-and-implement base
_W_PUBLIC_BASELINE = 0.1  # merely being public API

# Function-name prefixes/substrings that signal a hook or registration seam.
_HOOK_NAME_PARTS = (
    "register", "unregister", "add_", "on_", "hook", "subscribe", "listen",
    "connect", "emit", "dispatch", "plugin", "extend", "handler", "callback",
)
# Class-name suffixes that signal a role meant to be implemented/subclassed.
# Includes common JS/TS role suffixes (Component, Service, ...) alongside the
# language-agnostic ones.
_CLASS_ROLE_SUFFIXES = (
    "Plugin", "Hook", "Extension", "Handler", "Listener", "Middleware",
    "Backend", "Provider", "Adapter", "Driver", "Strategy", "Base",
    "Component", "Service", "Controller", "Module", "Directive", "Store",
    "Reducer",
)
# Decorator names that look like registration.
_REGISTRATION_DECORATOR_PARTS = (
    "register", "hook", "on_", "subscribe", "plugin", "command", "route", "listener",
)

_SCORE_MAX = 1.0


def _name_hook_part(name: str) -> str | None:
    low = name.lower()
    for part in _HOOK_NAME_PARTS:
        if low.startswith(part) or part in low:
            return part
    return None


def _class_role_suffix(name: str) -> str | None:
    # An exact match ("Plugin", "Handler") is itself a role type, so no
    # `name != suffix` guard — a class or base named exactly for its role counts.
    for suffix in _CLASS_ROLE_SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return None


def _registration_decorator(decorators: str) -> str | None:
    low = decorators.lower()
    for part in _REGISTRATION_DECORATOR_PARTS:
        if part in low:
            return part
    return None


def _score_dynamic_import(seam: Seam) -> ExtensionPoint:
    # The builtin __import__ is a general-purpose reflection / lazy-import
    # primitive, not a plugin-discovery mechanism like entry_points or
    # import_string. Ranking it as a top plugin_loader floods the output of any
    # package that lazy-loads its own submodules (e.g. pygments' lexer registry).
    # It stays detected — only its score drops to weak, ambiguous evidence.
    if seam.name == "__import__":
        return ExtensionPoint(
            seam=seam,
            category="reflection",
            score=_W_PUBLIC_BASELINE,
            signals=("builtin __import__ — reflection/lazy import, not a plugin mechanism",),
        )
    return ExtensionPoint(
        seam=seam,
        category="plugin_loader",
        score=_W_DYNAMIC_IMPORT,
        signals=(f"runtime import ({seam.detail or seam.name}) — plugin-loading seam",),
    )


def _score_class(seam: Seam) -> ExtensionPoint:
    score = _W_PUBLIC_BASELINE
    signals = ["public class"]

    if seam.kind == "abstract_class":
        score += _W_ABSTRACT
        signals.append("abstract (ABC / @abstractmethod) — meant to be subclassed")

    suffix = _class_role_suffix(seam.name)
    if suffix:
        score += _W_NAME_CLASS_ROLE
        signals.append(f"name ends in '{suffix}' — role type")

    # For classes, seam.detail holds bases (not decorators); a base matching a
    # role suffix hints the class implements an extension interface.
    role_base = None
    for base in seam.detail.split(","):
        role_base = _class_role_suffix(base.strip())
        if role_base:
            break
    if role_base:
        score += _W_NAME_CLASS_ROLE
        signals.append(f"subclasses a '{role_base}' role type")

    if seam.reexported:
        score += _W_REEXPORT
        signals.append("re-exported from the package's public entry point")

    if seam.has_override_point:
        score += _W_OVERRIDE_POINT
        signals.append("defines an override point (raises NotImplementedError)")

    category = (
        "subclass"
        if (seam.kind == "abstract_class" or suffix or role_base or seam.has_override_point)
        else "api"
    )
    return ExtensionPoint(seam, category, min(score, _SCORE_MAX), tuple(signals))


def _score_function(seam: Seam) -> ExtensionPoint:
    score = _W_PUBLIC_BASELINE
    signals = ["public function"]
    category = "api"

    part = _name_hook_part(seam.name)
    if part:
        score += _W_NAME_HOOK
        signals.append(f"name matches hook/registration pattern ('{part}')")
        category = "hook" if part in ("on_", "hook", "emit", "dispatch", "listen") else "registration"

    deco = _registration_decorator(seam.detail)
    if deco:
        score += _W_REGISTRATION_DECORATOR
        signals.append(f"registration-style decorator ('{deco}')")
        if category == "api":
            category = "registration"

    if seam.reexported:
        score += _W_REEXPORT
        signals.append("re-exported from the package's public entry point")

    return ExtensionPoint(seam, category, min(score, _SCORE_MAX), tuple(signals))


def _score_seam(seam: Seam) -> ExtensionPoint:
    if seam.kind == "dynamic_import":
        return _score_dynamic_import(seam)
    if seam.kind in ("class", "abstract_class"):
        return _score_class(seam)
    return _score_function(seam)


def detect_extension_points(
    graph: ExtensionGraph, min_score: float = 0.0
) -> list[ExtensionPoint]:
    """Score every seam and return extension points sorted most-moddable first.

    `min_score` filters out weak candidates (e.g. plain public API with no other
    signal scores only the public baseline).
    """
    points = [_score_seam(s) for s in graph.seams]
    points = [p for p in points if p.score >= min_score]
    # Stable, deterministic order: score desc, then location for ties.
    points.sort(key=lambda p: (-p.score, p.seam.module, p.seam.lineno))
    return points
