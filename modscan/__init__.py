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

import logging as _logging
from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
from importlib.metadata import version as _metadata_version

try:
    __version__ = _metadata_version("modscan")
except _PackageNotFoundError:  # running from a source checkout, not installed
    __version__ = "0.0.0+unknown"

# Library convention: attach a NullHandler so importing modscan never configures
# logging or prints to stderr on its own. Applications (and the CLI) opt in by
# configuring handlers themselves.
_logging.getLogger(__name__).addHandler(_logging.NullHandler())

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
from modscan.scaffold import render_scaffold, scaffold, scaffold_all
from modscan.sandbox import validate_in_sandbox
from modscan.diff import ManifestDiff, PointChange, diff_manifests, render_diff_markdown
from modscan.languages import (
    LanguageParser,
    available_languages,
    get_language_parser,
    register_language,
)
from modscan.config_scan import ConfigPoint, find_config_points, render_config_markdown

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
    "scaffold",
    "scaffold_all",
    "render_scaffold",
    "validate_in_sandbox",
    "ManifestDiff",
    "PointChange",
    "diff_manifests",
    "render_diff_markdown",
    "LanguageParser",
    "available_languages",
    "get_language_parser",
    "register_language",
    "ConfigPoint",
    "find_config_points",
    "render_config_markdown",
]
