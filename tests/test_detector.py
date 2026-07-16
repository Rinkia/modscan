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
from modscan.detector import detect_extension_points  # noqa: E402
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


if __name__ == "__main__":
    test_detector_ranking()
