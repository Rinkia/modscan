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

Register it with a client by pointing at the `modscan-mcp` command. The one tool,
`detect_extension_points`, takes a filesystem path and returns the ranked points.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from modscan.detector import detect_extension_points
from modscan.graph import build_graph
from modscan.languages import get_language_parser

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


def main() -> None:
    """Console-script entry point: run the stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
