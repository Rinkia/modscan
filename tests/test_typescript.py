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

"""Self-check for the TypeScript/JavaScript front-end.

Skips cleanly (exit 0) when tree-sitter is not installed, so the core CI — which
installs no optional deps — stays green. Install to run:
    pip install modscan[typescript]
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HAVE_TS = (
    importlib.util.find_spec("tree_sitter") is not None
    and importlib.util.find_spec("tree_sitter_typescript") is not None
)

from modscan.languages import available_languages, get_language_parser  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.detector import detect_extension_points  # noqa: E402

TS_SRC = """
import { Core } from './core';

export interface RenderPlugin {
  load(world): void;
  render(scene): string;
}

export abstract class BaseMod extends Core {
  abstract onTick(dt): void;
}

export function registerPlugin(fn) { return fn; }

class Hidden {}
"""


def test_ts_and_js_registered() -> None:
    langs = available_languages()
    assert "typescript" in langs
    assert "javascript" in langs


def test_ts_parses_into_seams() -> int:
    if not _HAVE_TS:
        print("SKIP: typescript front-end (pip install modscan[typescript] to run)")
        return 0

    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "plugin.ts"), "w", encoding="utf-8") as fh:
            fh.write(TS_SRC)
        cb = get_language_parser("typescript").parse_codebase(root)

        module = cb.modules[0]
        classes = {c.name: c for c in module.classes}
        # interface + abstract class are captured; abstract-ness set
        assert classes["RenderPlugin"].is_abstract is True
        assert classes["RenderPlugin"].is_public is True
        assert classes["BaseMod"].is_abstract is True
        assert "Core" in classes["BaseMod"].bases
        # non-exported class is private
        assert classes["Hidden"].is_public is False
        # exported function captured and public
        funcs = {f.name: f for f in module.functions}
        assert funcs["registerPlugin"].is_public is True

        # the language-agnostic detector finds real seams
        points = {p.seam.name: p for p in detect_extension_points(build_graph(cb), min_score=0.4)}
        assert points["RenderPlugin"].category == "subclass"
        assert points["registerPlugin"].category == "registration"
        assert "Hidden" not in points  # private, filtered out
    return 0


if __name__ == "__main__":
    test_ts_and_js_registered()
    test_ts_parses_into_seams()
    print("OK: typescript self-check passed")
