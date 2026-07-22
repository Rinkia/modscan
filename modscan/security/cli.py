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

"""`modscan-audit` — the security lens's own command.

A sibling entry point, separate from `modscan`, so the security framing never
mixes with the moddability UX. Offline and free: it runs the parser + sink
detector, never the LLM. It is a report, not a gate — it exits 0 whatever it
finds (an attack-surface map is informational; the reviewer decides).
"""

from __future__ import annotations

import argparse
import os
import sys

from modscan.security.detect import find_risk_sinks
from modscan.security.report import render_json, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modscan-audit",
        description="Map a Python codebase's attack surface — where untrusted code "
        "or data can enter and execute. Enumeration only: no taint, CVEs, or secrets.",
    )
    parser.add_argument("root", help="path to the source tree to scan")
    parser.add_argument(
        "--json", action="store_true", help="machine-readable JSON instead of Markdown"
    )
    parser.add_argument(
        "--label",
        default=None,
        help="name shown in the report header (default: the directory basename; "
        "never the full scan path)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="directory path to skip (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.root):
        print(f"error: not a directory: {args.root}", file=sys.stderr)
        return 2
    # The report uses em-dashes; a Windows cp1252 console would crash on them.
    # Force UTF-8 stdout, as the moddability CLI does.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    sinks = find_risk_sinks(args.root, exclude=tuple(args.exclude))
    label = args.label or os.path.basename(os.path.abspath(args.root))
    report = render_json(sinks, label) if args.json else render_markdown(sinks, label)
    print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
