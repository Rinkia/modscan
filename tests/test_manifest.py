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

"""Self-check for the JSON manifest: stable shape, deterministic, round-trips."""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.factblocks import FactBlock  # noqa: E402
from modscan.docgen import GeneratedPoint  # noqa: E402
from modscan.manifest import SCHEMA_VERSION, build_manifest, write_manifest  # noqa: E402


def _gp(module: str, symbol: str, status: str) -> GeneratedPoint:
    fb = FactBlock(
        module=module,
        symbol=symbol,
        kind="abstract_class",
        category="subclass",
        lineno=10,
        signature=f"class {symbol}(ABC)",
        bases=("ABC",),
        decorators=(),
        implement=("def run(self)",),
        signals=("abstract",),
        validation_method="subclass_instantiation",
    )
    return GeneratedPoint(
        fact=fb,
        guide="g",
        example_code="code",
        example_status=status,
        example_path=f"examples/{module}_{symbol}.py",
    )


def test_manifest() -> None:
    # deliberately out of order to prove the manifest sorts by id
    generated = [_gp("z.mod", "Zeta", "verified"), _gp("a.mod", "Alpha", "unverified")]
    manifest = build_manifest("/target", generated)

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["generated_by"] == "modscan"
    ids = [p["id"] for p in manifest["points"]]
    assert ids == ["a.mod:Alpha", "z.mod:Zeta"], ids  # sorted

    alpha = manifest["points"][0]
    assert alpha["category"] == "subclass"
    assert alpha["implement"] == ["def run(self)"]
    assert alpha["validation"]["method"] == "subclass_instantiation"
    assert alpha["example"]["status"] == "unverified"

    # deterministic: rebuilding yields identical JSON
    assert json.dumps(build_manifest("/target", generated), sort_keys=True) == json.dumps(
        manifest, sort_keys=True
    )

    # round-trips through disk
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "extension-points.json")
        write_manifest(path, manifest)
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded == manifest

    print("OK: manifest self-check passed")


if __name__ == "__main__":
    test_manifest()
