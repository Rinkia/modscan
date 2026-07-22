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


def test_detect_label_replaces_scan_path_in_header() -> None:
    """--label puts a clean name in the header instead of the scan path, so
    committed or shared output leaks no local filesystem path."""
    import io
    from contextlib import redirect_stdout

    pkg = "clilabel"
    with tempfile.TemporaryDirectory() as root:
        _write_pkg(root, pkg)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["detect", root, "--label", "clilabel 9.9.9"])
            out = buf.getvalue()
            assert code == 0
            assert "# Extension points in `clilabel 9.9.9`" in out
            assert root not in out, "the scan path must not appear when --label is set"
        finally:
            _cleanup(pkg)


def test_run_fails_fast_on_missing_dependency() -> None:
    """A target whose deps aren't installed stops before any LLM call, with a
    classified cause — not empty docs."""
    from modscan.preflight import PreflightError

    pkg = "clideps"
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, pkg)
        os.makedirs(d)
        with open(os.path.join(d, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write("import totally_absent_dep_xyz\n")
        with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
            fh.write("class Sink:\n    def write(self, item): ...\n")
        try:
            args = build_parser().parse_args([root, "--out", os.path.join(root, "o")])

            def responder(system: str, prompt: str) -> str:
                raise AssertionError("no LLM call should happen before preflight")

            raised = False
            try:
                run(args, FakeProvider(responder))
            except PreflightError as exc:
                raised = True
                assert "totally_absent_dep_xyz" in str(exc)
                assert "pip install" in str(exc)
            assert raised, "expected PreflightError"
        finally:
            _cleanup(pkg)


def test_dropped_points_are_classified_and_reported() -> None:
    """A point whose module fails to import (missing dep) is dropped with reason
    'import_failed', counted in the report, and shown in index.md — not silent."""
    from modscan.docgen import generate_docs

    pkg = "clidropped"
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, pkg)
        os.makedirs(d)
        # top-level package imports cleanly -> preflight passes
        open(os.path.join(d, "__init__.py"), "w").close()
        # but this module needs an absent dependency, so validating its seam fails
        with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
            fh.write(
                "import totally_absent_dep_xyz\n"
                "__all__ = ['Sink']\n"
                "class Sink:\n    def write(self, item): ...\n"
            )
        try:
            out = os.path.join(root, "o")
            report = generate_docs(root, FakeProvider(lambda s, p: "prose"), out, min_score=0.0)
            assert report.dropped, "the un-importable seam should be recorded, not silent"
            sink = [d for d in report.dropped if d.point_id.endswith(":Sink")]
            assert sink and sink[0].reason == "import_failed", report.dropped

            index = open(os.path.join(out, "index.md"), encoding="utf-8").read()
            assert "## Not documented" in index
            assert "dependencies are not installed" in index
        finally:
            _cleanup(pkg)


def test_is_inside_detects_output_in_scan_tree() -> None:
    from modscan.cli import _is_inside

    with tempfile.TemporaryDirectory() as root:
        assert _is_inside(os.path.join(root, "docs"), root)
        assert _is_inside(os.path.join(root, "a", "b"), root)
        assert not _is_inside(root, os.path.join(root, "docs"))
        with tempfile.TemporaryDirectory() as other:
            assert not _is_inside(other, root)


def test_consecutive_runs_are_independent() -> None:
    """Two runs of two different packages that share a module name must not see
    each other's cached module — run isolation."""
    from modscan.docgen import generate_docs

    def one(pkg: str, marker: str) -> str:
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, pkg)
            os.makedirs(d)
            with open(os.path.join(d, "__init__.py"), "w", encoding="utf-8") as fh:
                fh.write(f"from {pkg}.api import Sink\n__all__ = ['Sink']\n")
            with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
                fh.write(
                    f"MARKER = '{marker}'\n"
                    "class Sink:\n    def write(self, item): ...\n"
                )
            try:
                out = os.path.join(root, "o")
                generate_docs(root, FakeProvider(lambda s, p: "prose"), out, min_score=0.0)
                # the module the run imported carries this run's marker
                import sys as _sys
                return getattr(_sys.modules.get(f"{pkg}.api"), "MARKER", None)
            finally:
                _cleanup(pkg)

    # same package name across two runs; without isolation the second import
    # would return the first run's cached module
    a = one("dupname", "run-a")
    b = one("dupname", "run-b")
    # after each run, its module is cleaned up, so neither leaks to the process
    assert "dupname.api" not in sys.modules


def test_no_validate_examples_skips_preflight() -> None:
    """Opting out of executing target code also skips the probe (which imports)."""
    pkg = "clidepsskip"
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, pkg)
        os.makedirs(d)
        with open(os.path.join(d, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write("import totally_absent_dep_xyz\n")
        with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
            fh.write("__all__ = ['Sink']\nclass Sink:\n    def write(self, item): ...\n")
        try:
            args = build_parser().parse_args(
                [root, "--out", os.path.join(root, "o"), "--no-validate-examples"]
            )
            # No preflight, so the run proceeds and the FakeProvider is used.
            code = run(args, FakeProvider(lambda s, p: "prose"))
            assert code == 0
        finally:
            _cleanup(pkg)


def test_detect_separates_and_dedups_registration_points() -> None:
    """entry_points loader sites go in their own section, deduplicated, out of the
    implement-this ranking."""
    import io
    from contextlib import redirect_stdout

    pkg = "cliregister"
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, pkg)
        os.makedirs(d)
        open(os.path.join(d, "__init__.py"), "w").close()
        with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
            fh.write("class Sink:\n    def write(self, item): ...\n")
        # two entry_points call-sites in one module -> one deduplicated row
        with open(os.path.join(d, "loader.py"), "w", encoding="utf-8") as fh:
            fh.write(
                "from importlib.metadata import entry_points\n"
                "def load_a():\n    return entry_points(group='a')\n"
                "def load_b():\n    return entry_points(group='b')\n"
            )
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                assert main(["detect", root, "--min-score", "0.0"]) == 0
            out = buf.getvalue()

            assert "## Plugin registration points" in out
            head, _, reg = out.partition("## Plugin registration points")
            assert "Sink" in head, "implement-this seam belongs in the main table"
            assert "entry_points" not in head, "loader must not be in the main table"
            assert "entry_points" in reg
            # deduplicated: the two call-sites collapse to a single row
            assert reg.count("| `entry_points`") == 1, reg
        finally:
            _cleanup(pkg)


if __name__ == "__main__":
    test_parser_defaults()
    test_run_with_fake_provider()
    test_main_bad_root()
    test_detect_subcommand_no_llm()
    test_detect_bad_root()
    test_detect_label_replaces_scan_path_in_header()
    test_detect_separates_and_dedups_registration_points()
    test_run_fails_fast_on_missing_dependency()
    test_dropped_points_are_classified_and_reported()
    test_is_inside_detects_output_in_scan_tree()
    test_consecutive_runs_are_independent()
    test_no_validate_examples_skips_preflight()
    print("OK: cli self-check passed")
