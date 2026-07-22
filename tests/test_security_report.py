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

"""Self-check for the security lens report + CLI (M2)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.security.cli import main  # noqa: E402
from modscan.security.report import rank_sinks, render_json, render_markdown  # noqa: E402
from modscan.security.sinks import RiskSink  # noqa: E402

_HIGH = RiskSink("MS-SEC-EVAL", "code_exec", "high", "high", "m", "eval", 5)
_MED = RiskSink("MS-SEC-SUBPROCESS", "process", "medium", "medium", "m", "subprocess.run", 2)
_LOW = RiskSink("MS-SEC-ENTRYPOINTS", "dynamic_load", "low", "medium", "m", "x.entry_points", 9)

_FIXTURE = "import pickle\n\n\ndef f(b):\n    return pickle.loads(b)\n"


def test_ranking_severity_first() -> None:
    ranked = rank_sinks([_LOW, _MED, _HIGH])
    assert [s.severity for s in ranked] == ["high", "medium", "low"]


def test_report_always_states_non_coverage() -> None:
    # the disclaimer must appear whether or not sinks were found
    full = render_markdown([_HIGH], "pkg")
    empty = render_markdown([], "pkg")
    for report in (full, empty):
        assert "NOT a vulnerability scan" in report
        assert "not a clean bill of health" in report.lower()
    assert "1 sink(s)" in full
    assert "`MS-SEC-EVAL`" in full


def test_json_report_shape() -> None:
    data = json.loads(render_json([_HIGH, _LOW], "pkg"))
    assert data["target"] == "pkg"
    assert data["count"] == 2
    assert data["disclaimer"]  # present and non-empty
    assert data["sinks"][0]["severity"] == "high"  # ranked


def test_cli_runs_and_reports(capsys_free: bool = True) -> None:
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write(_FIXTURE)

        # Markdown to stdout, exit 0
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = main([root, "--label", "demo"])
        finally:
            sys.stdout = old
        out = buf.getvalue()
        assert code == 0
        assert "Attack surface — `demo`" in out
        assert "MS-SEC-PICKLE" in out
        assert "NOT a vulnerability scan" in out

        # JSON path
        buf = io.StringIO()
        sys.stdout = buf
        try:
            code = main([root, "--json", "--label", "demo"])
        finally:
            sys.stdout = old
        data = json.loads(buf.getvalue())
        assert code == 0
        assert data["count"] == 1 and data["sinks"][0]["id"] == "MS-SEC-PICKLE"

    # bad path -> exit 2
    assert main(["/no/such/dir/xyz"]) == 2


if __name__ == "__main__":
    test_ranking_severity_first()
    test_report_always_states_non_coverage()
    test_json_report_shape()
    test_cli_runs_and_reports()
    print("OK: security report + CLI self-check passed")
