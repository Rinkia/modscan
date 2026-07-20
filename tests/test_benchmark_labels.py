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

"""Integrity check for the ranking benchmark's ground truth.

Runs without pytest: `python tests/test_benchmark_labels.py`. Offline and
dependency-free — it only reads the labels file, so it can never make CI flaky.

This does NOT score anything. It guards the labels themselves: pinned versions,
well-formed ids, and a justification behind every claim. A label without
evidence is an opinion, and opinions are what this benchmark exists to remove.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GROUND_TRUTH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "benchmarks",
    "ground_truth.json",
)

# Seams MODScan currently ranks at the top of these targets but which are NOT
# real extension points. If any of these ever appears as a label, the labels
# were derived from MODScan's output instead of from documentation — which
# would make the benchmark measure nothing.
KNOWN_FALSE_POSITIVES = {
    "sqlalchemy.engine.cursor:NoCursorFetchStrategy",
    "sqlalchemy.engine.cursor:CursorFetchStrategy",
    "sqlalchemy.testing.fixtures.sql:TablesTest",
    "sqlalchemy.testing.fixtures.base:TestBase",
    "pluggy._callers:run_old_style_hookwrapper",
    "pluggy._hooks:normalize_hookimpl_opts",
}

# Seams MODScan currently MISSES entirely. The labels must contain them —
# otherwise the benchmark has nothing to detect an improvement against.
MUST_BE_LABELLED = {
    "pluggy._manager:PluginManager",
    "pluggy._hooks:HookimplMarker",
    "sqlalchemy.sql.type_api:TypeDecorator",
}


def _load() -> dict:
    with open(GROUND_TRUTH, encoding="utf-8") as fh:
        return json.load(fh)


def test_file_is_well_formed() -> None:
    data = _load()
    assert data.get("schema_version"), "schema_version missing"
    assert data.get("labelling_rule"), "the rule must travel with the labels"
    targets = data.get("targets")
    assert targets, "no targets"
    assert len(targets) >= 3, f"expected at least 3 targets, got {len(targets)}"


def test_every_target_pins_a_version() -> None:
    """Labels are only valid for the version they were derived from."""
    for name, target in _load()["targets"].items():
        version = target.get("version")
        assert version, f"{name}: no pinned version"
        # a bare major or a range is not a pin
        assert version.count(".") >= 2, f"{name}: version {version!r} is not exact"
        assert not any(c in version for c in "<>=~^*"), f"{name}: {version!r} is a range"


def test_every_label_is_well_formed_and_justified() -> None:
    for name, target in _load()["targets"].items():
        points = target.get("extension_points")
        assert points, f"{name}: no extension points labelled"

        seen = set()
        for point in points:
            pid = point.get("id", "")
            assert ":" in pid, f"{name}: id {pid!r} is not 'module:Symbol'"
            module, _, symbol = pid.partition(":")
            assert module and symbol, f"{name}: id {pid!r} has an empty half"
            assert module.startswith(name), (
                f"{name}: id {pid!r} does not belong to this target"
            )
            assert pid not in seen, f"{name}: duplicate label {pid!r}"
            seen.add(pid)

            justification = point.get("justification", "").strip()
            assert justification, f"{pid}: no justification — a label needs evidence"
            assert len(justification) > 40, (
                f"{pid}: justification too thin to be checkable: {justification!r}"
            )


def test_labels_were_not_derived_from_modscan_output() -> None:
    """The benchmark is worthless if the labels agree with today's ranking.

    Two directions are checked: seams MODScan wrongly promotes must be absent,
    and seams it currently misses must be present.
    """
    labelled = {
        point["id"]
        for target in _load()["targets"].values()
        for point in target["extension_points"]
    }

    contaminated = labelled & KNOWN_FALSE_POSITIVES
    assert not contaminated, (
        f"labels contain seams MODScan wrongly ranks highly: {sorted(contaminated)}. "
        "These were almost certainly copied from MODScan's output rather than "
        "derived from the package's documentation."
    )

    missing = MUST_BE_LABELLED - labelled
    assert not missing, (
        f"labels omit seams MODScan currently misses: {sorted(missing)}. "
        "Without them the benchmark cannot detect the improvement it exists for."
    )


if __name__ == "__main__":
    test_file_is_well_formed()
    test_every_target_pins_a_version()
    test_every_label_is_well_formed_and_justified()
    test_labels_were_not_derived_from_modscan_output()
    print("OK: benchmark ground-truth self-check passed")
