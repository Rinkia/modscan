"""Self-check for layer 5 (validator).

Runs without pytest: `python tests/test_validator.py`. Builds its own tiny
package (unique name to avoid sys.modules collisions with other tests), scans
it, then validates the detected extension points against the real, imported
code — the loop-closing check.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.parser import parse_codebase  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.detector import detect_extension_points  # noqa: E402
from modscan.validator import validate_points, validate_point  # noqa: E402

# Unique top package name so importing it never clashes with other test fixtures.
FIXTURE = {
    "vfix/__init__.py": "",
    "vfix/api.py": (
        "from abc import ABC, abstractmethod\n"
        "\n"
        "__all__ = ['Backend', 'NeedsArg', 'register']\n"
        "\n"
        "class Backend(ABC):\n"
        "    @abstractmethod\n"
        "    def handle(self, event):\n"
        "        ...\n"
        "\n"
        "class NeedsArg(Backend):\n"
        "    def __init__(self, required):\n"  # can't instantiate without arg
        "        self.required = required\n"
        "    def handle(self, event):\n"
        "        return event\n"
        "\n"
        "def register(fn):\n"
        "    return fn\n"
    ),
}


def _write(root: str) -> None:
    for rel, content in FIXTURE.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def _cleanup_imported() -> None:
    for name in list(sys.modules):
        if name == "vfix" or name.startswith("vfix."):
            del sys.modules[name]


def test_validator() -> None:
    with tempfile.TemporaryDirectory() as root:
        _write(root)
        try:
            cb = parse_codebase(root)
            points = detect_extension_points(build_graph(cb))
            by_name = {(p.seam.module, p.seam.name): p for p in points}

            # Backend: abstract subclass seam -> probe subclass instantiates OK
            backend = by_name[("vfix.api", "Backend")]
            res = validate_point(root, backend)
            assert res.ok is True, res.detail
            assert res.method == "subclass_instantiation"
            assert "abstract" in res.detail

            # NeedsArg: concrete but __init__ requires an arg -> fails gracefully
            needsarg = by_name[("vfix.api", "NeedsArg")]
            res = validate_point(root, needsarg)
            assert res.ok is False
            assert res.method == "error"
            assert "instantiate" in res.detail

            # register: registration/api seam -> importable & callable
            register = by_name[("vfix.api", "register")]
            res = validate_point(root, register)
            assert res.ok is True, res.detail
            assert res.method == "importable_callable"

            # batch API respects limit and preserves order
            results = validate_points(root, points, limit=2)
            assert len(results) == 2
            assert [r.point.seam.name for r in results] == [
                p.seam.name for p in points[:2]
            ]
        finally:
            _cleanup_imported()

    print("OK: validator self-check passed")


if __name__ == "__main__":
    test_validator()
