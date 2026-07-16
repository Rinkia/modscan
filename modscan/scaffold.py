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

"""Task 6: scaffold a plugin skeleton from the extension-points.json manifest.

This is where the machine-readable manifest pays off. Given a point id, emit a
ready-to-edit plugin file: a concrete subclass with stubbed abstract methods, or
a usage template for hook/registration points. Fully deterministic — reads the
facts, writes code, no LLM involved.
"""

from __future__ import annotations

import json
import os


def load_manifest(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_point(manifest: dict, point_id: str) -> dict:
    """Return the manifest entry for `point_id`, or raise with the valid ids."""
    for point in manifest.get("points", []):
        if point.get("id") == point_id:
            return point
    ids = ", ".join(p.get("id", "?") for p in manifest.get("points", [])) or "(none)"
    raise ValueError(f"point id {point_id!r} not found in manifest; available: {ids}")


def _method_name(sig: str) -> str:
    # sig looks like "def export(self, data, fmt)"
    inner = sig[len("def ") :] if sig.startswith("def ") else sig
    return inner.split("(", 1)[0].strip() or "method"


def _render_subclass(point: dict) -> str:
    module, symbol = point["module"], point["symbol"]
    cls_name = f"My{symbol}"
    lines = [
        f"from {module} import {symbol}",
        "",
        "",
        f"class {cls_name}({symbol}):",
        f'    """Plugin skeleton for {point["id"]}, scaffolded by MODScan."""',
    ]
    implement = point.get("implement", [])
    if implement:
        for sig in implement:
            name = _method_name(sig)
            lines.append("")
            lines.append(f"    {sig}:")
            lines.append(f'        raise NotImplementedError("TODO: implement {name}")')
    else:
        lines.append("")
        lines.append("    pass  # TODO: override methods to customize behavior")
    return "\n".join(lines) + "\n"


def _render_template(point: dict) -> str:
    """Fallback for non-subclass points: import the symbol and show its facts."""
    module, symbol = point["module"], point["symbol"]
    sig = point.get("signature", "")
    lines = [
        f"from {module} import {symbol}",
        "",
        "",
        f"# Extension point: {point['id']} ({point.get('category', '')})",
    ]
    if sig:
        lines.append(f"# Target signature: {sig}")
    lines += [
        f"# TODO: use {symbol} to register or invoke your plugin.",
        "",
        "def my_plugin():",
        '    raise NotImplementedError("TODO: implement your plugin")',
    ]
    return "\n".join(lines) + "\n"


def render_scaffold(point: dict) -> str:
    if point.get("kind") in ("class", "abstract_class"):
        return _render_subclass(point)
    return _render_template(point)


def _safe(point_id: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in point_id)


def _write_point(point: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{_safe(point['id'])}_plugin.py")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_scaffold(point))
    return path


def scaffold(manifest_path: str, point_id: str, out_dir: str = ".") -> str:
    """Write a plugin skeleton for `point_id`. Returns the written file path."""
    manifest = load_manifest(manifest_path)
    point = find_point(manifest, point_id)
    return _write_point(point, out_dir)


def scaffold_all(manifest_path: str, out_dir: str = ".") -> list[str]:
    """Write a plugin skeleton for every point in the manifest.

    Returns the list of written file paths (sorted by point id).
    """
    manifest = load_manifest(manifest_path)
    points = sorted(manifest.get("points", []), key=lambda p: p.get("id", ""))
    return [_write_point(point, out_dir) for point in points]
