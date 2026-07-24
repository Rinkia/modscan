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

"""Self-check for the usage cross-check's counting.

Runs without pytest and without any downstream package installed: the counting
functions take parsed modules, so synthetic ones are enough. Running the real
check is `python usage-crosscheck/crosscheck_usage.py`, by hand.
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "usage-crosscheck"))

from crosscheck_usage import base_tail, count_usage  # noqa: E402

from modscan.models import ClassInfo, ImportInfo, ModuleInfo  # noqa: E402


def test_base_tail_normalises_every_way_a_plugin_names_a_base() -> None:
    """Four spellings, one symbol — a plugin may write any of them."""
    for spelling in ("Field", "fields.Field", "ma.fields.Field", "Field[int]"):
        assert base_tail(spelling) == "Field", spelling


def _module(classes=(), imports=()) -> ModuleInfo:
    return ModuleInfo(qualname="plug", path="plug.py", classes=list(classes),
                      imports=list(imports))


def test_count_usage_finds_subclasses_and_imports_of_host_symbols() -> None:
    known = {"Field", "Schema", "ValidationError"}
    modules = [
        _module(
            classes=[ClassInfo(name="MyField", lineno=1, is_public=True,
                               bases=("ma.fields.Field",))],
            imports=[ImportInfo(module="marshmallow", name="ValidationError",
                                fromlist=True)],
        )
    ]
    subclassed, imported = count_usage(modules, known)
    assert subclassed == {"Field"}
    assert imported == {"ValidationError"}


def test_a_symbol_the_host_does_not_define_is_ignored() -> None:
    """Plugins subclass plenty of things; only the host's own symbols count."""
    modules = [
        _module(classes=[ClassInfo(name="X", lineno=1, is_public=True,
                                   bases=("object", "SomeOtherLib.Base"))])
    ]
    assert count_usage(modules, {"Field"}) == (set(), set())


def test_one_package_is_one_vote_however_often_it_subclasses() -> None:
    """Counting occurrences would let a single large plugin outvote an ecosystem."""
    modules = [
        _module(classes=[
            ClassInfo(name=f"F{i}", lineno=i, is_public=True, bases=("Field",))
            for i in range(40)
        ])
    ]
    subclassed, _ = count_usage(modules, {"Field"})
    assert subclassed == {"Field"}, "a set, not a tally — the caller counts packages"


def test_pinned_downstream_lists_are_wellformed() -> None:
    """The lockfile of this check: every host pins a version and its plugins."""
    path = os.path.join(_ROOT, "usage-crosscheck", "downstream.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["hosts"], "no hosts pinned"
    for host, spec in data["hosts"].items():
        assert spec["version"], f"{host} has no pinned version"
        assert spec["why"], f"{host} does not say why it is in the sample"
        assert spec["downstream"], f"{host} pins no downstream packages"
        for name, version in spec["downstream"].items():
            assert version, f"{host}/{name} is unpinned"


if __name__ == "__main__":
    test_base_tail_normalises_every_way_a_plugin_names_a_base()
    test_count_usage_finds_subclasses_and_imports_of_host_symbols()
    test_a_symbol_the_host_does_not_define_is_ignored()
    test_one_package_is_one_vote_however_often_it_subclasses()
    test_pinned_downstream_lists_are_wellformed()
    print("OK: usage cross-check self-check passed")
