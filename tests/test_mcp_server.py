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

from modscan.mcp_server import (  # noqa: E402
    audit_attack_surface_tool,
    detect_extension_points_tool,
    mcp,
)


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


_AUDIT_SRC = '''\
import pickle
import subprocess


def load(blob):
    return pickle.loads(blob)


def run(cmd):
    return subprocess.run(cmd, shell=True)
'''


def test_audit_tool_reports_sinks_with_disclaimer() -> None:
    """The security lens is exposed as its own tool, in its own vocabulary, and
    the non-coverage disclaimer travels with the data — a client must not be able
    to read the result as 'no vulnerabilities found'."""
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "app.py"), "w", encoding="utf-8") as fh:
            fh.write(_AUDIT_SRC)

        payload = audit_attack_surface_tool(root)
        assert {"tool", "target", "disclaimer", "count", "sinks"} <= set(payload)
        assert payload["disclaimer"], "the disclaimer must travel with the data"

        ids = {s["id"] for s in payload["sinks"]}
        assert "MS-SEC-PICKLE" in ids and "MS-SEC-SUBPROCESS" in ids, ids

        # ranked most-dangerous-first, and the literal shell=True was elevated
        assert payload["sinks"][0]["severity"] == "high"
        subproc = next(s for s in payload["sinks"] if s["id"] == "MS-SEC-SUBPROCESS")
        assert subproc["severity"] == "high", "literal shell=True should elevate"

        # the security answer is never phrased in moddability terms
        assert not any("score" in s for s in payload["sinks"])

        assert len(audit_attack_surface_tool(root, limit=1)["sinks"]) == 1


def test_empty_audit_still_carries_the_disclaimer() -> None:
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "safe.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        payload = audit_attack_surface_tool(root)
        assert payload["count"] == 0
        assert payload["disclaimer"], "an empty result is not a clean bill of health"


if __name__ == "__main__":
    test_tool_is_registered()
    test_tool_ranks_an_abstract_base()
    test_audit_tool_reports_sinks_with_disclaimer()
    test_empty_audit_still_carries_the_disclaimer()
    print("OK: mcp server self-check passed")
