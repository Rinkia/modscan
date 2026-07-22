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

"""Self-check for layer 3 (extension-point detector + ranking).

Runs without pytest: `python tests/test_detector.py`. Reuses the synthetic
plugin package from test_parser and asserts the ranking puts real extension
points on top and weak public API at the bottom.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.parser import parse_codebase  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.detector import (  # noqa: E402
    SIGNAL_CATALOG,
    detect_extension_points,
)
from tests.test_parser import FIXTURE, _write_fixture  # noqa: E402


def test_detector_ranking() -> None:
    with tempfile.TemporaryDirectory() as root:
        _write_fixture(root)
        cb = parse_codebase(root)
        graph = build_graph(cb)
        points = detect_extension_points(graph)

        by_name = {(p.seam.module, p.seam.name): p for p in points}

        # dynamic import (load -> importlib.import_module) is the top signal
        loaders = [p for p in points if p.category == "plugin_loader"]
        assert loaders, "expected a plugin_loader extension point"
        assert loaders[0].score >= 0.9

        # abstract Plugin is a subclass extension point, scored well
        plugin = by_name[("pkg.core", "Plugin")]
        assert plugin.category == "subclass"
        assert plugin.score >= 0.6
        assert any("abstract" in s for s in plugin.signals)

        # register() function flagged as registration via name
        register = by_name[("pkg.core", "register")]
        assert register.category == "registration"
        assert register.score > 0.1

        # Greeter subclasses Plugin (role base) -> subclass category
        greeter = by_name[("pkg.plugins", "Greeter")]
        assert greeter.category == "subclass"

        # ranking is sorted: scores non-increasing
        scores = [p.score for p in points]
        assert scores == sorted(scores, reverse=True)

        # min_score filter drops the weakest candidate(s)
        low = min(p.score for p in points)
        strong = detect_extension_points(graph, min_score=low + 0.01)
        assert all(p.score >= low + 0.01 for p in strong)
        assert len(strong) < len(points)

    print("OK: detector ranking self-check passed")


def test_reexport_signal_lifts_a_floor_seam() -> None:
    """A symbol re-exported from the package root outranks an identical one that
    is not. This is the whole point of the public-API re-export signal: two
    classes with no other distinguishing signal are separated only by whether the
    maintainer put them in the public entry point.
    """
    # Mirror how MODScan is actually pointed at a package: the scan root IS the
    # package directory, so its __init__ is the top-level entry point.
    fixture = {
        "__init__.py": "from public import Exposed\n__all__ = ['Exposed']\n",
        "public.py": "class Exposed:\n    pass\n",
        "internal.py": "class Hidden:\n    pass\n",
    }
    with tempfile.TemporaryDirectory() as root:
        for rel, content in fixture.items():
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write(content)

        points = detect_extension_points(build_graph(parse_codebase(root)))
        by_name = {(p.seam.module, p.seam.name): p for p in points}

        exposed = by_name[("public", "Exposed")]
        hidden = by_name[("internal", "Hidden")]

        assert exposed.seam.reexported, "Exposed is re-exported from lib/__init__.py"
        assert not hidden.seam.reexported, "Hidden is never re-exported"
        assert exposed.score > hidden.score, "re-export must lift the score"
        assert any("re-exported" in s for s in exposed.signals)
        # and the ranking reflects it
        assert points.index(exposed) < points.index(hidden)


def test_reexport_fires_when_scanning_a_parent_directory() -> None:
    """Re-export must fire whether MODScan is pointed at the package or its parent.

    Pointing at a parent (``repo/`` containing ``repo/pkg/``) is what a real
    checkout looks like and what the validator needs — fully-qualified qualnames
    (``pkg.public``) are what ``import`` can resolve. The signal keys off
    filesystem structure, not a qualname of "", so it must still fire here.
    """
    with tempfile.TemporaryDirectory() as parent:
        pkg = os.path.join(parent, "pkg")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write("from pkg.public import Exposed\n__all__ = ['Exposed']\n")
        with open(os.path.join(pkg, "public.py"), "w", encoding="utf-8") as fh:
            fh.write("class Exposed:\n    pass\n")
        with open(os.path.join(pkg, "internal.py"), "w", encoding="utf-8") as fh:
            fh.write("class Hidden:\n    pass\n")

        points = detect_extension_points(build_graph(parse_codebase(parent)))
        by_name = {p.seam.name: p for p in points}
        # qualnames are fully qualified (importable), and re-export still fires
        assert by_name["Exposed"].seam.module == "pkg.public"
        assert by_name["Exposed"].seam.reexported
        assert not by_name["Hidden"].seam.reexported
        assert by_name["Exposed"].score > by_name["Hidden"].score

    print("OK: re-export signal self-check passed")


def test_override_point_breaks_a_reexport_tie() -> None:
    """Two re-exported classes, identical but for an override point, must not tie:
    the one with a method raising NotImplementedError outranks the other. This is
    the discriminator that separates a subclass-me base from a concrete class that
    merely happens to be in the public API.
    """
    fixture = {
        "__init__.py": "from mod import Base, Plain\n__all__ = ['Base', 'Plain']\n",
        "mod.py": (
            "class Base:\n"
            "    def convert(self, v):\n"
            "        raise NotImplementedError\n"
            "class Plain:\n"
            "    def convert(self, v):\n"
            "        return v\n"
        ),
    }
    with tempfile.TemporaryDirectory() as root:
        for rel, content in fixture.items():
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write(content)

        points = detect_extension_points(build_graph(parse_codebase(root)))
        by_name = {(p.seam.module, p.seam.name): p for p in points}
        base = by_name[("mod", "Base")]
        plain = by_name[("mod", "Plain")]

        assert base.seam.reexported and plain.seam.reexported, "both are re-exported"
        assert base.seam.has_override_point and not plain.seam.has_override_point
        assert base.score > plain.score, "the override point must break the tie"
        assert base.category == "subclass"
        assert any("override point" in s for s in base.signals)
        assert points.index(base) < points.index(plain)

    print("OK: override-point tie-breaker self-check passed")


def test_import_builtin_scored_below_real_loaders() -> None:
    """builtin __import__ is reflection/lazy-import, not a plugin mechanism: it is
    detected but must not outrank a genuine loader like importlib.import_module.
    """
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "loaders.py"), "w", encoding="utf-8") as fh:
            fh.write(
                "import importlib\n"
                "def lazy(name):\n"
                "    return __import__(name)\n"
                "def load_plugin(name):\n"
                "    return importlib.import_module(name)\n"
            )
        points = detect_extension_points(build_graph(parse_codebase(root)))
        by_kind = {p.seam.name: p for p in points if p.seam.kind == "dynamic_import"}

        assert "__import__" in by_kind, "still detected"
        assert "import_module" in by_kind, "genuine loader detected"

        reflection = by_kind["__import__"]
        loader = by_kind["import_module"]
        assert reflection.category == "reflection"
        assert loader.category == "plugin_loader"
        assert reflection.score < loader.score, "reflection must rank below a real loader"
        assert points.index(loader) < points.index(reflection)

    print("OK: __import__ reflection self-check passed")


def test_signals_carry_stable_ids() -> None:
    """Every moddability signal is tagged with a stable catalog ID (Bandit-style),
    so a point's reasons are machine-referenceable. Presentation only — the IDs
    do not change the score (covered by the ranking tests above)."""
    # catalog integrity: all ids share the MS-MOD- namespace, none duplicated
    assert all(sid.startswith("MS-MOD-") for sid in SIGNAL_CATALOG)
    assert len(set(SIGNAL_CATALOG)) == len(SIGNAL_CATALOG)

    with tempfile.TemporaryDirectory() as root:
        pkg = os.path.join(root, "lib")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write("from .api import Base\n")
        with open(os.path.join(pkg, "api.py"), "w", encoding="utf-8") as fh:
            fh.write("from abc import ABC, abstractmethod\n\n\n"
                     "class Base(ABC):\n    @abstractmethod\n    def run(self): ...\n")
        points = detect_extension_points(build_graph(parse_codebase(root)))
        base = next(p for p in points if p.seam.name == "Base")
        # every reason on the point is prefixed with a bracketed catalog id
        assert base.signals, "expected signals on the abstract base"
        for reason in base.signals:
            assert reason.startswith("[MS-MOD-"), reason
        assert any("[MS-MOD-ABSTRACT]" in s for s in base.signals)
        assert any("[MS-MOD-REEXPORT]" in s for s in base.signals)
    print("OK: signal stable-id self-check passed")


if __name__ == "__main__":
    test_detector_ranking()
    test_reexport_signal_lifts_a_floor_seam()
    test_reexport_fires_when_scanning_a_parent_directory()
    test_override_point_breaks_a_reexport_tie()
    test_import_builtin_scored_below_real_loaders()
    test_signals_carry_stable_ids()
