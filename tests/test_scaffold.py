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

"""Self-check for scaffold — deterministic plugin skeleton from the manifest."""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.scaffold import (  # noqa: E402
    find_point,
    render_scaffold,
    scaffold,
    scaffold_all,
    verify_all,
    verify_point,
)
from modscan.cli import main  # noqa: E402

MANIFEST = {
    "schema_version": "1.0",
    "generated_by": "modscan",
    "target_root": "/t",
    "points": [
        {
            "id": "pkg.api:Exporter",
            "kind": "abstract_class",
            "category": "subclass",
            "module": "pkg.api",
            "symbol": "Exporter",
            "signature": "class Exporter(ABC)",
            "bases": ["ABC"],
            "decorators": [],
            "implement": ["def export(self, data, fmt)", "def name(self)"],
        },
        {
            "id": "pkg.api:register",
            "kind": "function",
            "category": "registration",
            "module": "pkg.api",
            "symbol": "register",
            "signature": "def register(fn)",
            "implement": [],
        },
    ],
}


def _write_manifest(root: str) -> str:
    path = os.path.join(root, "extension-points.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(MANIFEST, fh)
    return path


def test_render_subclass_is_valid_python() -> None:
    code = render_scaffold(MANIFEST["points"][0])
    assert "from pkg.api import Exporter" in code
    assert "class MyExporter(Exporter):" in code
    assert "def export(self, data, fmt):" in code
    assert "def name(self):" in code
    assert code.count("NotImplementedError") == 2
    compile(code, "<scaffold>", "exec")  # must be syntactically valid


def test_render_template_for_function() -> None:
    code = render_scaffold(MANIFEST["points"][1])
    assert "from pkg.api import register" in code
    assert "def register(fn)" in code  # signature shown as a fact
    compile(code, "<scaffold>", "exec")


def test_scaffold_writes_file() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest_path = _write_manifest(root)
        out = os.path.join(root, "gen")
        path = scaffold(manifest_path, "pkg.api:Exporter", out)
        assert os.path.isfile(path)
        assert path.endswith("pkg_api_Exporter_plugin.py")
        compile(open(path, encoding="utf-8").read(), path, "exec")


def test_find_point_unknown_lists_ids() -> None:
    try:
        find_point(MANIFEST, "nope:nope")
    except ValueError as exc:
        assert "pkg.api:Exporter" in str(exc)  # helpful: lists valid ids
    else:
        raise AssertionError("expected ValueError")


def test_cli_scaffold_subcommand() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest_path = _write_manifest(root)
        out = os.path.join(root, "out")
        code = main(["scaffold", "pkg.api:Exporter", "--manifest", manifest_path, "--out", out])
        assert code == 0
        assert os.path.isfile(os.path.join(out, "pkg_api_Exporter_plugin.py"))

        # missing manifest -> exit 2
        assert main(["scaffold", "x:y", "--manifest", os.path.join(root, "nope.json")]) == 2
        # unknown id -> exit 1
        assert main(["scaffold", "x:y", "--manifest", manifest_path]) == 1


def test_scaffold_all_writes_every_point() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest_path = _write_manifest(root)
        out = os.path.join(root, "gen")
        paths = scaffold_all(manifest_path, out)
        assert len(paths) == 2
        names = sorted(os.path.basename(p) for p in paths)
        assert names == ["pkg_api_Exporter_plugin.py", "pkg_api_register_plugin.py"]
        for p in paths:
            compile(open(p, encoding="utf-8").read(), p, "exec")


def test_cli_scaffold_all_and_missing_id() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest_path = _write_manifest(root)
        out = os.path.join(root, "out")
        assert main(["scaffold", "--all", "--manifest", manifest_path, "--out", out]) == 0
        assert len(os.listdir(out)) == 2
        # neither an id nor --all -> exit 2
        assert main(["scaffold", "--manifest", manifest_path]) == 2


# --- verification -----------------------------------------------------------
# A real importable target: a package whose base actually imports and subclasses,
# so verification exercises the validator end-to-end (no LLM, fully offline).

_FIXTURE_API = '''\
from abc import ABC, abstractmethod


class Exporter(ABC):
    @abstractmethod
    def export(self, data, fmt): ...

    @abstractmethod
    def name(self): ...


def register(fn):
    return fn
'''


def _write_fixture_target(root: str) -> dict:
    """Create pkg/api.py under `root` and return a manifest pointed at it."""
    os.makedirs(os.path.join(root, "pkg"), exist_ok=True)
    open(os.path.join(root, "pkg", "__init__.py"), "w").close()
    with open(os.path.join(root, "pkg", "api.py"), "w", encoding="utf-8") as fh:
        fh.write(_FIXTURE_API)
    manifest = json.loads(json.dumps(MANIFEST))  # deep copy
    manifest["target_root"] = root
    for p in manifest["points"]:
        p["location"] = f"{p['module']}:1"
    return manifest


def test_verify_all_passes_on_real_target() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest = _write_fixture_target(root)
        results = verify_all(manifest)
        assert len(results) == 2
        assert all(r.ok for r in results), [(r.method, r.detail) for r in results]
        methods = {r.point.seam.name: r.method for r in results}
        assert methods["Exporter"] == "subclass_instantiation"
        assert methods["register"] == "importable_callable"


def test_verify_point_fails_on_missing_symbol() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest = _write_fixture_target(root)
        # point at a symbol that does not exist in the target
        manifest["points"][0]["symbol"] = "DoesNotExist"
        result = verify_point(manifest, "pkg.api:Exporter")
        assert not result.ok
        assert result.method == "error"
        assert "import failed" in result.detail


def test_cli_scaffold_verify_exit_codes() -> None:
    with tempfile.TemporaryDirectory() as root:
        manifest = _write_fixture_target(root)
        manifest_path = os.path.join(root, "extension-points.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        out = os.path.join(root, "out")
        # verify a good target -> exit 0
        assert main(["scaffold", "--all", "--manifest", manifest_path, "--out", out, "--verify"]) == 0

        # break one point -> verify exits 1
        manifest["points"][0]["symbol"] = "DoesNotExist"
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        assert main(["scaffold", "--all", "--manifest", manifest_path, "--out", out, "--verify"]) == 1


if __name__ == "__main__":
    test_render_subclass_is_valid_python()
    test_render_template_for_function()
    test_scaffold_writes_file()
    test_find_point_unknown_lists_ids()
    test_cli_scaffold_subcommand()
    test_scaffold_all_writes_every_point()
    test_cli_scaffold_all_and_missing_id()
    test_verify_all_passes_on_real_target()
    test_verify_point_fails_on_missing_symbol()
    test_cli_scaffold_verify_exit_codes()
    print("OK: scaffold self-check passed")
