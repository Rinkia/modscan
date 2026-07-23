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

"""Risk-sink catalog for TypeScript / JavaScript.

Same shape as the Python catalog (`sinks.py`): stable ``MS-SEC-*`` ids rated by
severity x confidence, enumeration only. Ids are reused where the sink is the
same concept in both languages (``eval`` is ``MS-SEC-EVAL`` either way).

Modelled on `eslint-plugin-security`, the JS counterpart to Bandit. Two of its
rules shaped this catalog directly:

* ``detect-non-literal-require`` — only a *computed* ``require``/``import``
  argument is dynamic loading. ``require('fs')`` is a static import and
  ubiquitous; flagging every one would bury the report. This is stricter than the
  Python side, where ``import_module`` is flagged regardless, because the base
  rates differ by ecosystem.
* ``detect-child-process`` — the node child_process family.

Where this catalog goes further: eslint-plugin-security has no rule for
``new Function`` or the ``vm`` module, both of which execute code from a string.
Its rules outside the execution-sink scope (unsafe regex, object injection,
timing attacks, fs filenames) are deliberately not mirrored — the lens does not
claim them.
"""

from __future__ import annotations

from modscan.security.sinks import (
    CODE_EXEC,
    DYNAMIC_LOAD,
    HIGH,
    LOW,
    MEDIUM,
    PROCESS,
    SinkSpec,
)

# --- module-qualified sinks -------------------------------------------------
# Keyed by the *member* name on a known module binding (see MODULE_SINKS below),
# so `child_process.exec(...)`, `cp.exec(...)` and a destructured `exec(...)` all
# resolve to the same entry once the binding is known.
CHILD_PROCESS_SINKS: dict[str, SinkSpec] = {
    # these hand the command to a shell
    "exec": SinkSpec("MS-SEC-CHILDPROC", PROCESS, HIGH, HIGH),
    "execSync": SinkSpec("MS-SEC-CHILDPROC", PROCESS, HIGH, HIGH),
    # these do not
    "spawn": SinkSpec("MS-SEC-CHILDPROC-NOSHELL", PROCESS, MEDIUM, MEDIUM),
    "spawnSync": SinkSpec("MS-SEC-CHILDPROC-NOSHELL", PROCESS, MEDIUM, MEDIUM),
    "execFile": SinkSpec("MS-SEC-CHILDPROC-NOSHELL", PROCESS, MEDIUM, MEDIUM),
    "execFileSync": SinkSpec("MS-SEC-CHILDPROC-NOSHELL", PROCESS, MEDIUM, MEDIUM),
    "fork": SinkSpec("MS-SEC-CHILDPROC-NOSHELL", PROCESS, MEDIUM, MEDIUM),
}

VM_SINKS: dict[str, SinkSpec] = {
    "runInThisContext": SinkSpec("MS-SEC-VM", CODE_EXEC, HIGH, MEDIUM),
    "runInNewContext": SinkSpec("MS-SEC-VM", CODE_EXEC, HIGH, MEDIUM),
    "runInContext": SinkSpec("MS-SEC-VM", CODE_EXEC, HIGH, MEDIUM),
    "compileFunction": SinkSpec("MS-SEC-VM", CODE_EXEC, HIGH, MEDIUM),
    "Script": SinkSpec("MS-SEC-VM", CODE_EXEC, HIGH, MEDIUM),
}

# Node module name -> its member catalog. Bindings of these modules are tracked
# per file (import or require), which is what makes destructured and aliased
# usage resolve — the idiomatic JS forms a name-only match would miss.
MODULE_SINKS: dict[str, dict[str, SinkSpec]] = {
    "child_process": CHILD_PROCESS_SINKS,
    "node:child_process": CHILD_PROCESS_SINKS,
    "vm": VM_SINKS,
    "node:vm": VM_SINKS,
}

# --- global sinks (no module binding needed) --------------------------------
GLOBAL_SINKS: dict[str, SinkSpec] = {
    "eval": SinkSpec("MS-SEC-EVAL", CODE_EXEC, HIGH, HIGH),
    # `Function(src)` and `new Function(src)` both evaluate a string.
    "Function": SinkSpec("MS-SEC-JSFUNCTION", CODE_EXEC, HIGH, HIGH),
}

# --- argument-conditional sinks ---------------------------------------------
# Dynamic loaders: a sink only when the argument is NOT a string literal
# (eslint-plugin-security's detect-non-literal-require).
DYNAMIC_LOADERS: dict[str, SinkSpec] = {
    "require": SinkSpec("MS-SEC-DYNREQUIRE", DYNAMIC_LOAD, MEDIUM, MEDIUM),
    "import": SinkSpec("MS-SEC-DYNREQUIRE", DYNAMIC_LOAD, MEDIUM, MEDIUM),
}

# Timers evaluate a *string* first argument as code; a function argument is the
# normal, safe form, so only the string form is a sink.
STRING_TIMERS: dict[str, SinkSpec] = {
    "setTimeout": SinkSpec("MS-SEC-STRINGTIMER", CODE_EXEC, MEDIUM, LOW),
    "setInterval": SinkSpec("MS-SEC-STRINGTIMER", CODE_EXEC, MEDIUM, LOW),
}


def all_ts_specs() -> list[SinkSpec]:
    """Every distinct spec in the TS catalog (for integrity checks / docs)."""
    seen: dict[str, SinkSpec] = {}
    for table in (
        CHILD_PROCESS_SINKS, VM_SINKS, GLOBAL_SINKS, DYNAMIC_LOADERS, STRING_TIMERS,
    ):
        for spec in table.values():
            seen[spec.id] = spec
    return list(seen.values())
