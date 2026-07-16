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

"""extension-points.json — the machine-readable contract.

This manifest is the higher-value output long-term: it powers scaffolding
(`modscan scaffold <id>`), editor tooling, and breaking-change diffs between two
versions of a target. It is deterministic (sorted, stable ids) and versioned so
downstream tools can rely on its shape.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # avoid an import cycle with docgen at runtime
    from modscan.docgen import GeneratedPoint

SCHEMA_VERSION = "1.0"


def _point_entry(gp: "GeneratedPoint") -> dict:
    fb = gp.fact
    return {
        "id": fb.point_id,
        "kind": fb.kind,
        "category": fb.category,
        "module": fb.module,
        "symbol": fb.symbol,
        "location": f"{fb.module}:{fb.lineno}",
        "signature": fb.signature,
        "bases": list(fb.bases),
        "decorators": list(fb.decorators),
        "implement": list(fb.implement),
        "signals": list(fb.signals),
        "validation": {"method": fb.validation_method},
        "example": {"path": gp.example_path, "status": gp.example_status},
    }


def build_manifest(target_root: str, generated: Iterable["GeneratedPoint"]) -> dict:
    points = sorted((_point_entry(gp) for gp in generated), key=lambda e: e["id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "modscan",
        "target_root": target_root,
        "points": points,
    }


def write_manifest(path: str, manifest: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
