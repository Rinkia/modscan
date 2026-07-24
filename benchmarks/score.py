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

"""Score MODScan's ranking against the labelled ground truth.

Answers one question before you open a pull request: did this heuristic change
help? Runs offline and free — no API key, no paid call, no network.

    pip install pluggy==1.6.0 click==8.4.2 sqlalchemy==2.0.51 \
                pygments==2.20.0 marshmallow==4.3.0 flask==3.1.2
    python benchmarks/score.py

Reports, per target, where each labelled extension point ranks, plus recall@10,
precision@10 and the median rank. The headline is aggregate recall@10 across all
targets; see benchmarks/README.md for why it is aggregate and why median rank is
reported alongside.

recall@10 is also reported with **tie bounds**. The detector breaks score ties
alphabetically, so when a band of equally-scored candidates straddles rank 10,
the alphabet — not the ranking — decides which labels land inside. The bounds say
what the score would be if every tie broke in the ranking's favour and if every
tie broke against it. A change is only real if it moves the lower bound.

A target that is not installed, or installed at a version other than the one its
labels were derived from, is SKIPPED with a notice. A score against a different
version would be misleading, and a misleading number is worse than no number.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan import build_graph, detect_extension_points, parse_codebase  # noqa: E402

K = 10

GROUND_TRUTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ground_truth.json")


# --- metrics (pure — no IO, no target imports; tested in tests/) -------------


def normalise_id(target: str, module: str, name: str) -> str:
    """Build a label id from what the parser actually emits.

    The parser reports module paths relative to the directory it was pointed at,
    so scanning an installed pluggy yields ``_manager``, not ``pluggy._manager``.
    Labels are fully qualified because that is the form a human can check against
    the documentation, so the two have to be reconciled somewhere — here.
    """
    if not module:
        module = target
    elif module != target and not module.startswith(f"{target}."):
        module = f"{target}.{module}"
    return f"{module}:{name}"


def recall_at_k(ranks: dict[str, int], k: int = K) -> tuple[int, int]:
    """Labelled points reaching the top k, out of all labelled points."""
    return sum(1 for r in ranks.values() if r <= k), len(ranks)


def precision_at_k(ranks: dict[str, int], k: int = K) -> tuple[int, int]:
    """Labelled points in the top k, out of k.

    Reported, not optimised: with a partial label list this has a ceiling below
    1 no matter how good the ranking is. See benchmarks/README.md.
    """
    return sum(1 for r in ranks.values() if r <= k), k


def tie_bounds(scores: list[float], position: int) -> tuple[int, int]:
    """Best and worst rank the point at 1-based ``position`` could hold.

    The detector breaks score ties by module name, i.e. alphabetically, so a
    point's printed rank inside a tied band is an artefact of its name. These are
    the bounds of that band: the rank it would have if the tie broke entirely in
    its favour, and if it broke entirely against.
    """
    score = scores[position - 1]
    higher = sum(1 for s in scores if s > score)
    same = sum(1 for s in scores if s == score)
    return higher + 1, higher + same


def recall_bounds(bounds: dict[str, tuple[int, int]], k: int = K) -> tuple[int, int]:
    """Labelled points reaching the top k under the best and worst tie order.

    When these two disagree, the tie order — not the ranking — is deciding the
    score, and ``recall_at_k`` should be read as one sample from that interval.
    """
    best = sum(1 for lo, _ in bounds.values() if lo <= k)
    worst = sum(1 for _, hi in bounds.values() if hi <= k)
    return worst, best


def median_rank(ranks: dict[str, int]) -> float:
    """Median rank of the labelled points.

    Continuous, so it moves before recall@k does. That matters for a target like
    SQLAlchemy whose labels sit in the hundreds: a large genuine improvement can
    leave recall@10 pinned at 0 while this figure drops sharply.
    """
    return statistics.median(ranks.values())


# --- the run ----------------------------------------------------------------


JS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js", "node_modules")


def _js_package_dir(target: str) -> str:
    return os.path.join(JS_ROOT, target)


def _js_version(target: str) -> str | None:
    """Installed version from the package's own package.json, or None."""
    manifest = os.path.join(_js_package_dir(target), "package.json")
    try:
        with open(manifest, encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except (OSError, json.JSONDecodeError):
        return None


JAVA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "java")


def _java_package_dir(target: str, pinned: str) -> str:
    """Sources unpacked by benchmarks/java/fetch.py, version in the dir name."""
    return os.path.join(JAVA_ROOT, f"{target}-{pinned}")


def _skip_reason_java(target: str, pinned: str) -> str | None:
    if not os.path.isdir(_java_package_dir(target, pinned)):
        return f"not fetched - python benchmarks/java/fetch.py"
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_java  # noqa: F401
    except ImportError:
        return "tree-sitter-java not installed - pip install modscan[java]"
    return None


def _skip_reason_js(target: str, pinned: str) -> str | None:
    """Why a JS/TS target cannot be scored, or None if it can be."""
    if not os.path.isdir(_js_package_dir(target)):
        return f"not installed - cd benchmarks/js && npm install"
    installed = _js_version(target)
    if installed is None:
        return f"no package.json version - cd benchmarks/js && npm install"
    if installed != pinned:
        return (
            f"installed {installed}, labels are for {pinned} - "
            f"cd benchmarks/js && npm install {target}@{pinned}"
        )
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_typescript  # noqa: F401
    except ImportError:
        return "tree-sitter not installed - pip install modscan[typescript]"
    return None


def _skip_reason(target: str, pinned: str, language: str = "python") -> str | None:
    """Why this target cannot be scored, or None if it can be."""
    if language == "java":
        return _skip_reason_java(target, pinned)
    if language != "python":
        return _skip_reason_js(target, pinned)
    try:
        importlib.import_module(target)
    except ImportError:
        return f"not installed — pip install {target}=={pinned}"

    try:
        installed = importlib.metadata.version(target)
    except importlib.metadata.PackageNotFoundError:
        return f"no distribution metadata — pip install {target}=={pinned}"

    if installed != pinned:
        return f"installed {installed}, labels are for {pinned} — pip install {target}=={pinned}"
    return None


def rank_labels(
    target: str,
    labels: set[str],
    language: str = "python",
    pinned: str = "",
) -> tuple[dict[str, int], dict[str, tuple[int, int]], int]:
    """Rank of every labelled point in the detector's output, plus tie bounds and
    the candidate count.

    A label the detector never surfaces is recorded at ``candidates + 1`` rather
    than dropped. Dropping it would let a change that loses a seam entirely make
    the median *improve*.
    """
    if language == "python":
        root = os.path.dirname(importlib.import_module(target).__file__)
        codebase = parse_codebase(root)
    else:
        # Non-Python targets are fetched into benchmarks/<lang>/ and their module
        # qualnames are not package-prefixed ("lib/command",
        # "org.junit.jupiter.api.extension.Extension"), so ids are
        # target-qualified - "commander/lib/command:Command". That keeps the
        # "an id belongs to its target" invariant the label self-check enforces.
        from modscan.languages import get_language_parser  # registers front-ends

        root = (
            _java_package_dir(target, pinned)
            if language == "java"
            else _js_package_dir(target)
        )
        codebase = get_language_parser(language).parse_codebase(root)
    points = detect_extension_points(build_graph(codebase))

    scores = [p.score for p in points]
    ranks: dict[str, int] = {}
    bounds: dict[str, tuple[int, int]] = {}
    for position, point in enumerate(points, start=1):
        pid = (
            normalise_id(target, point.seam.module, point.seam.name)
            if language == "python"
            else f"{target}/{point.seam.module}:{point.seam.name}"
        )
        if pid in labels and pid not in ranks:
            ranks[pid] = position
            bounds[pid] = tie_bounds(scores, position)

    for missing in labels - set(ranks):
        ranks[missing] = len(points) + 1
        bounds[missing] = (len(points) + 1, len(points) + 1)

    return ranks, bounds, len(points)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", help="score only this target (default: all)")
    args = ap.parse_args()

    with open(GROUND_TRUTH, encoding="utf-8") as fh:
        truth = json.load(fh)

    targets = truth["targets"]
    if args.target:
        if args.target not in targets:
            print(f"unknown target {args.target!r}; known: {', '.join(sorted(targets))}")
            return 2
        targets = {args.target: targets[args.target]}

    rows: list[str] = []
    absent: list[str] = []
    scored_hits = scored_total = 0
    scored_worst = scored_best = 0

    for name, target in sorted(targets.items()):
        pinned = target["version"]
        language = target.get("language", "python")
        reason = _skip_reason(name, pinned, language)
        if reason:
            print(f"SKIP {name}: {reason}")
            continue

        labels = {p["id"] for p in target["extension_points"]}
        ranks, bounds, candidates = rank_labels(name, labels, language, pinned)

        hits, total = recall_at_k(ranks)
        worst, best = recall_bounds(bounds)
        scored_hits += hits
        scored_total += total
        scored_worst += worst
        scored_best += best

        absent += [pid for pid, r in ranks.items() if r > candidates]
        ordered = ", ".join(str(r) for r in sorted(ranks.values()))
        # ASCII only: this line is printed, and Windows' cp1252 stdout mangles
        # an en-dash into a question mark.
        span = f"{hits}/{total}" if worst == best else f"{hits}/{total} ({worst}..{best})"
        rows.append(
            f"| {name} {pinned} | {candidates} | {total} | {ordered} | "
            f"{span} | {median_rank(ranks):g} |"
        )

    if not rows:
        print("\nNothing scored — install the pinned targets and re-run.")
        return 1

    print(
        f"\n| Target | Candidates | Labels | Rank of each label | "
        f"recall@{K} (tie bounds) | Median rank |"
    )
    print("|---|---|---|---|---|---|")
    print("\n".join(rows))

    for pid in absent:
        print(f"\nNOT DETECTED: {pid} — counted at candidates+1.")

    print(f"\nAggregate recall@{K}: {scored_hits}/{scored_total}")
    if scored_worst != scored_best:
        print(
            f"Tie-aware bounds: {scored_worst}/{scored_total} to {scored_best}/{scored_total}. "
            f"{scored_best - scored_worst} of {scored_total} labels sit in a band that straddles "
            f"rank {K}, so their hit or miss is decided by the alphabetical tiebreak, not by the "
            f"ranking. Judge a change on the LOWER bound."
        )
    if len(rows) < len(truth["targets"]):
        print("Partial run — the aggregate is not comparable to the published baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
