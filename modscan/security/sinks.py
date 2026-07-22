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

"""The risk-sink catalog + fact type for the security lens.

A *sink* is a call (or, for `__reduce__`, a method definition) through which
untrusted code or data can reach code execution. The catalog is modelled on
Bandit: each entry has a stable ID (namespace ``MS-SEC-*``), a risk category,
and a two-axis **severity x confidence** rating. This is deliberately NOT the
moddability ``_W_*`` weight-sum — a different question (how dangerous, not how
extensible) gets a different rating.

Detection is enumeration only: it locates the sink, it does not trace whether
attacker-controlled data actually reaches it (that is taint analysis, out of
scope). Treat the output as *attack surface to review*, never a clean bill.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- severity / confidence (Bandit's two axes) ------------------------------
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# --- risk categories --------------------------------------------------------
CODE_EXEC = "code_exec"            # eval/exec/compile — arbitrary code from a string
DESERIALIZATION = "deserialization"  # pickle/marshal/yaml — code exec on load
PROCESS = "process"               # os.system/subprocess — shells out
DYNAMIC_LOAD = "dynamic_load"     # importlib/entry_points — loads code by name


@dataclass(frozen=True)
class SinkSpec:
    """A catalog entry: what a matching call means and how it is rated."""

    id: str
    category: str
    severity: str
    confidence: str


@dataclass(frozen=True)
class RiskSink:
    """A located sink — the security lens's fact, analogous to DynamicImport.

    ``dotted`` is the call as written (``pickle.loads``); ``detail`` is the first
    string-literal argument when there is one, else ``None`` (dynamic).
    """

    id: str
    category: str
    severity: str
    confidence: str
    module: str      # owning module qualname (relative to scan root)
    dotted: str      # the matched call / symbol, as written
    lineno: int
    detail: str | None = None


# Sinks matched by their *dotted* call name. A pattern matches a call whose
# dotted name equals it or ends with ``.<pattern>`` — so ``pickle.loads`` fires
# but the safe ``json.loads`` never does (the qualifier is part of the key).
# Bare builtins (eval/exec/compile) are keyed without a dot.
_SINKS: dict[str, SinkSpec] = {
    # code execution from a string
    "eval": SinkSpec("MS-SEC-EVAL", CODE_EXEC, HIGH, HIGH),
    "exec": SinkSpec("MS-SEC-EXEC", CODE_EXEC, HIGH, HIGH),
    "compile": SinkSpec("MS-SEC-COMPILE", CODE_EXEC, MEDIUM, LOW),
    # deserialization that can execute code on load
    "pickle.loads": SinkSpec("MS-SEC-PICKLE", DESERIALIZATION, HIGH, HIGH),
    "pickle.load": SinkSpec("MS-SEC-PICKLE", DESERIALIZATION, HIGH, HIGH),
    "cPickle.loads": SinkSpec("MS-SEC-PICKLE", DESERIALIZATION, HIGH, HIGH),
    "cPickle.load": SinkSpec("MS-SEC-PICKLE", DESERIALIZATION, HIGH, HIGH),
    "marshal.loads": SinkSpec("MS-SEC-MARSHAL", DESERIALIZATION, HIGH, MEDIUM),
    "marshal.load": SinkSpec("MS-SEC-MARSHAL", DESERIALIZATION, HIGH, MEDIUM),
    "yaml.load": SinkSpec("MS-SEC-YAML", DESERIALIZATION, HIGH, HIGH),
    # process / shell
    "os.system": SinkSpec("MS-SEC-OSSYSTEM", PROCESS, HIGH, HIGH),
    "subprocess.Popen": SinkSpec("MS-SEC-SUBPROCESS", PROCESS, MEDIUM, MEDIUM),
    "subprocess.call": SinkSpec("MS-SEC-SUBPROCESS", PROCESS, MEDIUM, MEDIUM),
    "subprocess.run": SinkSpec("MS-SEC-SUBPROCESS", PROCESS, MEDIUM, MEDIUM),
    "subprocess.check_call": SinkSpec("MS-SEC-SUBPROCESS", PROCESS, MEDIUM, MEDIUM),
    "subprocess.check_output": SinkSpec("MS-SEC-SUBPROCESS", PROCESS, MEDIUM, MEDIUM),
}

# Dynamic code-loading seams — the loader family MODScan already knows, re-framed
# here as attack surface (its own catalog, not shared with moddability). Unlike
# the sinks above, these are matched on the *trailing* call segment: their names
# have no benign homonym (nobody writes a safe ``x.import_module``), and this
# mirrors how the parser's own `_DYNAMIC_CALLS` keys them. `__import__` is bare;
# the rest are usually dotted (``importlib.metadata.entry_points``).
_LOADER_SINKS: dict[str, SinkSpec] = {
    "import_module": SinkSpec("MS-SEC-DYNIMPORT", DYNAMIC_LOAD, MEDIUM, MEDIUM),
    "__import__": SinkSpec("MS-SEC-DYNIMPORT", DYNAMIC_LOAD, MEDIUM, LOW),
    "import_string": SinkSpec("MS-SEC-IMPORTSTRING", DYNAMIC_LOAD, MEDIUM, MEDIUM),
    "entry_points": SinkSpec("MS-SEC-ENTRYPOINTS", DYNAMIC_LOAD, LOW, MEDIUM),
    "iter_entry_points": SinkSpec("MS-SEC-ENTRYPOINTS", DYNAMIC_LOAD, LOW, MEDIUM),
    "load_entry_point": SinkSpec("MS-SEC-ENTRYPOINTS", DYNAMIC_LOAD, LOW, MEDIUM),
    "load_module": SinkSpec("MS-SEC-LOADMODULE", DYNAMIC_LOAD, MEDIUM, LOW),
}

# `__reduce__`, unlike the others, is a *method definition* (it customises how an
# object pickles — an execution vector on the deserialization side), so it is
# matched on the def name, not a call. Kept separate for that reason.
_REDUCE_METHODS = {
    "__reduce__": SinkSpec("MS-SEC-REDUCE", DESERIALIZATION, MEDIUM, LOW),
    "__reduce_ex__": SinkSpec("MS-SEC-REDUCE", DESERIALIZATION, MEDIUM, LOW),
}


def match_call(dotted: str) -> SinkSpec | None:
    """Return the SinkSpec for a call's dotted name, or None.

    Two match modes:

    - **Qualified** (``_SINKS``): equals the key or ends with ``.key`` — the
      qualifier is load-bearing, so ``pickle.loads`` fires but ``json.loads`` and
      ``re.compile`` never do.
    - **Trailing** (``_LOADER_SINKS``): matches the final call segment regardless
      of qualifier — for loader names with no benign homonym, mirroring the
      parser's dynamic-import detection.
    """
    if dotted in _SINKS:
        return _SINKS[dotted]
    for pattern, spec in _SINKS.items():
        if "." in pattern and dotted.endswith("." + pattern):
            return spec
    return _LOADER_SINKS.get(dotted.rsplit(".", 1)[-1])


def match_reduce(name: str) -> SinkSpec | None:
    return _REDUCE_METHODS.get(name)


def all_specs() -> list[SinkSpec]:
    """Every distinct spec in the catalog (for integrity checks / docs)."""
    seen: dict[str, SinkSpec] = {}
    for spec in list(_SINKS.values()) + list(_LOADER_SINKS.values()) + list(_REDUCE_METHODS.values()):
        seen[spec.id] = spec
    return list(seen.values())
