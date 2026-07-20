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

"""Config / data-driven extension surface detection.

The easiest mods are often just data: dropping a JSON/YAML file into a plugins
directory, or editing a manifest the app reads at startup. Those surfaces are
invisible to the AST detector (no code seam), so this pass looks at file and
directory names instead — manifest-looking data files and conventional
plugin/mod/data directories. Deterministic, name-based, no parsing of contents.

ponytail: pure name heuristics, no schema inference. It points a modder at
"here's where data-driven extension likely lives"; reading the actual schema is
a follow-up if it proves useful.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from modscan.fsutil import SKIP_DIRS

# File stems that read like a plugin/mod manifest or registry.
_CONFIG_STEMS = {
    "plugins", "plugin", "mods", "mod", "config", "manifest", "registry",
    "extensions", "addons", "settings", "modules",
}
# Data file extensions a modder would edit.
_DATA_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
# Directory names that conventionally hold drop-in data/plugins.
_DATA_DIRS = {"plugins", "mods", "addons", "extensions", "data", "content"}


@dataclass(frozen=True)
class ConfigPoint:
    path: str  # path relative to the scan root
    kind: str  # "manifest_file" | "data_dir"
    reason: str


def find_config_points(root: str) -> list[ConfigPoint]:
    root = os.path.abspath(root)
    points: list[ConfigPoint] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for d in dirnames:
            if d.lower() in _DATA_DIRS:
                rel = os.path.relpath(os.path.join(dirpath, d), root).replace(os.sep, "/")
                points.append(
                    ConfigPoint(rel, "data_dir", f"'{d}/' is a conventional drop-in directory")
                )

        for fn in filenames:
            stem, ext = os.path.splitext(fn)
            if stem.lower() in _CONFIG_STEMS and ext.lower() in _DATA_EXTS:
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                points.append(
                    ConfigPoint(rel, "manifest_file", f"'{fn}' looks like a data-driven manifest")
                )

    points.sort(key=lambda p: (p.kind, p.path))
    return points


def render_config_markdown(points: list[ConfigPoint]) -> str:
    lines = ["## Config / data-driven extension surfaces", ""]
    if not points:
        lines.append("None found.")
        return "\n".join(lines) + "\n"
    for p in points:
        lines.append(f"- `{p.path}` ({p.kind}) - {p.reason}")
    return "\n".join(lines) + "\n"
