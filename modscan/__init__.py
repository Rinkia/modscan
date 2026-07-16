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

"""MODScan — scan a codebase, generate plugin/mod documentation."""

from modscan.models import (
    Codebase,
    ModuleInfo,
    FunctionInfo,
    ClassInfo,
    ImportInfo,
    DynamicImport,
)
from modscan.parser import parse_codebase, parse_file
from modscan.graph import ExtensionGraph, Seam, build_graph
from modscan.detector import ExtensionPoint, detect_extension_points
from modscan.validator import ValidationResult, validate_point, validate_points
from modscan.factblocks import FactBlock, build_fact_block, render_fact_block
from modscan.providers import DEFAULT_MODEL, FakeProvider, Provider, get_provider
from modscan.docgen import DocReport, GeneratedPoint, generate_docs

__all__ = [
    "Codebase",
    "ModuleInfo",
    "FunctionInfo",
    "ClassInfo",
    "ImportInfo",
    "DynamicImport",
    "parse_codebase",
    "parse_file",
    "ExtensionGraph",
    "Seam",
    "build_graph",
    "ExtensionPoint",
    "detect_extension_points",
    "ValidationResult",
    "validate_point",
    "validate_points",
    "FactBlock",
    "build_fact_block",
    "render_fact_block",
    "Provider",
    "FakeProvider",
    "get_provider",
    "DEFAULT_MODEL",
    "DocReport",
    "GeneratedPoint",
    "generate_docs",
]
