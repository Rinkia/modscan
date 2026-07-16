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

"""Self-check for layer 1 (parser) + layer 2 (extension graph).

Runs without pytest: `python tests/test_parser.py`. Also discoverable by pytest.
Builds a tiny synthetic plugin-style package on disk, parses it, and asserts the
facts and seams come out right.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.parser import parse_codebase  # noqa: E402
from modscan.graph import build_graph  # noqa: E402


FIXTURE = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "from abc import ABC, abstractmethod\n"
        "import importlib\n"
        "\n"
        "__all__ = ['Plugin', 'register']\n"
        "\n"
        "class Plugin(ABC):\n"
        "    @abstractmethod\n"
        "    def run(self):\n"
        "        ...\n"
        "\n"
        "class _Internal:\n"
        "    pass\n"
        "\n"
        "def register(name):\n"
        "    return name\n"
        "\n"
        "def _helper():\n"
        "    return 1\n"
        "\n"
        "def load(mod_name):\n"
        "    return importlib.import_module(mod_name)\n"
    ),
    "pkg/plugins.py": (
        "from pkg.core import Plugin, register\n"
        "\n"
        "@register\n"
        "class Greeter(Plugin):\n"
        "    def run(self):\n"
        "        return 'hi'\n"
    ),
    "pkg/broken.py": "def oops(:\n",  # syntax error on purpose
}


def _write_fixture(root: str) -> None:
    for rel, content in FIXTURE.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def test_parser_and_graph() -> None:
    with tempfile.TemporaryDirectory() as root:
        _write_fixture(root)
        cb = parse_codebase(root)

        by_name = {m.qualname: m for m in cb.modules}

        # broken file is captured, not fatal
        assert "pkg.broken" in by_name
        assert by_name["pkg.broken"].parse_error is not None
        assert len(cb.failed_modules) == 1

        core = by_name["pkg.core"]
        assert core.parse_error is None

        # __all__ drives public surface: register public, _helper/load hidden
        pub_fns = {f.name for f in core.public_functions}
        assert pub_fns == {"register"}, pub_fns

        # Plugin is public (in __all__) and detected abstract (ABC + abstractmethod)
        classes = {c.name: c for c in core.classes}
        assert classes["Plugin"].is_abstract is True
        assert classes["Plugin"].is_public is True
        assert classes["_Internal"].is_public is False

        # dynamic import via importlib.import_module is captured
        kinds = {d.kind for d in core.dynamic_imports}
        assert "import_module" in kinds, kinds

        # decorator on Greeter is recorded
        greeter = {c.name: c for c in by_name["pkg.plugins"].classes}["Greeter"]
        assert "register" in greeter.decorators
        assert "Plugin" in greeter.bases

        # --- graph ---
        g = build_graph(cb)

        # pkg.plugins depends on pkg.core (internal edge resolved)
        assert "pkg.core" in g.dependencies["pkg.plugins"]

        # Plugin shows up as a subclassable seam
        abstract_names = {s.name for s in g.subclassable}
        assert "Plugin" in abstract_names, abstract_names

        # dynamic import site is in the seam inventory
        assert any(s.kind == "dynamic_import" for s in g.seams)

    print("OK: parser + graph self-check passed")


if __name__ == "__main__":
    test_parser_and_graph()
