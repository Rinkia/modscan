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

"""Self-check for manifest diff (breaking-change detection)."""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.diff import diff_manifests, render_diff_markdown  # noqa: E402
from modscan.cli import main  # noqa: E402


def _m(points: list[dict]) -> dict:
    return {"schema_version": "1.0", "generated_by": "modscan", "points": points}


def _p(pid: str, signature: str = "class X(ABC)", implement=None) -> dict:
    return {
        "id": pid,
        "kind": "abstract_class",
        "signature": signature,
        "implement": implement or ["def run(self)"],
    }


def test_no_change_not_breaking() -> None:
    m = _m([_p("a:A"), _p("b:B")])
    diff = diff_manifests(m, m)
    assert not diff.breaking
    assert diff.removed == [] and diff.added == [] and diff.changed == []


def test_removed_is_breaking() -> None:
    old = _m([_p("a:A"), _p("b:B")])
    new = _m([_p("a:A")])
    diff = diff_manifests(old, new)
    assert diff.breaking
    assert diff.removed == ["b:B"]


def test_added_is_safe() -> None:
    old = _m([_p("a:A")])
    new = _m([_p("a:A"), _p("c:C")])
    diff = diff_manifests(old, new)
    assert not diff.breaking
    assert diff.added == ["c:C"]


def test_signature_change_is_breaking() -> None:
    old = _m([_p("a:A", signature="class A(ABC)")])
    new = _m([_p("a:A", signature="class A(Base)")])
    diff = diff_manifests(old, new)
    assert diff.breaking
    assert diff.changed[0].id == "a:A"
    assert diff.changed[0].field == "signature"


def test_new_required_method_is_breaking() -> None:
    old = _m([_p("a:A", implement=["def run(self)"])])
    new = _m([_p("a:A", implement=["def run(self)", "def setup(self)"])])
    diff = diff_manifests(old, new)
    assert diff.breaking
    assert any(c.field == "implement" for c in diff.changed)


def test_render_markdown_mentions_verdict() -> None:
    old = _m([_p("a:A"), _p("b:B")])
    new = _m([_p("a:A")])
    md = render_diff_markdown(diff_manifests(old, new))
    assert "Breaking changes" in md
    assert "b:B" in md


def test_render_markdown_carries_sticky_marker() -> None:
    # The marker must be on the first line so a CI gate can find and update its
    # own prior comment instead of stacking a new one each re-push.
    from modscan.diff import DIFF_COMMENT_MARKER

    md = render_diff_markdown(diff_manifests(_m([_p("a:A")]), _m([_p("a:A")])))
    assert md.startswith(DIFF_COMMENT_MARKER)


# --- detect --json (flat list) shape ---------------------------------------


def _d(pid: str, category: str = "subclass", kind: str = "class", score: float = 1.0) -> dict:
    """A point in the shape `detect --json` emits: a flat item, no manifest wrapper."""
    return {"id": pid, "module": pid.split(":")[0], "category": category,
            "kind": kind, "score": score, "signals": ["public class"]}


def test_flat_detect_list_removed_is_breaking() -> None:
    """A diff can run straight off `detect --json` output — a plain list."""
    old = [_d("a:A"), _d("b:B")]
    new = [_d("a:A")]
    diff = diff_manifests(old, new)
    assert diff.breaking
    assert diff.removed == ["b:B"]


def test_flat_detect_list_added_is_safe() -> None:
    diff = diff_manifests([_d("a:A")], [_d("a:A"), _d("c:C")])
    assert not diff.breaking
    assert diff.added == ["c:C"]


def test_category_change_is_breaking() -> None:
    old = [_d("a:A", category="subclass")]
    new = [_d("a:A", category="api")]
    diff = diff_manifests(old, new)
    assert diff.breaking
    assert any(c.field == "category" for c in diff.changed)


def test_score_only_change_is_not_breaking() -> None:
    """Re-ranking without changing the set of seams must not fail the gate."""
    old = [_d("a:A", score=1.0)]
    new = [_d("a:A", score=0.4)]
    diff = diff_manifests(old, new)
    assert not diff.breaking
    assert diff.changed == []


def test_mixed_manifest_and_flat_both_index() -> None:
    """Both shapes index the same way — the manifest path is unchanged."""
    manifest = _m([_p("a:A")])
    flat = [_d("a:A")]
    # each diffed against itself is a no-op; the point is that neither raises
    assert not diff_manifests(manifest, manifest).breaking
    assert not diff_manifests(flat, flat).breaking


def test_cli_diff_exit_codes() -> None:
    with tempfile.TemporaryDirectory() as d:
        old_path = os.path.join(d, "old.json")
        new_path = os.path.join(d, "new.json")
        with open(old_path, "w", encoding="utf-8") as fh:
            json.dump(_m([_p("a:A"), _p("b:B")]), fh)
        # identical -> exit 0
        with open(new_path, "w", encoding="utf-8") as fh:
            json.dump(_m([_p("a:A"), _p("b:B")]), fh)
        assert main(["diff", old_path, new_path]) == 0
        # breaking (b:B removed) -> exit 1
        with open(new_path, "w", encoding="utf-8") as fh:
            json.dump(_m([_p("a:A")]), fh)
        assert main(["diff", old_path, new_path]) == 1
        # missing file -> exit 2
        assert main(["diff", old_path, os.path.join(d, "nope.json")]) == 2


if __name__ == "__main__":
    test_no_change_not_breaking()
    test_removed_is_breaking()
    test_added_is_safe()
    test_signature_change_is_breaking()
    test_new_required_method_is_breaking()
    test_render_markdown_mentions_verdict()
    test_flat_detect_list_removed_is_breaking()
    test_flat_detect_list_added_is_safe()
    test_category_change_is_breaking()
    test_score_only_change_is_not_breaking()
    test_mixed_manifest_and_flat_both_index()
    test_cli_diff_exit_codes()
    print("OK: diff self-check passed")
