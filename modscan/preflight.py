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

"""Pre-flight import probe.

Before a documentation run does expensive work, check whether the target
actually imports. A target whose own dependencies are not installed produces
thin or empty docs — every example fails to load and is filtered out silently.
The probe surfaces that once, up front, with a remediation, instead of letting
the run grind to an empty result.

Like validation, this IMPORTS (and therefore executes) target code. It is only
run when the caller has already consented to executing the target — it never
introduces an execution path the user has not agreed to.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from modscan.execution import sys_path
from modscan.graph import top_level_packages
from modscan.models import Codebase


class PreflightError(Exception):
    """Raised when the target cannot be imported, to stop a run before it spends
    LLM calls producing empty docs. Carries the classified cause + remediation."""

    def __init__(self, result: "PreflightResult") -> None:
        super().__init__(result.message)
        self.result = result


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of probing whether the target imports.

    ``ok`` True means the run may proceed. Otherwise ``reason`` classifies the
    failure and ``message`` is a user-facing cause plus remediation.
    """

    ok: bool
    reason: str = "ok"  # "ok" | "missing_dependency" | "target_not_importable" | "import_error"
    message: str = ""
    missing_module: str | None = None


def _remediation(reason: str, missing_module: str | None) -> str:
    if reason == "missing_dependency":
        pkg = (missing_module or "").split(".")[0]
        return (
            f"'{missing_module}' is not installed. Install the target's "
            f"dependencies — e.g. `pip install {pkg}`, or `pip install -e .` in "
            "the target's checkout — then re-run."
        )
    if reason == "target_not_importable":
        return (
            "The target package could not be imported. Install it in this "
            "environment (`pip install -e .` in its checkout) so its modules "
            "resolve, then re-run."
        )
    return "Fix the import error above in the target, then re-run."


def probe_target(codebase: Codebase, root: str) -> PreflightResult:
    """Try to import each top-level package of the scanned tree.

    Classifies the first failure:

    - a ``ModuleNotFoundError`` naming a module that is not one of the target's
      own top-level packages is a **missing dependency**;
    - failure to import the target's own package is **target_not_importable**;
    - anything else is reported verbatim as an unclassified **import_error** —
      never dressed up as a missing dependency it might not be.

    A target with no importable top-level package (e.g. scanned as a bare
    directory with no package __init__) has nothing to probe and passes; the run
    itself will still surface per-point failures.
    """
    packages = top_level_packages(codebase)
    own_names = {m.qualname for m in packages if m.qualname}
    if not own_names:
        return PreflightResult(ok=True)

    with sys_path(root):
        for qualname in sorted(own_names):
            try:
                importlib.import_module(qualname)
            except ModuleNotFoundError as exc:
                missing = exc.name or ""
                top = missing.split(".")[0]
                if top and top not in own_names:
                    reason = "missing_dependency"
                    msg = (
                        f"Importing '{qualname}' failed: missing module "
                        f"'{missing}'. {_remediation(reason, missing)}"
                    )
                    return PreflightResult(False, reason, msg, missing)
                reason = "target_not_importable"
                return PreflightResult(
                    False, reason,
                    f"Importing '{qualname}' failed: {exc!r}. {_remediation(reason, None)}",
                )
            except Exception as exc:  # noqa: BLE001 — report verbatim, do not classify
                reason = "import_error"
                return PreflightResult(
                    False, reason,
                    f"Importing '{qualname}' raised {exc!r}. {_remediation(reason, None)}",
                )
    return PreflightResult(ok=True)
