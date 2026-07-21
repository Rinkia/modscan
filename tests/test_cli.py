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

"""Self-check for the CLI. run() is driven with a FakeProvider — no network."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.cli import build_parser, main, run  # noqa: E402
from modscan.providers import FakeProvider  # noqa: E402

API_SRC = (
    "from abc import ABC, abstractmethod\n"
    "__all__ = ['Sink']\n"
    "class Sink(ABC):\n"
    "    @abstractmethod\n"
    "    def write(self, item): ...\n"
)


def _write_pkg(root: str, pkg: str) -> None:
    d = os.path.join(root, pkg)
    os.makedirs(d)
    open(os.path.join(d, "__init__.py"), "w").close()
    with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
        fh.write(API_SRC)


def _cleanup(pkg: str) -> None:
    for name in list(sys.modules):
        if name == pkg or name.startswith(pkg + "."):
            del sys.modules[name]


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["/some/path"])
    assert args.root == "/some/path"
    assert args.out == "modding-docs"
    assert args.provider == "anthropic"
    assert args.min_score == 0.5
    assert args.retries == 4
    assert args.no_validate_examples is False


def test_run_with_fake_provider() -> None:
    pkg = "clifix"
    with tempfile.TemporaryDirectory() as root:
        _write_pkg(root, pkg)
        try:
            out = os.path.join(root, "modding-docs")
            args = build_parser().parse_args([root, "--out", out, "--min-score", "0.5"])

            def responder(system: str, prompt: str) -> str:
                if "EXAMPLE plugin" in prompt:
                    return (
                        f"```python\nfrom {pkg}.api import Sink\n"
                        "class MySink(Sink):\n"
                        "    def write(self, item):\n"
                        "        return item\n```"
                    )
                return "prose"

            code = run(args, FakeProvider(responder))
            assert code == 0
            assert os.path.isfile(os.path.join(out, "index.md"))
            assert os.path.isfile(os.path.join(out, "extension-points.json"))
        finally:
            _cleanup(pkg)


def test_main_bad_root() -> None:
    assert main(["C:/no/such/dir/modscan-xyz"]) == 2


def test_detect_subcommand_no_llm() -> None:
    """`modscan detect` ranks extension points offline — no provider, no network."""
    import io
    from contextlib import redirect_stdout

    pkg = "clidetect"
    with tempfile.TemporaryDirectory() as root:
        _write_pkg(root, pkg)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["detect", root, "--min-score", "0.3"])
            out = buf.getvalue()
            assert code == 0
            assert "Sink" in out, out  # the abstract base is surfaced
            assert "Extension points" in out

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["detect", root, "--json"])
            assert code == 0
            payload = __import__("json").loads(buf.getvalue())
            assert any(p["id"].endswith(":Sink") for p in payload), payload
        finally:
            _cleanup(pkg)


def test_detect_bad_root() -> None:
    assert main(["detect", "C:/no/such/dir/modscan-xyz"]) == 2


if __name__ == "__main__":
    test_parser_defaults()
    test_run_with_fake_provider()
    test_main_bad_root()
    test_detect_subcommand_no_llm()
    test_detect_bad_root()
    print("OK: cli self-check passed")
