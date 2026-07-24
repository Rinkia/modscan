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

"""Self-check for the Java security sinks.

Skips cleanly when the tree-sitter Java extra is not installed, like
tests/test_java.py — CI does not always install optional dependencies.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tree_sitter  # noqa: F401
    import tree_sitter_java  # noqa: F401
except ImportError:
    print("SKIP: tree-sitter-java not installed (pip install modscan[java])")
    sys.exit(0)

from modscan.security.detect import find_risk_sinks  # noqa: E402
from modscan.security.sinks import CODE_EXEC, DESERIALIZATION, HIGH, MEDIUM, PROCESS  # noqa: E402
from modscan.security.sinks_java import all_specs  # noqa: E402

# Each catalogued sink in the form real Java writes it — through a declared
# variable, a constructor receiver or a static call — never fully qualified,
# because real code never is.
_FIXTURE = """\
package demo;

import java.io.ObjectInputStream;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class Danger implements java.io.Serializable {

    private ScriptEngine engine = new ScriptEngineManager().getEngineByName("js");

    public void run(String userInput, java.io.InputStream in) throws Exception {
        engine.eval(userInput);                                 // MS-SEC-SCRIPTENGINE
        Runtime.getRuntime().exec(userInput);                   // MS-SEC-JAVAEXEC (medium)
        new ProcessBuilder(userInput).start();                  // MS-SEC-JAVAEXEC
        ObjectInputStream ois = new ObjectInputStream(in);
        ois.readObject();                                       // MS-SEC-JAVADESER
        Class.forName(userInput);                               // MS-SEC-DYNIMPORT (static)
    }

    private void readObject(ObjectInputStream in) { }           // MS-SEC-JAVADESERHOOK
}
"""

# Nothing here may fire. Same method names, different types.
_DECOYS = """\
package demo;

import java.util.Properties;

public class Benign {

    public void safe(Properties props, java.io.Reader r, Evaluator custom) throws Exception {
        props.load(r);              // load() on Properties is not SnakeYAML
        custom.eval("1 + 1");       // eval() on somebody's own type
        String cmd = exec("ls");    // a local method called exec
        StringBuilder b = new StringBuilder();
        b.append(cmd);
    }

    private String exec(String s) { return s; }

    private Object readObject(String notAStream) { return notAStream; }
}
"""

_SHELL = """\
package demo;

public class Shelling {
    public void go(String userInput) throws Exception {
        Runtime.getRuntime().exec(new String[]{"sh", "-c", userInput});
    }
}
"""


def _scan(files: dict[str, str]):
    with tempfile.TemporaryDirectory() as root:
        for name, body in files.items():
            with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        return find_risk_sinks(root, language="java")


def test_every_catalogued_family_fires_in_the_form_real_code_uses() -> None:
    sinks = _scan({"Danger.java": _FIXTURE})
    found = {s.id for s in sinks}
    for expected in (
        "MS-SEC-SCRIPTENGINE",     # method on a field whose declared type is known
        "MS-SEC-JAVAEXEC",         # Runtime.getRuntime().exec + new ProcessBuilder().start()
        "MS-SEC-JAVADESER",        # method on a local variable
        "MS-SEC-DYNIMPORT",        # static call, receiver identifier IS the type
        "MS-SEC-JAVADESERHOOK",    # a method DEFINITION, Java's __reduce__
    ):
        assert expected in found, f"{expected} missing from {sorted(found)}"
    assert all(s.module == "Danger" for s in sinks), "module is the dotted path"


def test_benign_lookalikes_never_fire() -> None:
    """The reason receiver types are resolved at all.

    `props.load(r)`, `custom.eval(...)` and a local method named `exec` are all
    the same *method names* as real sinks on different types. A name-only match
    would report every one of them.
    """
    assert _scan({"Benign.java": _DECOYS}) == []


def test_a_deserialization_hook_needs_the_real_signature() -> None:
    """`readObject(String)` is somebody's own reader, not the serialization hook."""
    sinks = _scan({"Benign.java": _DECOYS, "Danger.java": _FIXTURE})
    hooks = [s for s in sinks if s.id == "MS-SEC-JAVADESERHOOK"]
    assert len(hooks) == 1, "only the ObjectInputStream signature counts"
    assert hooks[0].module == "Danger"


def test_a_named_shell_elevates_the_process_sink() -> None:
    """Java's shell=True: the command array literally names a shell."""
    plain = [s for s in _scan({"Danger.java": _FIXTURE}) if s.id == "MS-SEC-JAVAEXEC"]
    assert plain and all(s.severity == MEDIUM for s in plain), \
        "Java's process API does not use a shell on its own"

    shelled = [s for s in _scan({"Shelling.java": _SHELL}) if s.id == "MS-SEC-JAVAEXEC"]
    assert len(shelled) == 1
    assert shelled[0].severity == HIGH, "naming sh is the Java analogue of shell=True"


def test_one_spawn_written_two_ways_is_reported_once() -> None:
    """`new ProcessBuilder(cmd).start()` is one act on one line, two AST nodes."""
    sinks = _scan({"P.java": (
        "package demo;\n"
        "public class P {\n"
        "  void go(String c) throws Exception { new ProcessBuilder(c).start(); }\n"
        "}\n"
    )})
    assert len(sinks) == 1, sinks


def test_catalog_integrity() -> None:
    """Every spec is well-formed and stays inside the categories the lens claims."""
    specs = all_specs()
    assert specs, "empty catalog"
    for spec in specs:
        assert spec.id.startswith("MS-SEC-"), spec
        assert spec.category in (CODE_EXEC, DESERIALIZATION, PROCESS, "dynamic_load"), spec
        assert spec.severity in ("high", "medium", "low"), spec
        assert spec.confidence in ("high", "medium", "low"), spec
    ids = [s.id for s in specs]
    assert len(ids) == len(set(ids)), "all_specs must return one entry per id"


def test_shared_ids_keep_their_cross_language_meaning() -> None:
    """An id means the same thing in every catalog, or it should not be reused."""
    from modscan.security import sinks as py_sinks

    by_id = {s.id: s for s in all_specs()}
    for shared in ("MS-SEC-DYNIMPORT", "MS-SEC-YAML", "MS-SEC-ENTRYPOINTS"):
        java = by_id.get(shared)
        python = next((s for s in py_sinks.all_specs() if s.id == shared), None)
        assert java is not None and python is not None, shared
        assert java.category == python.category, \
            f"{shared} means a different category in Java than in Python"


if __name__ == "__main__":
    test_every_catalogued_family_fires_in_the_form_real_code_uses()
    test_benign_lookalikes_never_fire()
    test_a_deserialization_hook_needs_the_real_signature()
    test_a_named_shell_elevates_the_process_sink()
    test_one_spawn_written_two_ways_is_reported_once()
    test_catalog_integrity()
    test_shared_ids_keep_their_cross_language_meaning()
    print("OK: Java security-sink self-check passed")
