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

"""Generate a committable showcase: MODScan run against a real project.

An example output in the repository is worth more than any amount of prose — it
shows what MODScan actually produces, on code people recognise, including the
parts it gets wrong.

This script MAKES PAID API CALLS. It therefore:
  * shows the worst-case call count and makes you confirm with --yes;
  * caps calls with a hard budget, so a surprise cannot run away;
  * caches responses, so re-runs while you tune flags are free;
  * previews the detected extension points for free (no LLM) with --dry-run.

Usage:
    python examples/generate_showcase.py --dry-run                # free preview
    python examples/generate_showcase.py --target click --yes     # real run

The target may be an installed package name (copied to a temp dir so module
qualnames resolve, mirroring a repo checkout) or a path to a source tree.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.detector import detect_extension_points  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.parser import parse_codebase  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGET = "click"


def resolve_target(target: str) -> tuple[str, str, bool]:
    """Return (scan_root, label, is_temp).

    A path is scanned in place. An installed package is copied into a temp dir
    as <tmp>/<pkg>/ so that qualnames match what `import` expects — the same
    layout a repository checkout has.
    """
    if os.path.isdir(target):
        return os.path.abspath(target), os.path.basename(os.path.abspath(target)), False

    spec = importlib.util.find_spec(target)
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(
            f"error: {target!r} is neither a directory nor an installed package"
        )
    src = list(spec.submodule_search_locations)[0]
    tmp = tempfile.mkdtemp(prefix="modscan-showcase-")
    shutil.copytree(src, os.path.join(tmp, target))
    return tmp, target, True


def preview(scan_root: str, min_score: float, limit: int) -> int:
    """Print the extension points MODScan would document. Costs nothing."""
    codebase = parse_codebase(scan_root)
    points = detect_extension_points(build_graph(codebase), min_score=min_score)
    print(f"modules parsed : {len(codebase.ok_modules)} "
          f"(failed: {len(codebase.failed_modules)})")
    print(f"points >= {min_score}  : {len(points)}")
    print(f"would document : {min(limit, len(points))} (--limit {limit})\n")
    for p in points[:limit]:
        print(f"  {p.score:.2f}  {p.category:13}  {p.seam.module}:{p.seam.name}")
    return min(limit, len(points))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=DEFAULT_TARGET,
                    help=f"installed package name or source path (default: {DEFAULT_TARGET})")
    ap.add_argument("--out", default=None,
                    help="output dir (default: examples/showcase-<target>/)")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--min-score", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=8,
                    help="how many extension points to document (default: 8)")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--cache-dir", default=os.path.join(REPO_ROOT, ".showcase-cache"))
    ap.add_argument("--dry-run", action="store_true",
                    help="preview detected points without calling any API")
    ap.add_argument("--yes", action="store_true",
                    help="confirm you accept the API cost of a real run")
    args = ap.parse_args(argv)

    scan_root, label, is_temp = resolve_target(args.target)
    out = args.out or os.path.join(REPO_ROOT, "examples", f"showcase-{label}")

    try:
        print(f"target      : {label}  ({scan_root})")
        planned = preview(scan_root, args.min_score, args.limit)

        # Worst case: one overview call, then per point a guide plus up to
        # `retries` example attempts.
        budget = 1 + planned * (1 + args.retries)
        print(f"\nworst-case LLM calls: {budget}  "
              f"(1 overview + {planned} x (1 guide + up to {args.retries} examples))")
        print(f"per-call output cap : {args.max_tokens} tokens")

        if args.dry_run:
            print("\ndry run: nothing was sent to any API.")
            return 0
        if not args.yes:
            print("\nThis run makes PAID API calls. Re-run with --yes to proceed, "
                  "or use --dry-run to preview for free.")
            return 1

        from modscan.docgen import generate_docs
        from modscan.providers import BudgetExceeded, BudgetProvider, CachingProvider
        from modscan.providers import get_provider

        provider = get_provider(
            args.provider, model=args.model, max_tokens=args.max_tokens
        )
        provider = CachingProvider(provider, args.cache_dir)  # cache below budget
        provider = BudgetProvider(provider, max_calls=budget)

        print(f"\ngenerating into {out} ...")
        try:
            report = generate_docs(
                scan_root,
                provider,
                out,
                min_score=args.min_score,
                limit=args.limit,
                max_example_retries=args.retries,
                concurrency=args.concurrency,
            )
        except BudgetExceeded as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3

        verified = report.verified_count
        print(f"\ndocumented {len(report.points)} points, {verified} with a verified "
              f"example. LLM calls used: {provider.calls}/{provider.max_calls}")
        print(f"output: {out}")
        print("\nReview it before committing — especially whether the ranking "
              "surfaced the extension points a real plugin author would want.")
        return 0
    finally:
        if is_temp:
            shutil.rmtree(scan_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
