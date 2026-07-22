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

"""Filesystem conventions shared by every scanner.

Before this module the skip-list lived in three places with three different
values, so the Python front-end walked `dist/` while the TypeScript one walked
`.venv/` — the same tree produced different results depending on who asked.
One set, one walker, one slug function.

Depends on nothing in modscan: this is leaf infrastructure.
"""

from __future__ import annotations

import os
from typing import Iterator

# Directories no source scanner should descend into. Union of what the Python,
# TypeScript and config scanners each used to skip individually — deliberately
# broad, since anything listed here is build output, vendored code, or tooling
# cache, never a codebase's own extension points.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".eggs",
        "node_modules",
        "dist",
        "build",
        ".next",
    }
)


def _canon(path: str) -> str:
    """Normalized absolute path for reliable comparison across case and symlinks."""
    return os.path.normcase(os.path.realpath(path))


def walk_source_files(
    root: str, extensions: tuple[str, ...], skip_paths: tuple[str, ...] = ()
) -> Iterator[str]:
    """Yield paths under `root` whose extension is in `extensions`.

    Prunes SKIP_DIRS by name and any directory in `skip_paths` by path, in place,
    so pruned subtrees are never descended into. `skip_paths` is how a run keeps
    its own output directory out of a later scan when it sits inside the tree.
    Order is deterministic (sorted per directory) so scans are reproducible.
    """
    skip = {_canon(p) for p in skip_paths}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SKIP_DIRS and _canon(os.path.join(dirpath, d)) not in skip
        )
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1] in extensions:
                yield os.path.join(dirpath, filename)


def slugify(point_id: str) -> str:
    """Filesystem-safe slug for an extension point id.

    Shared by the doc generator (examples/<slug>.py) and the scaffolder
    (<slug>_plugin.py): if these two ever disagreed, generated filenames would
    stop lining up with manifest ids.
    """
    return "".join(c if c.isalnum() else "_" for c in point_id)
