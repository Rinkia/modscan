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

"""Diff two attack-surface snapshots to find sinks a change *introduced*.

A one-shot audit tells you where you are today; comparing two snapshots tells you
what a pull request added. Sinks are identified by ``(id, module, call)`` and
compared as a **counted multiset**: the line number is deliberately excluded, so
shifting code never registers as a change, while adding a third ``eval`` to a
module that already had two still shows up as one introduced sink.

Deterministic, offline, no LLM. Still enumeration: an introduced sink is new
attack surface to review, not a proven vulnerability.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Own marker, distinct from the moddability gate's, so a repo running both gates
# gets two independently-updating comments instead of one overwriting the other.
SURFACE_DIFF_MARKER = "<!-- modscan-attack-surface-diff -->"

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Thresholds a gate can fail on. "high" is the recommended default: measured
# across real packages, the medium tier is dominated by routine `__reduce__`,
# dynamic imports and subprocess calls — normal code for a plugin host — while
# the high tier (eval/exec/pickle.loads/yaml.load/os.system) is rare and a new
# occurrence genuinely warrants a review conversation.
FAIL_ON_CHOICES = ("none", "high", "medium", "low")

_DISCLAIMER = (
    "> **New attack surface to review — NOT a vulnerability verdict.** This "
    "compares enumerated execution sinks between two snapshots. It does **not** "
    "trace whether input reaches them (no taint analysis), match CVEs, or detect "
    "secrets. **An empty diff means no new catalogued sinks — not that the change "
    "is safe.**"
)


@dataclass(frozen=True)
class SurfaceChange:
    """One sink identity whose occurrence count changed between snapshots."""

    id: str
    module: str
    call: str
    category: str
    severity: str
    count: int  # how many occurrences were added (introduced) or dropped (removed)


@dataclass
class SurfaceDiff:
    introduced: list[SurfaceChange] = field(default_factory=list)
    removed: list[SurfaceChange] = field(default_factory=list)

    @property
    def has_new_surface(self) -> bool:
        """True when the change adds execution sinks (what a gate keys off)."""
        return bool(self.introduced)


def _sinks(data: dict | list) -> list[dict]:
    """Accept a ``modscan-audit --json`` payload or a bare list of sinks.

    Mirrors how ``modscan diff`` takes either a manifest or a flat detect list, so
    a caller can pipe whichever shape it already has.
    """
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    sinks = data.get("sinks", [])
    return [s for s in sinks if isinstance(s, dict)]


def _key(sink: dict) -> tuple[str, str, str]:
    """Location-insensitive identity: line numbers move, the sink is the same."""
    return (sink.get("id", ""), sink.get("module", ""), sink.get("call", ""))


def _meta(sinks: list[dict]) -> dict[tuple[str, str, str], dict]:
    """First-seen category/severity per key, to decorate the diff output."""
    out: dict[tuple[str, str, str], dict] = {}
    for s in sinks:
        out.setdefault(_key(s), s)
    return out


def _changes(
    delta: Counter, meta: dict[tuple[str, str, str], dict]
) -> list[SurfaceChange]:
    changes = [
        SurfaceChange(
            id=key[0], module=key[1], call=key[2],
            category=meta.get(key, {}).get("category", ""),
            severity=meta.get(key, {}).get("severity", ""),
            count=count,
        )
        for key, count in delta.items()
        if count > 0
    ]
    changes.sort(key=lambda c: (_SEVERITY_ORDER.get(c.severity, 9), c.module, c.call))
    return changes


def diff_surfaces(base: dict | list, new: dict | list) -> SurfaceDiff:
    """Sinks the `new` snapshot adds over `base` (and those it drops)."""
    base_sinks, new_sinks = _sinks(base), _sinks(new)
    base_counts = Counter(_key(s) for s in base_sinks)
    new_counts = Counter(_key(s) for s in new_sinks)

    meta = {**_meta(base_sinks), **_meta(new_sinks)}
    return SurfaceDiff(
        introduced=_changes(new_counts - base_counts, meta),
        removed=_changes(base_counts - new_counts, meta),
    )


def introduced_at_or_above(diff: SurfaceDiff, threshold: str) -> list[SurfaceChange]:
    """Introduced sinks at least as severe as `threshold`.

    ``"none"`` never selects anything (report-only). ``"high"`` selects only high;
    ``"medium"`` selects high+medium; ``"low"`` selects everything.
    """
    if threshold == "none":
        return []
    limit = _SEVERITY_ORDER.get(threshold)
    if limit is None:
        return []
    return [c for c in diff.introduced if _SEVERITY_ORDER.get(c.severity, 9) <= limit]


def _rows(changes: list[SurfaceChange]) -> list[str]:
    lines = ["| Severity | ID | Category | Module | Call | Count |",
             "| --- | --- | --- | --- | --- | --- |"]
    lines += [
        f"| {c.severity} | `{c.id}` | {c.category} | {c.module or '(root)'} | "
        f"`{c.call}` | {c.count} |"
        for c in changes
    ]
    return lines


def render_surface_diff_markdown(diff: SurfaceDiff, label: str) -> str:
    """Markdown report for a CI comment. Marker first, disclaimer always."""
    verdict = (
        f"**{sum(c.count for c in diff.introduced)} new execution sink(s)**"
        if diff.introduced
        else "No new execution sinks"
    )
    lines = [
        SURFACE_DIFF_MARKER,
        f"## MODScan attack-surface diff — `{label}`",
        "",
        verdict,
        "",
        _DISCLAIMER,
        "",
    ]

    if diff.introduced:
        lines += ["### Introduced (new attack surface)", ""] + _rows(diff.introduced) + [""]
    if diff.removed:
        lines += ["### Removed", ""] + _rows(diff.removed) + [""]
    if not diff.introduced and not diff.removed:
        lines += ["The two snapshots enumerate the same execution sinks.", ""]

    return "\n".join(lines).rstrip() + "\n"
