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

from modscan.parser import parse_codebase, parse_file  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.detector import detect_extension_points  # noqa: E402


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
    "pkg/loaders.py": (
        "from werkzeug.utils import import_string\n"
        "import pkg_resources\n"
        "import importlib.util\n"
        "import pkgutil\n"
        "\n"
        "def load_by_path(path):\n"
        "    return import_string(path)\n"
        "\n"
        "def load_ep(name):\n"
        "    return pkg_resources.load_entry_point('myapp', 'myapp.plugins', name)\n"
        "\n"
        "def iter_eps():\n"
        "    return list(pkg_resources.iter_entry_points('myapp.plugins'))\n"
        "\n"
        "def legacy_load(loader, name):\n"
        "    return loader.load_module(name)\n"
        "\n"
        "def find(name):\n"
        "    return importlib.util.find_spec(name)\n"
        "\n"
        "def loader_for(name):\n"
        "    return pkgutil.get_loader(name)\n"
    ),
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


def test_new_dynamic_calls() -> None:
    """Each call added for issue #17 is captured as a dynamic import, and
    surfaces as a plugin_loader extension point once run through the graph
    and detector layers.
    """
    with tempfile.TemporaryDirectory() as root:
        _write_fixture(root)
        cb = parse_codebase(root)
        by_name = {m.qualname: m for m in cb.modules}
        loaders = by_name["pkg.loaders"]
        assert loaders.parse_error is None

        kinds = {d.kind for d in loaders.dynamic_imports}
        # import_string (Werkzeug/Django)
        assert "import_string" in kinds, kinds
        # load_entry_point / iter_entry_points (pkg_resources) both collapse
        # into the "entry_points" kind, same concept as importlib.metadata's.
        assert "entry_points" in kinds, kinds
        entry_point_calls = [d for d in loaders.dynamic_imports if d.kind == "entry_points"]
        assert len(entry_point_calls) == 2, entry_point_calls
        # load_module (legacy Loader API)
        assert "load_module" in kinds, kinds
        # find_spec (importlib.util)
        assert "find_spec" in kinds, kinds
        # get_loader (pkgutil)
        assert "get_loader" in kinds, kinds

        # --- graph + detector: each new call is a plugin_loader seam ---
        g = build_graph(cb)
        points = detect_extension_points(g)
        loader_points = [
            p for p in points if p.category == "plugin_loader" and p.seam.module == "pkg.loaders"
        ]
        seen_kinds = {p.seam.name for p in loader_points}
        for expected in ("import_string", "entry_points", "load_module", "find_spec", "get_loader"):
            assert expected in seen_kinds, (expected, seen_kinds)

    print("OK: new dynamic-call detection self-check passed")


def test_import_module_still_isolated_via_parse_file() -> None:
    """Sanity check that parse_file (used directly, not just via parse_codebase)
    also captures a new call — guards against a regression where only the
    directory-walking path was updated.
    """
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "single.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "import importlib.util\n"
                "def find(name):\n"
                "    return importlib.util.find_spec(name)\n"
            )
        mod = parse_file(path, root)
        assert any(d.kind == "find_spec" for d in mod.dynamic_imports)

    print("OK: parse_file direct-call self-check passed")


def test_override_point_detected() -> None:
    """A method raising NotImplementedError marks the method, and its class as
    having an override point. An ordinary method does not.
    """
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "bases.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "class Base:\n"
                "    def convert(self, value):\n"
                "        raise NotImplementedError('override me')\n"
                "    def helper(self):\n"
                "        return 1\n"
                "class Concrete:\n"
                "    def run(self):\n"
                "        return 2\n"
            )
        cb = parse_codebase(root)
        methods = {m.name: m for mod in cb.modules for c in mod.classes for m in c.methods}
        assert methods["convert"].raises_notimplemented is True
        assert methods["helper"].raises_notimplemented is False

        g = build_graph(cb)
        seam = {s.name: s for s in g.seams}
        assert seam["Base"].has_override_point is True
        assert seam["Concrete"].has_override_point is False

    print("OK: override-point detection self-check passed")


def test_parse_codebase_excludes_output_dir() -> None:
    """A directory passed in `exclude` is not scanned — the self-scan guard: a
    run's output living inside the tree is never parsed by a later run."""
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "real.py"), "w", encoding="utf-8") as fh:
            fh.write("class Real:\n    pass\n")
        out = os.path.join(root, "modding-docs")
        os.makedirs(os.path.join(out, "examples"))
        # a file a previous run might have generated inside the output dir
        with open(os.path.join(out, "examples", "gen_plugin.py"), "w", encoding="utf-8") as fh:
            fh.write("class Generated:\n    pass\n")

        without = parse_codebase(root)
        assert any(m.qualname.endswith("gen_plugin") for m in without.modules), \
            "sanity: without exclude, the generated file IS scanned (the hazard)"

        with_exclude = parse_codebase(root, exclude=(out,))
        names = {m.qualname for m in with_exclude.modules}
        assert "real" in names, "the real source is still scanned"
        assert not any(q.endswith("gen_plugin") for q in names), \
            "the excluded output dir is not scanned"

    print("OK: output-dir exclusion self-check passed")


def test_overload_stubs_collapse_to_one_seam() -> None:
    """A `@overload` family is one public symbol, not one per signature.

    SQLAlchemy's shape: two typing-only stubs then the implementation. Taking
    every `def` at face value made `union_all` three separate candidates ranked
    20, 21 and 22, inflating the tied bands the ranking is judged on.
    """
    source = (
        "from typing import overload\n"
        "import typing as t\n"
        "\n"
        "@overload\n"
        "def union_all(a: int) -> int: ...\n"
        "@t.overload\n"
        "def union_all(a: str) -> str: ...\n"
        "def union_all(a):\n"
        "    return a\n"
        "\n"
        "@overload\n"
        "def stub_only(a: int) -> int: ...\n"
        "@overload\n"
        "def stub_only(a: str) -> str: ...\n"
        "\n"
        "def plain():\n"
        "    return 1\n"
    )
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write(source)
        module = parse_codebase(root).modules[0]

        union = [f for f in module.functions if f.name == "union_all"]
        assert len(union) == 1, f"one seam per overloaded symbol, got {len(union)}"
        assert union[0].decorators == (), "the implementation is kept, not a stub"
        assert union[0].lineno == 8, "and it keeps the implementation's line"

        stub_only = [f for f in module.functions if f.name == "stub_only"]
        assert len(stub_only) == 1, "a stub-only symbol is deduplicated, not dropped"

        assert len([f for f in module.functions if f.name == "plain"]) == 1

    print("OK: overload-stub collapse self-check passed")


if __name__ == "__main__":
    test_parser_and_graph()
    test_new_dynamic_calls()
    test_import_module_still_isolated_via_parse_file()
    test_override_point_detected()
    test_parse_codebase_excludes_output_dir()
    test_overload_stubs_collapse_to_one_seam()
