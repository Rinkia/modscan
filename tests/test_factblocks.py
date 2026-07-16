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

"""Self-check for fact blocks — the point -> rich-model join."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.parser import parse_codebase  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.detector import detect_extension_points  # noqa: E402
from modscan.factblocks import build_fact_block, render_fact_block  # noqa: E402

SRC = (
    "from abc import ABC, abstractmethod\n"
    "\n"
    "__all__ = ['Exporter', 'register']\n"
    "\n"
    "class Exporter(ABC):\n"
    "    @abstractmethod\n"
    "    def export(self, data, fmt):\n"
    "        ...\n"
    "    @abstractmethod\n"
    "    def name(self):\n"
    "        ...\n"
    "    def helper(self):\n"  # concrete, not required to implement
    "        return 1\n"
    "\n"
    "def register(fn):\n"
    "    return fn\n"
)


def test_factblocks() -> None:
    with tempfile.TemporaryDirectory() as root:
        pkg = os.path.join(root, "fb")
        os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").close()
        with open(os.path.join(pkg, "plug.py"), "w", encoding="utf-8") as fh:
            fh.write(SRC)

        cb = parse_codebase(root)
        points = {
            (p.seam.module, p.seam.name): p
            for p in detect_extension_points(build_graph(cb))
        }

        # abstract class -> implement lists both @abstractmethod signatures, not helper
        exporter = points[("fb.plug", "Exporter")]
        fb = build_fact_block(cb, exporter, validation_method="subclass_instantiation")
        assert fb.point_id == "fb.plug:Exporter"
        assert fb.signature == "class Exporter(ABC)"
        assert "def export(self, data, fmt)" in fb.implement
        assert "def name(self)" in fb.implement
        assert not any("helper" in s for s in fb.implement)
        assert fb.validation_method == "subclass_instantiation"

        # function fact block carries its signature
        reg = build_fact_block(cb, points[("fb.plug", "register")])
        assert reg.signature == "def register(fn)"

        # rendered block is facts-only: no raw source lines like 'return 1' or '...'
        text = render_fact_block(fb)
        assert "must implement:" in text
        # facts-only: method bodies never appear (no source paraphrasing risk)
        assert "return 1" not in text
        assert "..." not in text

    print("OK: factblocks self-check passed")


if __name__ == "__main__":
    test_factblocks()
