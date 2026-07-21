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

"""Output types produced by the doc generator.

Kept in their own module so the renderer and the pipeline can both depend on
them without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modscan.factblocks import FactBlock
from modscan.models import ExampleStatus


@dataclass
class GeneratedPoint:
    fact: FactBlock
    guide: str
    example_code: str
    example_status: ExampleStatus
    example_path: str


@dataclass(frozen=True)
class DroppedPoint:
    """An extension point detected but not documented, because validating it —
    loading and exercising the seam — failed. Recorded with a classified reason
    so the run explains *why* it is thinner than the detection, instead of
    filtering silently."""

    point_id: str
    category: str
    location: str
    reason: str  # "import_failed" (often a missing dependency) | "validation_failed"
    detail: str

    @property
    def likely_missing_dependency(self) -> bool:
        return self.reason == "import_failed"


@dataclass
class DocReport:
    out_dir: str
    overview: str
    points: list[GeneratedPoint] = field(default_factory=list)
    manifest_path: str = ""
    dropped: list[DroppedPoint] = field(default_factory=list)

    @property
    def verified_count(self) -> int:
        return sum(1 for p in self.points if p.example_status == ExampleStatus.VERIFIED)
