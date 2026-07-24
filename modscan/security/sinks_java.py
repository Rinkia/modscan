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

"""Risk-sink catalog for Java.

Same shape as the Python catalog (`sinks.py`) and the TS one (`sinks_ts.py`):
stable ``MS-SEC-*`` ids rated by severity x confidence, enumeration only. Ids are
reused where the sink is the same concept across languages, so
``MS-SEC-DYNIMPORT`` covers ``importlib.import_module``, a computed
``require()`` and ``Class.forName`` alike.

Modelled on **find-sec-bugs**, the SpotBugs plugin that is Java's counterpart to
Bandit. Its detector names are noted per entry so an entry can be argued against
a published rule rather than an opinion.

Three calibration decisions, all deliberate:

* **Java's process API does not use a shell.** ``Runtime.exec(String)`` and
  ``ProcessBuilder`` execute a program directly, so they sit at medium — the same
  tier as ``subprocess.run`` without ``shell=True`` and node's ``spawn``. The
  shell only appears when the command array *names* one
  (``exec(new String[]{"sh", "-c", cmd})``), and that is the Java analogue of
  ``shell=True``: the detector elevates to high when it sees a shell literal in
  the arguments. find-sec-bugs rates all command execution high; this catalog
  keeps the cross-language tiering consistent instead, because the gate's
  ``fail-on: high`` default was chosen by measuring what routine plugin-host code
  looks like.
* **Deserialization is where Java's high-severity mass sits**, not process
  spawning — ``ObjectInputStream.readObject``, ``XMLDecoder``, XStream and
  SnakeYAML are the classic remote-code-execution paths. The gate therefore has
  teeth on Java without relying on the shell heuristic above.
* **``readObject`` / ``readResolve`` / ``readExternal`` definitions** are matched
  as *method definitions*, exactly like Python's ``__reduce__``: a class that
  defines one customises how it deserializes, which is an execution vector on the
  deserialization side rather than a call. Also like ``__reduce__``, this is
  coverage the external authority has no single rule for — extra surface, not a
  false positive.

Matching is **qualifier-strict wherever a benign homonym exists**. ``eval`` is a
bare method name on any object in Java, so it fires only on a known
script-engine binding; a lone ``x.eval(...)`` is not a sink.
"""

from __future__ import annotations

from modscan.security.sinks import (
    CODE_EXEC,
    DESERIALIZATION,
    DYNAMIC_LOAD,
    HIGH,
    LOW,
    MEDIUM,
    PROCESS,
    SinkSpec,
)

# --- receiver-qualified sinks ------------------------------------------------
# Keyed by "Type.method". A call matches when its receiver text ends with the
# type name, so `javax.script.ScriptEngine.eval`, `engine.eval` on a variable
# declared ScriptEngine, and `new ScriptEngineManager()...eval` all resolve —
# see detect_java.py for how the receiver type is recovered.
_TYPED_SINKS: dict[str, SinkSpec] = {
    # code execution from a string (find-sec-bugs: SCRIPT_ENGINE_INJECTION,
    # GROOVY_SHELL, SPEL_INJECTION, EL_INJECTION)
    "ScriptEngine.eval": SinkSpec("MS-SEC-SCRIPTENGINE", CODE_EXEC, HIGH, HIGH),
    "ScriptEngineManager.eval": SinkSpec("MS-SEC-SCRIPTENGINE", CODE_EXEC, HIGH, HIGH),
    "Compilable.compile": SinkSpec("MS-SEC-SCRIPTENGINE", CODE_EXEC, HIGH, MEDIUM),
    "GroovyShell.evaluate": SinkSpec("MS-SEC-GROOVY", CODE_EXEC, HIGH, HIGH),
    "GroovyShell.parse": SinkSpec("MS-SEC-GROOVY", CODE_EXEC, HIGH, HIGH),
    "GroovyClassLoader.parseClass": SinkSpec("MS-SEC-GROOVY", CODE_EXEC, HIGH, HIGH),
    "ExpressionParser.parseExpression": SinkSpec("MS-SEC-SPEL", CODE_EXEC, HIGH, MEDIUM),
    "SpelExpressionParser.parseExpression": SinkSpec("MS-SEC-SPEL", CODE_EXEC, HIGH, MEDIUM),
    "ExpressionFactory.createValueExpression": SinkSpec("MS-SEC-EL", CODE_EXEC, HIGH, LOW),
    "ExpressionFactory.createMethodExpression": SinkSpec("MS-SEC-EL", CODE_EXEC, HIGH, LOW),
    # deserialization that can execute code on load (find-sec-bugs:
    # OBJECT_DESERIALIZATION, XMLDECODER, XSTREAM_INIT, UNSAFE_YAML_DESERIALIZATION)
    "ObjectInputStream.readObject": SinkSpec("MS-SEC-JAVADESER", DESERIALIZATION, HIGH, HIGH),
    "ObjectInputStream.readUnshared": SinkSpec("MS-SEC-JAVADESER", DESERIALIZATION, HIGH, HIGH),
    "XMLDecoder.readObject": SinkSpec("MS-SEC-XMLDECODER", DESERIALIZATION, HIGH, HIGH),
    "XStream.fromXML": SinkSpec("MS-SEC-XSTREAM", DESERIALIZATION, HIGH, HIGH),
    "Yaml.load": SinkSpec("MS-SEC-YAML", DESERIALIZATION, HIGH, HIGH),
    "Yaml.loadAll": SinkSpec("MS-SEC-YAML", DESERIALIZATION, HIGH, HIGH),
    # process (find-sec-bugs: COMMAND_INJECTION) — no shell unless one is named,
    # hence medium, with elevate_on_shell doing the rest.
    "Runtime.exec": SinkSpec("MS-SEC-JAVAEXEC", PROCESS, MEDIUM, HIGH, True),
    "ProcessBuilder.start": SinkSpec("MS-SEC-JAVAEXEC", PROCESS, MEDIUM, MEDIUM, True),
    # dynamic loading by name (find-sec-bugs: REFLECTION_UNSAFE / CLASS_INJECTION)
    "Class.forName": SinkSpec("MS-SEC-DYNIMPORT", DYNAMIC_LOAD, MEDIUM, MEDIUM),
    "ClassLoader.loadClass": SinkSpec("MS-SEC-DYNIMPORT", DYNAMIC_LOAD, MEDIUM, MEDIUM),
    "ClassLoader.defineClass": SinkSpec("MS-SEC-DEFINECLASS", CODE_EXEC, HIGH, MEDIUM),
    "URLClassLoader.newInstance": SinkSpec("MS-SEC-DYNIMPORT", DYNAMIC_LOAD, MEDIUM, LOW),
    "ServiceLoader.load": SinkSpec("MS-SEC-ENTRYPOINTS", DYNAMIC_LOAD, LOW, MEDIUM),
    "Method.invoke": SinkSpec("MS-SEC-REFLECTINVOKE", DYNAMIC_LOAD, MEDIUM, LOW),
}

# Constructors that are sinks in themselves: building one is the dangerous act,
# because what follows is a read. `new ProcessBuilder(cmd).start()` also matches
# ProcessBuilder.start above; the detector deduplicates by (line, id).
_CONSTRUCTOR_SINKS: dict[str, SinkSpec] = {
    "ProcessBuilder": SinkSpec("MS-SEC-JAVAEXEC", PROCESS, MEDIUM, MEDIUM, True),
    "XMLDecoder": SinkSpec("MS-SEC-XMLDECODER", DESERIALIZATION, HIGH, MEDIUM),
    "GroovyShell": SinkSpec("MS-SEC-GROOVY", CODE_EXEC, HIGH, MEDIUM),
    "GroovyClassLoader": SinkSpec("MS-SEC-GROOVY", CODE_EXEC, HIGH, LOW),
    "URLClassLoader": SinkSpec("MS-SEC-DYNIMPORT", DYNAMIC_LOAD, MEDIUM, LOW),
}

# Method *definitions* that customise deserialization — Java's `__reduce__`.
_DESER_HOOKS: dict[str, SinkSpec] = {
    "readObject": SinkSpec("MS-SEC-JAVADESERHOOK", DESERIALIZATION, MEDIUM, LOW),
    "readResolve": SinkSpec("MS-SEC-JAVADESERHOOK", DESERIALIZATION, MEDIUM, LOW),
    "readExternal": SinkSpec("MS-SEC-JAVADESERHOOK", DESERIALIZATION, MEDIUM, LOW),
}

# Argument literals that mean "hand this to a shell". Seeing one of these in a
# Runtime.exec / ProcessBuilder argument list is Java's shell=True.
SHELL_LITERALS = ("sh", "bash", "zsh", "/bin/sh", "/bin/bash", "cmd", "cmd.exe", "powershell")


def match_typed_call(receiver_type: str, method: str) -> SinkSpec | None:
    """Spec for ``<receiver_type>.<method>``, or None.

    ``receiver_type`` is matched on its trailing segment, so a fully-qualified
    ``java.io.ObjectInputStream`` and a bare ``ObjectInputStream`` are one key.
    """
    if not receiver_type:
        return None
    return _TYPED_SINKS.get(f"{receiver_type.rsplit('.', 1)[-1]}.{method}")


def match_constructor(type_name: str) -> SinkSpec | None:
    return _CONSTRUCTOR_SINKS.get(type_name.rsplit(".", 1)[-1])


def match_deserialization_hook(name: str) -> SinkSpec | None:
    return _DESER_HOOKS.get(name)


def all_specs() -> list[SinkSpec]:
    """Every distinct spec in the Java catalog (for integrity checks / docs)."""
    seen: dict[str, SinkSpec] = {}
    for spec in (
        list(_TYPED_SINKS.values())
        + list(_CONSTRUCTOR_SINKS.values())
        + list(_DESER_HOOKS.values())
    ):
        seen.setdefault(spec.id, spec)
    return list(seen.values())
