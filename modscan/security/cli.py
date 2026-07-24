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
detector, never the LLM.

Scanning is always a report — an attack-surface map is informational and exits 0
whatever it finds. Only `--diff` can fail, and only when explicitly asked with
`--fail-on`, which is how the CI gate turns "sinks were introduced" into a
failing check.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from modscan import __version__
from modscan.security.detect import find_risk_sinks
from modscan.security.report import render_json, render_markdown
from modscan.security.surface_diff import (
    FAIL_ON_CHOICES,
    diff_surfaces,
    introduced_at_or_above,
    render_surface_diff_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modscan-audit",
        description="Map a Python codebase's attack surface — where untrusted code "
        "or data can enter and execute. Enumeration only: no taint, CVEs, or secrets.",
    )
    parser.add_argument(
        "--version", action="version", version=f"modscan-audit {__version__}"
    )
    parser.add_argument(
        "root", nargs="?", help="path to the source tree to scan"
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("BASE", "PR"),
        help="compare two `--json` snapshots and report the execution sinks the "
        "second one introduces (line numbers are ignored, so moved code is not a "
        "change). Reports only unless --fail-on is given.",
    )
    parser.add_argument(
        "--fail-on",
        choices=FAIL_ON_CHOICES,
        default="none",
        help="with --diff, exit 1 when a sink of at least this severity is "
        "introduced (default: none — report only). 'high' is the recommended gate "
        "setting: the medium tier is mostly routine __reduce__/dynamic-import/"
        "subprocess code.",
    )
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
        "--language",
        choices=("python", "typescript", "javascript", "java"),
        default="python",
        help="source language of the tree to scan (default: python). "
        "typescript/javascript need pip install modscan[typescript]; "
        "java needs pip install modscan[java]",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="directory path to skip (repeatable)",
    )
    return parser


def _run_diff(paths: list[str], label: str | None, fail_on: str = "none") -> int:
    """Report the execution sinks the second snapshot introduces over the first.

    Returns 1 when `fail_on` is set and a sink at least that severe was
    introduced — the signal a CI gate keys off. Otherwise 0.
    """
    for path in paths:
        if not os.path.isfile(path):
            print(f"error: snapshot not found: {path}", file=sys.stderr)
            return 2
    try:
        with open(paths[0], encoding="utf-8") as fh:
            base = json.load(fh)
        with open(paths[1], encoding="utf-8") as fh:
            new = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"error: not a valid --json snapshot: {exc}", file=sys.stderr)
        return 2

    diff = diff_surfaces(base, new)
    shown = label or (new.get("target") if isinstance(new, dict) else None) or "target"
    print(render_surface_diff_markdown(diff, shown), end="")

    blocking = introduced_at_or_above(diff, fail_on)
    if blocking:
        print(
            f"error: {sum(c.count for c in blocking)} newly-introduced sink(s) at or "
            f"above severity '{fail_on}' — review before merging.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.diff and not args.root:
        print("error: provide a path to scan, or --diff BASE PR", file=sys.stderr)
        return 2

    # The report uses em-dashes; a Windows cp1252 console would crash on them.
    # Force UTF-8 stdout, as the moddability CLI does.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.diff:
        return _run_diff(args.diff, args.label, args.fail_on)

    if not os.path.isdir(args.root):
        print(f"error: not a directory: {args.root}", file=sys.stderr)
        return 2

    sinks = find_risk_sinks(args.root, exclude=tuple(args.exclude), language=args.language)
    label = args.label or os.path.basename(os.path.abspath(args.root))
    report = render_json(sinks, label) if args.json else render_markdown(sinks, label)
    print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
