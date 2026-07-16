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

"""Command-line entry point: `modscan <path>` -> modding-docs/.

Thin wrapper over the pipeline. Provider construction (which needs an SDK + API
key) is kept in `main`; the actual work lives in `run(args, provider)` so it can
be exercised with a FakeProvider in tests, no network.
"""

from __future__ import annotations

import argparse
import os
import sys

from modscan.docgen import generate_docs
from modscan.providers import Provider, get_provider
from modscan.scaffold import scaffold, scaffold_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modscan",
        description="Scan a codebase and generate plugin/mod documentation "
        "(Markdown + extension-points.json).",
    )
    parser.add_argument("root", help="path to the source-available codebase to scan")
    parser.add_argument(
        "--out", default="modding-docs", help="output directory (default: modding-docs)"
    )
    parser.add_argument(
        "--provider", default="anthropic", help="LLM provider: anthropic | openai"
    )
    parser.add_argument("--model", default=None, help="model id (default: provider's default)")
    parser.add_argument(
        "--base-url", default=None, help="OpenAI-compatible endpoint base URL"
    )
    parser.add_argument(
        "--min-score", type=float, default=0.5, help="min moddability score (default: 0.5)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="cap how many points are validated/documented"
    )
    parser.add_argument(
        "--retries", type=int, default=4, help="example-validation retries, 3-5 (default: 4)"
    )
    parser.add_argument(
        "--no-validate-examples",
        action="store_true",
        help="skip executing generated examples (no import/exec of target code)",
    )
    return parser


def build_scaffold_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modscan scaffold",
        description="Generate a plugin skeleton for an extension point id, "
        "using a previously generated extension-points.json manifest.",
    )
    parser.add_argument(
        "point_id", nargs="?", help="extension point id, e.g. 'pkg.mod:Symbol'"
    )
    parser.add_argument(
        "--all", action="store_true", help="scaffold every point in the manifest"
    )
    parser.add_argument(
        "--manifest",
        default=os.path.join("modding-docs", "extension-points.json"),
        help="path to extension-points.json (default: modding-docs/extension-points.json)",
    )
    parser.add_argument("--out", default=".", help="output directory (default: .)")
    return parser


def _main_scaffold(argv: list[str]) -> int:
    args = build_scaffold_parser().parse_args(argv)
    if not os.path.isfile(args.manifest):
        print(f"error: manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    if args.all:
        paths = scaffold_all(args.manifest, args.out)
        print(f"Wrote {len(paths)} plugin skeleton(s) to {args.out}")
        return 0
    if not args.point_id:
        print("error: provide a point id or --all", file=sys.stderr)
        return 2
    try:
        path = scaffold(args.manifest, args.point_id, args.out)
    except ValueError as exc:  # point id not found — message lists valid ids
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote plugin skeleton: {path}")
    return 0


def run(args: argparse.Namespace, provider: Provider) -> int:
    """Run the pipeline with an already-constructed provider. Returns exit code."""
    report = generate_docs(
        args.root,
        provider,
        args.out,
        min_score=args.min_score,
        limit=args.limit,
        max_example_retries=args.retries,
        validate_examples=not args.no_validate_examples,
    )
    verified = report.verified_count
    total = len(report.points)
    unverified = sum(1 for p in report.points if p.example_status == "unverified")
    print(f"Scanned: {args.root}")
    print(f"Extension points documented: {total} (verified: {verified}, unverified: {unverified})")
    print(f"Docs:     {os.path.join(args.out, 'index.md')}")
    print(f"          {os.path.join(args.out, 'plugin-guide.md')}")
    print(f"Manifest: {report.manifest_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "scaffold":
        return _main_scaffold(argv[1:])

    args = build_parser().parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"error: not a directory: {args.root}", file=sys.stderr)
        return 2

    if not args.no_validate_examples:
        print(
            "warning: MODScan will IMPORT and EXECUTE code under "
            f"'{args.root}' to validate examples. Run only on code you trust "
            "(use --no-validate-examples to skip).",
            file=sys.stderr,
        )

    try:
        provider = get_provider(args.provider, model=args.model, base_url=args.base_url)
        return run(args, provider)
    except Exception as exc:  # noqa: BLE001 — top-level CLI guard, report cleanly
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
