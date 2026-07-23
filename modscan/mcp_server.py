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

"""MCP server exposing MODScan's static extension-point detection as a tool.

Lets an AI client (Claude Desktop, Cursor, …) answer "what are the extension
points of this codebase?" without leaving the conversation. Only the offline,
no-LLM, no-code-execution path is exposed — the detector, not the full docgen
pipeline — so the tool is safe to run against any local checkout.

    pip install modscan[mcp]
    modscan-mcp                     # stdio server

Register it with a client by pointing at the `modscan-mcp` command. Two tools are
exposed, both offline: `detect_extension_points` ranks a codebase's extension
points, and `audit_attack_surface` maps where untrusted code can enter and
execute. They keep their own vocabulary — moddability and attack surface are
different questions, and neither answer is phrased in the other's terms.
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from modscan.detector import detect_extension_points
from modscan.graph import build_graph
from modscan.languages import get_language_parser
from modscan.security.detect import find_risk_sinks
from modscan.security.report import render_json

mcp = FastMCP("modscan")


@mcp.tool()
def detect_extension_points_tool(
    path: str,
    language: str = "python",
    min_score: float = 0.0,
    limit: int | None = None,
) -> list[dict]:
    """Rank a codebase's extension points by static analysis. No LLM, no code execution.

    Args:
        path: filesystem path to the source tree to scan.
        language: python (default), typescript, or javascript.
        min_score: minimum moddability score to include (0..1).
        limit: return only the top N points, or None for all.

    Returns:
        A list of points, most-moddable first, each with its id
        (``module:Symbol``), category, score, kind and the signals behind it.
    """
    codebase = get_language_parser(language).parse_codebase(path)
    points = detect_extension_points(build_graph(codebase), min_score=min_score)
    if limit is not None:
        points = points[:limit]
    return [
        {
            "id": f"{p.seam.module or path}:{p.seam.name}",
            "category": p.category,
            "score": round(p.score, 4),
            "kind": p.seam.kind,
            "signals": list(p.signals),
        }
        for p in points
    ]


@mcp.tool()
def audit_attack_surface_tool(
    path: str,
    language: str = "python",
    limit: int | None = None,
) -> dict:
    """Map where untrusted code or data can enter and execute. No LLM, no code execution.

    This is an attack-surface map, NOT a vulnerability scan: it locates execution
    sinks (eval/exec, pickle/marshal/yaml deserialization, os.system/subprocess,
    dynamic loaders) but does not trace whether input reaches them, match CVEs, or
    detect secrets. An empty result is not a clean bill of health.

    Args:
        path: filesystem path to the source tree to scan.
        language: python (default), typescript, or javascript.
        limit: return only the top N sinks, or None for all.

    Returns:
        The same payload `modscan-audit --json` emits — the sinks ranked
        most-dangerous-first by severity then confidence, each with its stable
        MS-SEC id, category and location, alongside the non-coverage disclaimer.
    """
    # Built through the CLI's own renderer so this tool and `modscan-audit --json`
    # cannot drift apart — in particular so the disclaimer travels with the data.
    payload = json.loads(
        render_json(find_risk_sinks(path, language=language), os.path.basename(os.path.abspath(path)))
    )
    if limit is not None:
        payload["sinks"] = payload["sinks"][:limit]
    return payload


def main() -> None:
    """Console-script entry point: run the stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
