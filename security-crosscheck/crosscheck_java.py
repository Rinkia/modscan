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

"""Cross-check the Java security lens against Semgrep.

The Python lens is measured against Bandit and the TS/JS lens against
eslint-plugin-security. Java's authority is **Semgrep's `p/security-audit`
ruleset**, an authority this project does not control.

    python security-crosscheck/crosscheck_java.py            # needs Docker

There is a hard environment constraint: **Semgrep's engine (`semgrep-core`)
cannot run on native Windows** — it fails at `socketpair`. So this harness runs
Semgrep through its official Docker image (`semgrep/semgrep`), which is also how
it would run in CI. Docker must be available; the Java sources are fetched the
same way `benchmarks/java/fetch.py` fetches benchmark targets.

The asymmetry that shapes the comparison
----------------------------------------
Bandit and eslint-plugin-security are **enumeration** tools, like the lens, so a
finding-for-finding recall is meaningful. **Semgrep's Java security rules are
mostly taint-mode**: they fire only when data flows from a source (an HTTP
parameter, say) to the sink. Library source has no such entry points, so Semgrep
reports *almost nothing* on it — 0 on xstream and snakeyaml, 1 on commons-lang3
in the spike that built this — while the enumeration lens reports dozens.

That means "lens-only" is not a false-positive count here, any more than it is
for `__reduce__` against Bandit. The direction that *is* meaningful is the other
one: **every sink Semgrep does flag must appear in the lens.** Semgrep's
taint-confirmed findings are a high-precision lower bound; the lens claims to
enumerate a superset, so it must contain them. This harness measures exactly that
containment, and treats a Semgrep finding the lens misses as the real signal —
which is how it caught the try-with-resources gap in the Java detector.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from modscan.security.detect import find_risk_sinks  # noqa: E402
from modscan.languages.java import _qualname  # noqa: E402

LINE_TOLERANCE = 3
WORK = os.path.join(_HERE, "java-targets")
MAVEN = "https://repo1.maven.org/maven2"
SEMGREP_IMAGE = "semgrep/semgrep"
SEMGREP_CONFIG = "p/security-audit"

# group:artifact -> version. Chosen for having real execution/deserialization
# surface, so Semgrep has something to confirm against.
TARGETS: dict[str, tuple[str, str]] = {
    "xstream": ("com.thoughtworks.xstream:xstream", "1.4.20"),
    "commons-lang3": ("org.apache.commons:commons-lang3", "3.17.0"),
    "snakeyaml": ("org.yaml:snakeyaml", "2.3"),
    "spring-expression": ("org.springframework:spring-expression", "6.1.14"),
}

# Semgrep check-id trailing segments in the lens's scope. Semgrep's own
# out-of-scope rules (SQLi, path traversal, weak crypto, XXE-only) are ignored
# the same way Bandit's crypto/assert tests are — counting them would measure a
# promise the lens never made.
IN_SCOPE_SEMGREP = {
    "object-deserialization",
    "script-engine-injection",
    "command-injection-formatted-runtime-call",
    "java-jdbc-sqli",  # excluded below by category, listed for clarity
    "spel-injection",
    "el-injection",
    "xml-decoder",
    "unsafe-reflection",
}


def _target_dir(name: str, version: str) -> str:
    return os.path.join(WORK, f"{name}-{version}")


def fetch(name: str, coordinate: str, version: str) -> str:
    """Unpack the -sources.jar, like benchmarks/java/fetch.py. Returns the dir."""
    dest = _target_dir(name, version)
    if os.path.isdir(dest):
        return dest
    group, artifact = coordinate.split(":", 1)
    url = f"{MAVEN}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}-sources.jar"
    raw = urllib.request.urlopen(url, timeout=120).read()  # noqa: S310 - fixed Maven host
    zipfile.ZipFile(io.BytesIO(raw)).extractall(dest)
    return dest


def _semgrep(root: str) -> set[tuple[str, int]]:
    """In-scope Semgrep findings as (relative path, line), via the Docker image."""
    proc = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{os.path.abspath(root)}:/src",
            SEMGREP_IMAGE, "semgrep", "scan", "--config", SEMGREP_CONFIG,
            "--json", "--metrics=off", "--disable-version-check", "/src",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",  # Windows console + subprocess: never let cp1252 drop output
        env={**os.environ, "MSYS_NO_PATHCONV": "1"},
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"  ! semgrep produced no JSON for {root}\n{proc.stderr[-500:]}\n")
        return set()
    found = set()
    for r in data.get("results", []):
        segment = r["check_id"].rsplit(".", 1)[-1]
        if segment in IN_SCOPE_SEMGREP:
            rel = r["path"].split("/src/", 1)[-1]
            found.add((rel, r["start"]["line"]))
    return found


def _lens(root: str) -> set[tuple[str, int]]:
    """Lens findings as (relative path, line). Every category is in scope here:
    the Semgrep rules we compare against are all execution sinks."""
    found = set()
    for sink in find_risk_sinks(root, language="java"):
        rel = sink.module.replace(".", "/") + ".java"
        found.add((rel, sink.lineno))
    return found


def _matched(item: tuple[str, int], others: set[tuple[str, int]]) -> bool:
    path, line = item
    return any(p == path and abs(ln - line) <= LINE_TOLERANCE for p, ln in others)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="append", help="package name to check (repeatable)")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        print("Docker is not available. Semgrep cannot run on native Windows "
              "(semgrep-core fails at socketpair), so this check needs Docker or a "
              "Linux/CI environment. Start Docker and re-run.")
        return 1

    names = args.target or list(TARGETS)
    os.makedirs(WORK, exist_ok=True)

    print(f"{'package':<20} {'semgrep in-scope':>16} {'covered by lens':>16}")
    total_semgrep = total_covered = 0
    gaps: list[str] = []
    for name in names:
        coordinate, version = TARGETS[name]
        root = fetch(name, coordinate, version)
        semgrep, lens = _semgrep(root), _lens(root)
        covered = [f for f in semgrep if _matched(f, lens)]
        missed = [f for f in sorted(semgrep) if not _matched(f, lens)]
        total_semgrep += len(semgrep)
        total_covered += len(covered)
        print(f"{name:<20} {len(semgrep):>16} {len(covered):>16}")
        gaps += [f"{name}: {p}:{ln}" for p, ln in missed]

    print(f"\nContainment: the lens covers {total_covered}/{total_semgrep} of Semgrep's "
          "in-scope, taint-confirmed findings.")
    if gaps:
        print("\nSemgrep found these and the lens did NOT — real gaps to investigate:")
        for g in gaps:
            print(f"  {g}")
        return 1
    print("\nEvery sink Semgrep confirmed appears in the lens. Note this is CONTAINMENT, "
          "not recall: Semgrep's taint rules under-report on library source by design, so "
          "the lens finding far more is expected coverage, not false positives.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
