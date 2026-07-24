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

"""Cross-check the moddability labels against what real plugins actually extend.

The security lens is validated against Bandit and eslint-plugin-security —
authorities this project does not control. Moddability had no equivalent: its
ground truth came from one source, the host's own documentation, and MODScan's
ranking is the thing being judged, so neither could validate the other.

This is the missing third source. For each host it parses a pinned set of real
downstream packages and counts, per host symbol, **how many of them subclass
it**. Nobody involved in this project controls what a plugin author chose to
subclass.

    python usage-crosscheck/crosscheck_usage.py --install   # print the pip line
    python usage-crosscheck/crosscheck_usage.py

Offline and free: the downstream packages are *parsed*, never imported or
executed, so a package that will not install into this interpreter can still be
measured. Install them with ``--target`` into ``usage-crosscheck/downstream/``
(the printed command does this) — they are gitignored, like every other target.

What the count is, and is not
-----------------------------
**Subclass count is the measurement. Import count is deliberately not.** Import
counts were measured too and rank an API by popularity, not by extensibility:
marshmallow's most-imported symbol is ``ValidationError`` (an exception you
catch) and click's is ``echo``. Those are precisely the "things you merely call"
the labelling rule excludes, so ranking by imports would contradict the rule the
labels are built on. The report prints both, so that stays checkable rather than
asserted.

This is *not* the rejected "internal subclass count" hypothesis. That one counted
subclasses **inside the package being scanned** and failed because a package's
own machinery subclasses its own bases constantly. This counts subclasses in
*downstream* code — which the earlier work explicitly named as the place the
evidence lives and a single-package scan can never see.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from modscan.parser import parse_codebase, parse_file  # noqa: E402

DOWNSTREAM = os.path.join(_HERE, "downstream.json")
PACKAGES_DIR = os.path.join(_HERE, "downstream")


# --- counting (pure — takes parsed modules, so it is testable without targets)


def base_tail(base: str) -> str:
    """Last segment of a base-class expression, generics stripped.

    Plugins name a base every way Python allows — ``ma.fields.Field``,
    ``fields.Field``, ``Field``, ``Field[int]``. All four mean the same symbol.
    """
    return base.split(".")[-1].split("[")[0].strip()


def count_usage(modules, known: set[str]) -> tuple[set[str], set[str]]:
    """Host symbols this package subclasses, and host symbols it imports.

    Both are per-package *sets*, not totals: a package that subclasses ``Field``
    forty times is one package's opinion, not forty. Counting occurrences would
    let a single large plugin outvote the ecosystem.
    """
    subclassed: set[str] = set()
    imported: set[str] = set()
    for module in modules:
        for cls in module.classes:
            for base in cls.bases:
                tail = base_tail(base)
                if tail in known:
                    subclassed.add(tail)
        for imp in module.imports:
            if imp.name in known:
                imported.add(imp.name)
    return subclassed, imported


# --- the run ----------------------------------------------------------------


def _host_symbols(host: str) -> set[str]:
    """Every public symbol the parser finds in the installed host."""
    import importlib

    root = os.path.dirname(importlib.import_module(host).__file__)
    codebase = parse_codebase(root)
    names: set[str] = set()
    for module in codebase.modules:
        names |= {c.name for c in module.classes}
        names |= {f.name for f in module.functions}
    return names


def _host_ranks(host: str) -> dict[str, int]:
    """MODScan's own rank per symbol name, so agreement can be read off directly."""
    import importlib

    from modscan import build_graph, detect_extension_points

    root = os.path.dirname(importlib.import_module(host).__file__)
    points = detect_extension_points(build_graph(parse_codebase(root)))
    ranks: dict[str, int] = {}
    for position, point in enumerate(points, start=1):
        ranks.setdefault(point.seam.name, position)
    return ranks


def _parse_package(path: str):
    """Modules of a downstream package, whether it is a directory or one file."""
    if os.path.isdir(path):
        return parse_codebase(path).modules
    return [parse_file(path, os.path.basename(path)[:-3])]


def _package_paths(root: str) -> list[str]:
    skip = ("bin", "__pycache__")
    out = []
    for entry in sorted(os.listdir(root)):
        if entry.endswith(".dist-info") or entry in skip:
            continue
        path = os.path.join(root, entry)
        if os.path.isdir(path) or entry.endswith(".py"):
            out.append(path)
    return out


def _pip_line(spec: dict) -> str:
    pins = " ".join(f"{n}=={v}" for n, v in spec["downstream"].items())
    return f'pip install --no-deps --target usage-crosscheck/downstream/{{host}} {pins}'


def report_host(host: str, spec: dict) -> int:
    root = os.path.join(PACKAGES_DIR, host)
    if not os.path.isdir(root):
        print(f"SKIP {host}: no downstream packages — run with --install for the command")
        return 0

    known = _host_symbols(host)
    ranks = _host_ranks(host)
    subclassed: Counter[str] = Counter()
    imported: Counter[str] = Counter()

    paths = _package_paths(root)
    for path in paths:
        subs, imps = count_usage(_parse_package(path), known)
        for name in subs:
            subclassed[name] += 1
        for name in imps:
            imported[name] += 1

    labels = _labels_for(host)
    print(f"\n## {host} {spec['version']} — {len(paths)} downstream packages")
    print(f"_{spec['why']}_\n")
    print("| Host symbol | Plugins subclassing it | Plugins importing it | MODScan rank | Labelled |")
    print("|---|---|---|---|---|")
    for name, count in subclassed.most_common(12):
        rank = ranks.get(name)
        print(
            f"| `{name}` | **{count}** | {imported[name]} | "
            f"{rank if rank else '—'} | {'yes' if name in labels else 'no'} |"
        )

    if not subclassed:
        print("| _nothing_ | 0 | | | |")

    missed = [n for n in labels if subclassed[n] == 0]
    if missed:
        print(f"\nLabelled but subclassed by none of these plugins: {', '.join(sorted(missed))}")
    unlabelled = [n for n, c in subclassed.most_common(5) if n not in labels]
    if unlabelled:
        print(
            f"Subclassed but not labelled: {', '.join(unlabelled)} — candidates for a "
            "documentation check, not labels to add on usage alone."
        )
    return len(paths)


def _labels_for(host: str) -> set[str]:
    """Label names for a host, read from the benchmark's ground truth."""
    path = os.path.join(os.path.dirname(_HERE), "benchmarks", "ground_truth.json")
    with open(path, encoding="utf-8") as fh:
        truth = json.load(fh)
    target = truth["targets"].get(host)
    if not target:
        return set()
    return {p["id"].rsplit(":", 1)[-1] for p in target["extension_points"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--install", action="store_true", help="print the pip commands and exit"
    )
    ap.add_argument("--host", help="only this host (default: all)")
    args = ap.parse_args()

    with open(DOWNSTREAM, encoding="utf-8") as fh:
        hosts = json.load(fh)["hosts"]
    if args.host:
        if args.host not in hosts:
            print(f"unknown host {args.host!r}; known: {', '.join(sorted(hosts))}")
            return 2
        hosts = {args.host: hosts[args.host]}

    if args.install:
        for host, spec in hosts.items():
            print(_pip_line(spec).format(host=host))
        return 0

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    scored = sum(report_host(host, spec) for host, spec in hosts.items())
    if not scored:
        print("\nNothing measured — run with --install and follow the printed commands.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
