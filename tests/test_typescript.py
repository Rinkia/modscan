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


_CJS_SRC = """\
const EventEmitter = require('events');

class Command extends EventEmitter {
  createCommand(name) { return new Command(name); }
}

class Help {
  formatHelp(cmd) { return ''; }
}

class Internal {}

function makeOption(flags) { return flags; }
function privateHelper() { return 1; }

exports.Command = Command;
exports.makeOption = makeOption;
module.exports.Help = Help;
"""


def test_commonjs_exports_are_public() -> int:
    """CommonJS is most of npm; without recognising `exports.X = X` every such
    file reports zero public symbols and contributes no seams at all."""
    if not _HAVE_TS:
        print("SKIP: typescript front-end (pip install modscan[typescript] to run)")
        return 0

    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "command.js"), "w", encoding="utf-8") as fh:
            fh.write(_CJS_SRC)
        cb = get_language_parser("typescript").parse_codebase(root)
        module = cb.modules[0]

        public_classes = {c.name for c in module.public_classes}
        assert "Command" in public_classes, "exports.Command = Command not recognised"
        assert "Help" in public_classes, "module.exports.Help = Help not recognised"
        # a class that is never exported stays private
        assert "Internal" not in public_classes

        public_funcs = {f.name for f in module.public_functions}
        assert "makeOption" in public_funcs
        assert "privateHelper" not in public_funcs
    return 0


def test_generate_docs_typescript() -> int:
    """generate_docs(language='typescript') produces static docs (no execution)."""
    if not _HAVE_TS:
        print("SKIP: typescript docgen (pip install modscan[typescript] to run)")
        return 0

    import json

    from modscan.docgen import generate_docs
    from modscan.providers import FakeProvider

    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "plugin.ts"), "w", encoding="utf-8") as fh:
            fh.write(TS_SRC)
        out = os.path.join(root, "modding-docs")
        provider = FakeProvider(
            lambda s, p: "class MyMod extends BaseMod {}" if "EXAMPLE" in p else "prose"
        )
        report = generate_docs(root, provider, out, min_score=0.4, language="typescript")

        assert report.points, "expected TS extension points documented"
        # non-executing language -> examples are 'generated', never validated
        assert all(p.example_status == "generated" for p in report.points)
        # examples written with a .ts extension
        assert all(p.example_path.endswith(".ts") for p in report.points)
        assert os.path.isfile(os.path.join(out, "extension-points.json"))

        with open(os.path.join(out, "extension-points.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        ids = {pt["id"] for pt in manifest["points"]}
        assert any("RenderPlugin" in i for i in ids)
    return 0


if __name__ == "__main__":
    test_ts_and_js_registered()
    test_ts_parses_into_seams()
    test_commonjs_exports_are_public()
    test_generate_docs_typescript()
    print("OK: typescript self-check passed")
