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

"""Self-check for the subprocess sandbox. Spawns child processes; no network."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.sandbox import validate_in_sandbox  # noqa: E402

API_SRC = (
    "from abc import ABC, abstractmethod\n"
    "__all__ = ['Sink']\n"
    "class Sink(ABC):\n"
    "    @abstractmethod\n"
    "    def write(self, item): ...\n"
)


def _make_pkg() -> str:
    root = tempfile.mkdtemp()
    d = os.path.join(root, "sbx")
    os.makedirs(d)
    open(os.path.join(d, "__init__.py"), "w").close()
    with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
        fh.write(API_SRC)
    return root


def test_sandbox_accepts_valid_subclass() -> None:
    root = _make_pkg()
    code = (
        "from sbx.api import Sink\n"
        "class MySink(Sink):\n"
        "    def write(self, item):\n"
        "        return item\n"
    )
    assert validate_in_sandbox(root, "sbx.api", "Sink", code, "abstract_class") is True


def test_sandbox_rejects_non_subclass() -> None:
    root = _make_pkg()
    code = "x = 1\n"  # loads fine but defines no Sink subclass
    assert validate_in_sandbox(root, "sbx.api", "Sink", code, "abstract_class") is False


def test_sandbox_rejects_bad_import() -> None:
    root = _make_pkg()
    code = "import definitely_not_a_real_module_xyz\n"
    assert validate_in_sandbox(root, "sbx.api", "Sink", code, "abstract_class") is False


def test_sandbox_kills_hang_on_timeout() -> None:
    root = _make_pkg()
    code = "while True:\n    pass\n"  # would hang forever in-process
    assert (
        validate_in_sandbox(root, "sbx.api", "Sink", code, "abstract_class", timeout=2)
        is False
    )


def test_host_and_sandbox_agree() -> None:
    """The in-process and sandboxed paths must return the same verdict.

    They now share one implementation (modscan.execution.validate_example) —
    the sandbox child imports it rather than carrying a copy. This test could
    not be written while the logic was duplicated in a string literal.
    """
    from modscan.execution import validate_example

    root = _make_pkg()
    cases = [
        # (code, kind) -> both paths must agree
        ("from sbx.api import Sink\nclass S(Sink):\n    def write(self, i):\n        return i\n", "abstract_class"),
        ("x = 1\n", "abstract_class"),                       # no subclass
        ("import definitely_not_real_xyz\n", "abstract_class"),  # bad import
        ("from sbx.api import Sink\n", "function"),          # non-class seam, loads
        ("import definitely_not_real_xyz\n", "function"),    # non-class seam, fails
    ]
    for code, kind in cases:
        host = validate_example(root, "sbx.api", "Sink", code, kind)
        child = validate_in_sandbox(root, "sbx.api", "Sink", code, kind)
        assert host == child, (kind, code, host, child)


if __name__ == "__main__":
    test_sandbox_accepts_valid_subclass()
    test_sandbox_rejects_non_subclass()
    test_sandbox_rejects_bad_import()
    test_sandbox_kills_hang_on_timeout()
    test_host_and_sandbox_agree()
    print("OK: sandbox self-check passed")
