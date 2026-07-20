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

"""Layer 4: the doc generator.

Split into focused modules — `pipeline` orchestrates, `examples` owns example
generation and the retry policy, `render` owns document/manifest output, `types`
holds the shared result objects. The public surface is unchanged: importing
`generate_docs`, `DocReport` and `GeneratedPoint` from `modscan.docgen` works
exactly as it did when this was a single module.
"""

from modscan.docgen.pipeline import generate_docs
from modscan.docgen.types import DocReport, GeneratedPoint

__all__ = ["generate_docs", "DocReport", "GeneratedPoint"]
