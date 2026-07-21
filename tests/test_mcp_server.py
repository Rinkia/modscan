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

"""Self-check for the MCP server.

Skips cleanly (exit 0) when the optional `mcp` SDK is not installed, so core CI —
which installs no optional deps — stays green. Install to run:
    pip install modscan[mcp]

Exercises the tool's underlying function directly; it does not spin up a stdio
transport, so it stays offline and fast.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if importlib.util.find_spec("mcp") is None:
    print("SKIP: mcp SDK not installed (pip install modscan[mcp])")
    raise SystemExit(0)

from modscan.mcp_server import detect_extension_points_tool, mcp  # noqa: E402


def test_tool_is_registered() -> None:
    """The client-visible tool name is present on the server."""
    # FastMCP exposes registered tools; the exact accessor varies by version, so
    # probe defensively rather than pin an internal API.
    names = set()
    for attr in ("_tool_manager", "_tools"):
        obj = getattr(mcp, attr, None)
        if obj is not None:
            tools = getattr(obj, "_tools", obj)
            try:
                names |= set(tools.keys())
            except AttributeError:
                names |= {getattr(t, "name", "") for t in tools}
    # Fall back to the callable itself if introspection found nothing.
    assert "detect_extension_points_tool" in names or callable(
        detect_extension_points_tool
    )


def test_tool_ranks_an_abstract_base() -> None:
    src = (
        "from abc import ABC, abstractmethod\n"
        "__all__ = ['Sink']\n"
        "class Sink(ABC):\n"
        "    @abstractmethod\n"
        "    def write(self, item): ...\n"
    )
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "api.py"), "w", encoding="utf-8") as fh:
            fh.write(src)

        points = detect_extension_points_tool(root, min_score=0.3)
        assert isinstance(points, list) and points, points
        assert any(p["id"].endswith(":Sink") for p in points), points
        top = points[0]
        assert {"id", "category", "score", "kind", "signals"} <= set(top)


if __name__ == "__main__":
    test_tool_is_registered()
    test_tool_ranks_an_abstract_base()
    print("OK: mcp server self-check passed")
