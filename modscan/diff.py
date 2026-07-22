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

"""Diff two extension-points.json manifests to catch breaking changes.

When a target app updates, its extension points can move, change signature, or
disappear — silently breaking every mod that relied on them. Comparing the old
and new manifests turns that into an explicit report: what's gone (breaking),
what changed (potentially breaking), and what's new (safe). Deterministic, no
LLM. Powers a CI gate that comments on the PR that would break mods.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PointChange:
    id: str
    field: str  # "signature" | "implement" | ...
    old: object
    new: object


@dataclass
class ManifestDiff:
    removed: list[str] = field(default_factory=list)  # ids gone in new (breaking)
    added: list[str] = field(default_factory=list)  # ids new in new (safe)
    changed: list[PointChange] = field(default_factory=list)  # signature/impl deltas

    @property
    def breaking(self) -> bool:
        """A removed point or a changed signature/contract can break mods."""
        return bool(self.removed) or bool(self.changed)


# Fields whose change can break an existing plugin. `signature`/`implement` come
# from the LLM-generated manifest; `kind`/`category` from a `detect --json` list.
# A field absent on both sides compares equal, so each input shape only flags the
# fields it actually carries. `score` is deliberately excluded: re-ranking a
# package without changing its set of extension points is not a breaking change.
_COMPARED_FIELDS = ("signature", "implement", "kind", "category")


def _index(data: dict | list) -> dict[str, dict]:
    """Index points by id, accepting either a `{"points": [...]}` manifest or the
    flat list that `detect --json` emits — so a diff can run off free detect
    output as well as an LLM-generated manifest."""
    points = data if isinstance(data, list) else data.get("points", [])
    return {p["id"]: p for p in points if "id" in p}


def diff_manifests(old: dict | list, new: dict | list) -> ManifestDiff:
    old_points = _index(old)
    new_points = _index(new)

    removed = sorted(set(old_points) - set(new_points))
    added = sorted(set(new_points) - set(old_points))

    changed: list[PointChange] = []
    for pid in sorted(set(old_points) & set(new_points)):
        op, np = old_points[pid], new_points[pid]
        for f in _COMPARED_FIELDS:
            if op.get(f) != np.get(f):
                changed.append(PointChange(id=pid, field=f, old=op.get(f), new=np.get(f)))

    return ManifestDiff(removed=removed, added=added, changed=changed)


def render_diff_markdown(diff: ManifestDiff) -> str:
    """Render the diff as a short Markdown report (for CLI output or PR comments)."""
    verdict = (
        "**Breaking changes to extension points**"
        if diff.breaking
        else "No breaking changes to extension points"
    )
    lines = ["## MODScan extension-point diff", "", verdict, ""]

    if diff.removed:
        lines.append("### Removed (breaking)")
        lines += [f"- `{pid}`" for pid in diff.removed]
        lines.append("")
    if diff.changed:
        lines.append("### Changed (may break plugins)")
        for c in diff.changed:
            lines.append(f"- `{c.id}` — {c.field}: `{c.old}` → `{c.new}`")
        lines.append("")
    if diff.added:
        lines.append("### Added (new extension points)")
        lines += [f"- `{pid}`" for pid in diff.added]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
