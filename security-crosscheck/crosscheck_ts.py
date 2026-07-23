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

"""Cross-check the TypeScript/JavaScript lens against eslint-plugin-security.

The JS counterpart to `crosscheck.py`, which measures the Python lens against
Bandit. Same discipline: the authority is a tool this project does not control,
so the check cannot flatter itself, and only the sinks the lens *claims* are
compared.

    cd security-crosscheck/js && npm install
    python security-crosscheck/crosscheck_ts.py

Scope
-----
`eslint.config.mjs` enables exactly three rules — the ones inside the lens's
declared scope:

| eslint-plugin-security rule | lens category |
|---|---|
| `detect-eval-with-expression` | code_exec |
| `detect-child-process` | process |
| `detect-non-literal-require` | dynamic_load |

Its other rules (unsafe regex, object injection, timing attacks, fs filenames,
pseudo-random bytes) are left off: the lens does not claim them.

Expected asymmetries — not defects
----------------------------------
* **eslint flags `eval` only with a computed argument.** The lens flags every
  `eval`, matching Bandit's stance on the Python side. A literal `eval("1+1")`
  therefore shows as lens-only.
* **eslint has no rule for `new Function`, the `vm` module, or string-bodied
  timers.** The lens catalogues all three, so they show as lens-only coverage.
* **Line attribution can differ on multi-line calls**, as with Bandit; the same
  tolerance applies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.security.detect_ts import find_ts_risk_sinks  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JS_DIR = os.path.join(HERE, "js")
CONFIG = os.path.join(JS_DIR, "eslint.config.mjs")
ESLINT = os.path.join(JS_DIR, "node_modules", ".bin", "eslint")

# Only these categories are compared; the config enables only their rules.
IN_SCOPE_LENS = {"code_exec", "process", "dynamic_load"}
LINE_TOLERANCE = 3

# Packages installed under security-crosscheck/js/node_modules to scan.
DEFAULT_TARGETS = ["shelljs", "cross-spawn"]


def _eslint(root: str) -> set[tuple[str, int]]:
    """In-scope eslint findings as (relative path, line)."""
    exe = ESLINT + (".cmd" if os.name == "nt" and os.path.exists(ESLINT + ".cmd") else "")
    if not os.path.exists(exe):
        print(
            "eslint not installed - run: cd security-crosscheck/js && npm install",
            file=sys.stderr,
        )
        return set()
    # Decode as UTF-8 explicitly: `text=True` would use the locale encoding, and a
    # Windows cp1252 console corrupts (or fails on) eslint's output — which would
    # silently drop findings and inflate the recall number.
    proc = subprocess.run(
        [exe, "--no-config-lookup", "-c", CONFIG, "--format", "json", "."],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        report = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        print(f"  ! eslint produced no JSON for {root}", file=sys.stderr)
        return set()

    found = set()
    for entry in report:
        rel = os.path.relpath(entry["filePath"], root).replace("\\", "/")
        for msg in entry.get("messages", []):
            rule = msg.get("ruleId") or ""
            if rule.startswith("security/"):
                found.add((rel, msg["line"]))
    return found


def _lens(root: str) -> set[tuple[str, int]]:
    """In-scope lens findings as (relative path, line)."""
    return {
        (s.module, s.lineno)
        for s in find_ts_risk_sinks(root)
        if s.category in IN_SCOPE_LENS
    }


def _matched(item: tuple[str, int], others: set[tuple[str, int]]) -> bool:
    """True if `item` has a counterpart in `others` within LINE_TOLERANCE.

    The lens reports module paths without an extension; eslint reports the file.
    Compare on the extension-stripped path so the two line up.
    """
    path, line = item
    stem = os.path.splitext(path)[0]
    return any(
        os.path.splitext(p)[0] == stem and abs(l - line) <= LINE_TOLERANCE
        for p, l in others
    )


def compare(root: str) -> tuple[int, int, int, list[tuple[str, int]]]:
    eslint, lens = _eslint(root), _lens(root)
    eslint_only = [f for f in sorted(eslint) if not _matched(f, lens)]
    lens_only = [f for f in sorted(lens) if not _matched(f, eslint)]
    return len(eslint) - len(eslint_only), len(eslint_only), len(lens_only), eslint_only


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="append", help="package under js/node_modules (repeatable)")
    ap.add_argument("--path", help="scan an arbitrary directory instead")
    args = ap.parse_args()

    roots: list[tuple[str, str]] = []
    if args.path:
        roots.append((os.path.basename(os.path.abspath(args.path)), os.path.abspath(args.path)))
    else:
        for name in args.target or DEFAULT_TARGETS:
            path = os.path.join(JS_DIR, "node_modules", name)
            if os.path.isdir(path):
                roots.append((name, path))
            else:
                print(f"{name:<16} (not installed - cd security-crosscheck/js && npm install)")

    print(f"{'package':<16} {'agreed':>7} {'eslint-only':>12} {'lens-only':>10}  recall")
    total_agreed = total_eslint_only = 0
    gaps: list[str] = []

    for name, root in roots:
        agreed, eslint_only, lens_only, missed = compare(root)
        total_agreed += agreed
        total_eslint_only += eslint_only
        total = agreed + eslint_only
        recall = f"{agreed}/{total}" if total else "n/a"
        print(f"{name:<16} {agreed:>7} {eslint_only:>12} {lens_only:>10}  {recall}")
        gaps += [f"{name}:{p}:{ln}" for p, ln in missed]

    denom = total_agreed + total_eslint_only
    print(f"\nIn-scope recall vs eslint-plugin-security: {total_agreed}/{denom}")
    if gaps:
        print("\neslint-only findings - inspect for catalog gaps:")
        for gap in gaps:
            print("  ", gap)
    else:
        print("No eslint-only findings: the catalog covers every in-scope rule that fired.")

    print(
        "\nNote: 'lens-only' is expected - eslint has no rule for new Function, the vm "
        "module or string-bodied timers, and it flags eval only with a computed argument."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
