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

"""Rank risk sinks and render the attack-surface report.

Ranking is severity-first, then confidence — Bandit's two axes, ordered. This is
deliberately NOT the moddability score. The report opens with an unmissable
statement of what it does NOT cover, so it can never read as a clean bill of
health (the lens's top risk).
"""

from __future__ import annotations

import json

from modscan.security.sinks import RiskSink

# Order for both axes: high sorts before medium before low.
_RANK = {"high": 0, "medium": 1, "low": 2}

# Printed at the top of every report. Kept blunt on purpose: this maps where
# untrusted code/data can ENTER; it does not prove any of it is exploitable, and
# an empty report is not a security guarantee.
_BANNER = (
    "> **Attack-surface map — NOT a vulnerability scan.** This lists where "
    "untrusted code or data can enter and execute. It does **not** trace whether "
    "input actually reaches these sinks (no taint analysis), match known CVEs, or "
    "detect secrets. **An empty or short report is not a clean bill of health** — "
    "it is a map to review by hand."
)


def rank_sinks(sinks: list[RiskSink]) -> list[RiskSink]:
    """Most dangerous first: severity, then confidence, then location."""
    return sorted(
        sinks,
        key=lambda s: (_RANK.get(s.severity, 9), _RANK.get(s.confidence, 9), s.module, s.lineno),
    )


def _counts(sinks: list[RiskSink], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in sinks:
        out[getattr(s, attr)] = out.get(getattr(s, attr), 0) + 1
    return out


def render_markdown(sinks: list[RiskSink], label: str) -> str:
    """The attack-surface report for a scanned target `label`."""
    ranked = rank_sinks(sinks)
    lines = [f"# Attack surface — `{label}`", "", _BANNER, ""]

    if not ranked:
        lines += [
            "No catalogued sinks found. This means none of the detector's known "
            "execution sinks appear as calls — **not** that the target is safe. "
            "Review dynamic behaviour and data handling by hand.",
        ]
        return "\n".join(lines) + "\n"

    sev = _counts(ranked, "severity")
    lines += [
        f"**{len(ranked)} sink(s)** — "
        + ", ".join(f"{sev.get(s, 0)} {s}" for s in ("high", "medium", "low") if sev.get(s)),
        "",
        "| Severity | Confidence | ID | Category | Location | Call |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in ranked:
        loc = f"{s.module or '(root)'}:{s.lineno}"
        lines.append(
            f"| {s.severity} | {s.confidence} | `{s.id}` | {s.category} | {loc} | `{s.dotted}` |"
        )
    return "\n".join(lines) + "\n"


def render_json(sinks: list[RiskSink], label: str) -> str:
    """Machine-readable report. Carries the same non-coverage disclaimer."""
    ranked = rank_sinks(sinks)
    payload = {
        "tool": "modscan-security",
        "target": label,
        "disclaimer": (
            "attack-surface map, not a vulnerability scan; no taint/CVE/secret "
            "coverage; absence of findings is not a clean bill of health"
        ),
        "count": len(ranked),
        "sinks": [
            {
                "id": s.id, "category": s.category, "severity": s.severity,
                "confidence": s.confidence, "module": s.module, "call": s.dotted,
                "lineno": s.lineno, "detail": s.detail,
            }
            for s in ranked
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
