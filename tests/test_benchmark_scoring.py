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

"""Self-check for the benchmark scorer's maths.

Runs without pytest: `python tests/test_benchmark_scoring.py`. Exercises only
the pure functions against synthetic ranks, so it needs none of the target
packages installed and stays safe under CI's `tests/test_*.py` glob. Scoring a
real target is `python benchmarks/score.py`, which is run by hand.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "benchmarks"))

from score import median_rank, normalise_id, precision_at_k, recall_at_k  # noqa: E402


def test_normalise_id_qualifies_a_relative_module() -> None:
    """The mismatch that made the first hand-run report 0 of 12 labels found."""
    assert normalise_id("pluggy", "_manager", "PluginManager") == "pluggy._manager:PluginManager"
    assert normalise_id("sqlalchemy", "engine.cursor", "X") == "sqlalchemy.engine.cursor:X"


def test_normalise_id_leaves_an_already_qualified_module_alone() -> None:
    """Must be idempotent — otherwise a second pass yields pluggy.pluggy._manager."""
    once = normalise_id("pluggy", "pluggy._manager", "PluginManager")
    assert once == "pluggy._manager:PluginManager"
    assert normalise_id("pluggy", once.split(":")[0], "PluginManager") == once


def test_normalise_id_handles_the_package_root() -> None:
    """A seam defined in __init__.py has an empty or bare-package module path."""
    assert normalise_id("click", "", "Command") == "click:Command"
    assert normalise_id("click", "click", "Command") == "click:Command"


def test_recall_counts_labels_not_slots() -> None:
    ranks = {"a": 1, "b": 5, "c": 40}
    assert recall_at_k(ranks, 10) == (2, 3)
    assert recall_at_k(ranks, 1) == (1, 3)
    assert recall_at_k(ranks, 100) == (3, 3)


def test_precision_is_out_of_k_and_so_has_a_ceiling() -> None:
    """Five labels can never fill ten slots — the reason precision is not the headline."""
    perfect = {f"label{i}": i for i in range(1, 6)}
    hits, out_of = precision_at_k(perfect, 10)
    assert (hits, out_of) == (5, 10)
    assert hits / out_of == 0.5, "a perfect ranker still scores 0.5 — do not optimise this"


def test_median_rank_matches_the_published_baseline() -> None:
    """The figures committed in benchmarks/README.md, recomputed."""
    assert median_rank({"a": 5, "b": 6, "c": 14}) == 6  # pluggy
    assert median_rank({"a": 1, "b": 2, "c": 38, "d": 39}) == 20  # click: (2+38)/2
    assert median_rank({"a": 620, "b": 1287, "c": 1369, "d": 1628, "e": 1631}) == 1369


def test_a_lost_seam_cannot_improve_the_median() -> None:
    """Absent labels are counted at candidates+1, not dropped.

    Dropping them would let a change that stops detecting a seam entirely look
    like an improvement, which is the opposite of what the benchmark is for.
    """
    before = median_rank({"a": 5, "b": 6, "c": 14})
    lost_counted_at_candidates_plus_one = median_rank({"a": 5, "b": 6, "c": 21})
    assert lost_counted_at_candidates_plus_one >= before, "counting a lost seam must not flatter"

    if_it_were_dropped = median_rank({"a": 5, "b": 6})
    assert if_it_were_dropped < before, "dropping a lost seam would flatter the score"


if __name__ == "__main__":
    test_normalise_id_qualifies_a_relative_module()
    test_normalise_id_leaves_an_already_qualified_module_alone()
    test_normalise_id_handles_the_package_root()
    test_recall_counts_labels_not_slots()
    test_precision_is_out_of_k_and_so_has_a_ceiling()
    test_median_rank_matches_the_published_baseline()
    test_a_lost_seam_cannot_improve_the_median()
    print("OK: benchmark scoring self-check passed")
