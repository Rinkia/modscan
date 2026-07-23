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

"""Self-check for the attack-surface diff (gate M1)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.security.cli import main  # noqa: E402
from modscan.security.surface_diff import (  # noqa: E402
    SURFACE_DIFF_MARKER,
    diff_surfaces,
    render_surface_diff_markdown,
)


def _sink(sid: str, module: str, call: str, lineno: int, severity: str = "high") -> dict:
    return {
        "id": sid, "category": "code_exec", "severity": severity,
        "confidence": "high", "module": module, "call": call, "lineno": lineno,
    }


def _snap(sinks: list[dict], target: str = "pkg") -> dict:
    return {"tool": "modscan-security", "target": target, "count": len(sinks), "sinks": sinks}


def test_added_occurrence_of_existing_sink_is_caught() -> None:
    """The counted-multiset rule: 2 evals -> 3 evals is one introduced sink."""
    base = _snap([_sink("MS-SEC-EVAL", "m", "eval", 3), _sink("MS-SEC-EVAL", "m", "eval", 9)])
    new = _snap([
        _sink("MS-SEC-EVAL", "m", "eval", 3),
        _sink("MS-SEC-EVAL", "m", "eval", 9),
        _sink("MS-SEC-EVAL", "m", "eval", 21),
    ])
    diff = diff_surfaces(base, new)
    assert diff.has_new_surface
    assert len(diff.introduced) == 1
    assert diff.introduced[0].count == 1
    assert diff.introduced[0].id == "MS-SEC-EVAL"
    assert not diff.removed


def test_line_shift_alone_is_not_a_change() -> None:
    """Line numbers are excluded from identity, so moved code never false-diffs."""
    base = _snap([_sink("MS-SEC-PICKLE", "m", "pickle.loads", 10)])
    new = _snap([_sink("MS-SEC-PICKLE", "m", "pickle.loads", 400)])
    diff = diff_surfaces(base, new)
    assert not diff.introduced and not diff.removed
    assert not diff.has_new_surface


def test_new_sink_type_and_removal() -> None:
    base = _snap([_sink("MS-SEC-EVAL", "m", "eval", 3)])
    new = _snap([_sink("MS-SEC-PICKLE", "m", "pickle.loads", 5, severity="high")])
    diff = diff_surfaces(base, new)
    assert [c.id for c in diff.introduced] == ["MS-SEC-PICKLE"]
    assert [c.id for c in diff.removed] == ["MS-SEC-EVAL"]


def test_accepts_bare_list_shape() -> None:
    base: list[dict] = []
    new = [_sink("MS-SEC-EVAL", "m", "eval", 1)]
    assert diff_surfaces(base, new).has_new_surface


def test_render_carries_marker_and_disclaimer() -> None:
    empty = render_surface_diff_markdown(diff_surfaces(_snap([]), _snap([])), "pkg")
    full = render_surface_diff_markdown(
        diff_surfaces(_snap([]), _snap([_sink("MS-SEC-EVAL", "m", "eval", 1)])), "pkg"
    )
    for report in (empty, full):
        assert report.startswith(SURFACE_DIFF_MARKER)  # sticky-comment anchor, line 1
        assert "NOT a vulnerability verdict" in report
    assert "not that the change" in empty.lower()  # empty never claims safety
    assert "1 new execution sink(s)" in full
    assert "Introduced" in full


def test_cli_diff_and_scan_still_work() -> None:
    old = sys.stdout
    with tempfile.TemporaryDirectory() as root:
        base_p = os.path.join(root, "base.json")
        new_p = os.path.join(root, "pr.json")
        with open(base_p, "w", encoding="utf-8") as fh:
            json.dump(_snap([]), fh)
        with open(new_p, "w", encoding="utf-8") as fh:
            json.dump(_snap([_sink("MS-SEC-EVAL", "m", "eval", 1)]), fh)

        buf = io.StringIO()
        sys.stdout = buf
        try:
            code = main(["--diff", base_p, new_p, "--label", "demo"])
        finally:
            sys.stdout = old
        out = buf.getvalue()
        assert code == 0  # M1 reports only; failing on new sinks is M2
        assert SURFACE_DIFF_MARKER in out and "MS-SEC-EVAL" in out and "demo" in out

        # regression: the released `modscan-audit <root>` form still works
        with open(os.path.join(root, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write("import pickle\n\n\ndef f(b):\n    return pickle.loads(b)\n")
        buf = io.StringIO()
        sys.stdout = buf
        try:
            code = main([root, "--label", "demo"])
        finally:
            sys.stdout = old
        assert code == 0 and "Attack surface" in buf.getvalue()

    assert main(["--diff", "/nope/a.json", "/nope/b.json"]) == 2  # missing snapshot
    assert main([]) == 2  # neither a path nor --diff


if __name__ == "__main__":
    test_added_occurrence_of_existing_sink_is_caught()
    test_line_shift_alone_is_not_a_change()
    test_new_sink_type_and_removal()
    test_accepts_bare_list_shape()
    test_render_carries_marker_and_disclaimer()
    test_cli_diff_and_scan_still_work()
    print("OK: attack-surface diff self-check passed")
