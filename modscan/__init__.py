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
]
