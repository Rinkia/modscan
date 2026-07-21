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

"""Self-check for the pre-flight import probe. Offline, no network, no pytest."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.parser import parse_codebase  # noqa: E402
from modscan.preflight import probe_target  # noqa: E402


def _cleanup(pkg: str) -> None:
    for name in list(sys.modules):
        if name == pkg or name.startswith(pkg + "."):
            del sys.modules[name]


def _write(root: str, pkg: str, init_body: str) -> None:
    d = os.path.join(root, pkg)
    os.makedirs(d)
    with open(os.path.join(d, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write(init_body)
    with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
        fh.write("class Sink:\n    def write(self, item): ...\n")


def test_missing_dependency_is_named() -> None:
    """A package whose __init__ imports an absent module is a missing dependency."""
    pkg = "preflightdep"
    with tempfile.TemporaryDirectory() as root:
        _write(root, pkg, "import totally_absent_dep_xyz\n")
        try:
            result = probe_target(parse_codebase(root), root)
            assert not result.ok
            assert result.reason == "missing_dependency", result
            assert result.missing_module == "totally_absent_dep_xyz", result
            assert "pip install" in result.message
        finally:
            _cleanup(pkg)


def test_clean_target_passes() -> None:
    """A package that imports cleanly may proceed."""
    pkg = "preflightok"
    with tempfile.TemporaryDirectory() as root:
        _write(root, pkg, "from preflightok.api import Sink\n__all__ = ['Sink']\n")
        try:
            result = probe_target(parse_codebase(root), root)
            assert result.ok, result
        finally:
            _cleanup(pkg)


def test_own_broken_import_is_not_called_a_missing_dependency() -> None:
    """A package importing a *sibling* module that does not exist points at the
    target itself, not a third-party dependency."""
    pkg = "preflightself"
    with tempfile.TemporaryDirectory() as root:
        _write(root, pkg, "from preflightself.nope_missing import thing\n")
        try:
            result = probe_target(parse_codebase(root), root)
            assert not result.ok
            # the missing module is under the target's own namespace, so it is
            # classified as the target not importing, not a missing dependency
            assert result.reason == "target_not_importable", result
        finally:
            _cleanup(pkg)


def test_no_package_nothing_to_probe() -> None:
    """A bare directory with no package __init__ has nothing to import; pass."""
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "loose.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        result = probe_target(parse_codebase(root), root)
        assert result.ok, result


if __name__ == "__main__":
    test_missing_dependency_is_named()
    test_clean_target_passes()
    test_own_broken_import_is_not_called_a_missing_dependency()
    test_no_package_nothing_to_probe()
    print("OK: preflight self-check passed")
