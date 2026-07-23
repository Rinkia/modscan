#!/usr/bin/env python
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

"""Cross-check the security lens against Bandit on real packages.

Answers one question the lens cannot answer about itself: **does it find the
execution sinks an established tool finds?** Bandit is an external authority this
project does not control, which is what makes the check non-circular — the same
discipline the moddability benchmark uses when it takes labels from a package's
own documentation rather than from MODScan's output.

    pip install "modscan[crosscheck]"
    python security-crosscheck/crosscheck.py

Offline and free apart from the target packages themselves: no LLM, no API key.

Scope
-----
The comparison is restricted to the sinks the lens *claims* to cover — code
execution, deserialization, process spawning. Bandit's other tests (weak crypto,
asserts, SQL, hardcoded passwords) are excluded on purpose: the lens explicitly
does not cover them, so counting them would measure a promise never made.

Two asymmetries are expected and are not defects:

* **Bandit has no test for some sinks the lens catalogues** — notably
  ``__reduce__`` and the builtin ``compile``. Those appear as "lens-only" and are
  extra coverage, not false positives.
* **Line attribution differs on multi-line calls.** Bandit sometimes reports a
  continuation line while the lens reports the line the call starts on. A small
  tolerance absorbs this; without it the same finding looks like a miss on one
  side and a false positive on the other.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.parser import parse_codebase  # noqa: E402
from modscan.security import find_risk_sinks  # noqa: E402

# Bandit test ids inside the lens's declared scope -> the lens category they map to.
IN_SCOPE_BANDIT = {
    "B102": "code_exec",        # exec_used
    "B307": "code_exec",        # eval
    "B301": "deserialization",  # pickle
    "B302": "deserialization",  # marshal
    "B506": "deserialization",  # yaml_load
    "B602": "process",          # subprocess with shell=True
    "B603": "process",          # subprocess without shell
    "B604": "process",          # other function with shell=True
    "B605": "process",          # start process with a shell
    "B606": "process",          # start process with no shell
}
# The lens's dynamic_load category has no Bandit counterpart (Bandit does not
# flag importlib.import_module / entry_points), so it is left out of the
# comparison rather than counted against either tool.
IN_SCOPE_LENS = {"code_exec", "deserialization", "process"}

# Multi-line calls are attributed differently by the two tools; treat findings in
# the same file within this many lines as the same finding.
LINE_TOLERANCE = 3

DEFAULT_TARGETS = ["click", "pygments", "marshmallow", "pluggy", "sqlalchemy"]


def _bandit(root: str) -> set[tuple[str, int]]:
    """In-scope Bandit findings as (relative path, line)."""
    proc = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", root, "-f", "json", "-q"],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        print(f"  ! bandit produced no JSON for {root}", file=sys.stderr)
        return set()
    return {
        (os.path.relpath(r["filename"], root).replace("\\", "/"), r["line_number"])
        for r in data.get("results", [])
        if r.get("test_id") in IN_SCOPE_BANDIT
    }


def _lens(root: str) -> set[tuple[str, int]]:
    """In-scope security-lens findings as (relative path, line)."""
    qual_to_path = {m.qualname: m.path for m in parse_codebase(root).ok_modules}
    found = set()
    for sink in find_risk_sinks(root):
        if sink.category not in IN_SCOPE_LENS:
            continue
        path = qual_to_path.get(sink.module)
        if path:
            found.add((os.path.relpath(path, root).replace("\\", "/"), sink.lineno))
    return found


def _matched(a: tuple[str, int], others: set[tuple[str, int]]) -> bool:
    """True if `a` has a counterpart in `others` within LINE_TOLERANCE."""
    path, line = a
    return any(p == path and abs(l - line) <= LINE_TOLERANCE for p, l in others)


def compare(root: str) -> tuple[int, int, int, list[tuple[str, int]]]:
    """(agreed, bandit_only, lens_only, the bandit-only findings)."""
    bandit, lens = _bandit(root), _lens(root)
    bandit_only = [f for f in sorted(bandit) if not _matched(f, lens)]
    lens_only = [f for f in sorted(lens) if not _matched(f, bandit)]
    return len(bandit) - len(bandit_only), len(bandit_only), len(lens_only), bandit_only


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="append", help="package to check (repeatable)")
    args = ap.parse_args()
    targets = args.target or DEFAULT_TARGETS

    print(f"{'package':<14} {'agreed':>7} {'bandit-only':>12} {'lens-only':>10}  recall")
    total_agreed = total_bandit_only = 0
    gaps: list[str] = []

    for name in targets:
        try:
            root = os.path.dirname(importlib.import_module(name).__file__)
        except ImportError:
            print(f"{name:<14} (not installed - pip install {name})")
            continue
        agreed, bandit_only, lens_only, missed = compare(root)
        total_agreed += agreed
        total_bandit_only += bandit_only
        total = agreed + bandit_only
        recall = f"{agreed}/{total}" if total else "n/a"
        print(f"{name:<14} {agreed:>7} {bandit_only:>12} {lens_only:>10}  {recall}")
        gaps += [f"{name}:{p}:{ln}" for p, ln in missed]

    denom = total_agreed + total_bandit_only
    print(f"\nIn-scope recall vs Bandit: {total_agreed}/{denom}")
    if gaps:
        print("\nBandit-only findings - inspect for catalog gaps:")
        for gap in gaps:
            print("  ", gap)
    else:
        print("No Bandit-only findings: the catalog covers every in-scope test Bandit fired.")

    print(
        "\nNote: 'lens-only' is expected and is not a false-positive count - Bandit "
        "has no test for __reduce__ or the builtin compile, which the lens catalogues."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
