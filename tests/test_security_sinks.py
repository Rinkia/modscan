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

"""Self-check for the security lens sink detector (M1).

Framework-free: `python tests/test_security_sinks.py`. A planted-sink fixture
with benign look-alikes proves each dangerous sink is detected and each benign
call is NOT flagged (the qualifier-keyed matching guards json.loads / re.compile
/ ast.literal_eval).
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.security import find_risk_sinks  # noqa: E402
from modscan.security.sinks import all_specs, match_call  # noqa: E402

# One of each dangerous sink, plus benign decoys that must NOT fire.
_FIXTURE = '''\
import os
import re
import json
import pickle
import marshal
import yaml
import subprocess
import ast


def danger(s, blob, path):
    eval(s)                         # MS-SEC-EVAL
    exec(s)                         # MS-SEC-EXEC
    compile(s, "<x>", "exec")       # MS-SEC-COMPILE
    pickle.loads(blob)              # MS-SEC-PICKLE
    marshal.loads(blob)             # MS-SEC-MARSHAL
    yaml.load(blob)                 # MS-SEC-YAML
    os.system(path)                 # MS-SEC-OSSYSTEM
    subprocess.run([path])          # MS-SEC-SUBPROCESS


def benign(s, blob):
    json.loads(blob)                # NOT a sink (json, not pickle)
    re.compile(s)                   # NOT a sink (re.compile, not builtin compile)
    ast.literal_eval(s)             # NOT a sink (literal_eval is safe)


class Widget:
    def __reduce__(self):           # MS-SEC-REDUCE (method def, not a call)
        return (Widget, ())

    def exec(self):                 # NOT a sink (a method named exec, not builtin)
        return 1
'''


def _write_fixture(root: str) -> None:
    with open(os.path.join(root, "mod.py"), "w", encoding="utf-8") as fh:
        fh.write(_FIXTURE)


_SHELL_FIXTURE = '''\
import os
import subprocess


def spawn(cmd, url):
    subprocess.run(cmd, shell=True)       # elevated to high
    subprocess.run(cmd)                   # stays medium
    subprocess.run(cmd, shell=flag)       # non-literal -> not elevated
    os.popen(cmd)                         # shell -> high
    os.system(cmd)                        # shell -> high
    os.startfile(url)                     # no shell -> medium
    os.execv(cmd, [])                     # no shell -> medium
'''


def test_shell_true_elevates_severity() -> None:
    """shell=True turns a contained subprocess call into command-injection
    surface — the Bandit B602/B603 distinction. Only a *literal* True counts."""
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "sh.py"), "w", encoding="utf-8") as fh:
            fh.write(_SHELL_FIXTURE)
        sinks = find_risk_sinks(root)
        subs = sorted(
            (s for s in sinks if s.id == "MS-SEC-SUBPROCESS"), key=lambda s: s.lineno
        )
        assert [s.severity for s in subs] == ["high", "medium", "medium"], [
            (s.lineno, s.severity) for s in subs
        ]

        by_id = {s.id: s for s in sinks}
        assert by_id["MS-SEC-OSSYSTEM"].severity == "high"       # os.popen / os.system
        assert by_id["MS-SEC-STARTPROCESS"].severity == "medium"  # startfile / execv


def test_process_sinks_bandit_parity() -> None:
    """Gaps found by cross-checking against Bandit (B605/B606) are covered."""
    for call in ("os.popen", "os.startfile", "os.execv", "os.spawnv", "os.posix_spawn"):
        assert match_call(call) is not None, call
    assert match_call("os.path.join") is None  # benign os.* still not a sink


def test_catalog_integrity() -> None:
    specs = all_specs()
    ids = [s.id for s in specs]
    assert all(i.startswith("MS-SEC-") for i in ids)
    assert len(set(ids)) == len(ids), "duplicate spec ids"
    assert all(s.severity in ("high", "medium", "low") for s in specs)
    assert all(s.confidence in ("high", "medium", "low") for s in specs)


def test_qualifier_keyed_matching() -> None:
    # the dangerous ones fire...
    assert match_call("pickle.loads").id == "MS-SEC-PICKLE"
    assert match_call("eval").id == "MS-SEC-EVAL"
    assert match_call("a.b.subprocess.run").id == "MS-SEC-SUBPROCESS"  # deep chain
    # ...and the benign look-alikes do not
    assert match_call("json.loads") is None
    assert match_call("re.compile") is None
    assert match_call("ast.literal_eval") is None
    assert match_call("obj.exec") is None  # method named exec, not builtin

    # loader family matches on the trailing segment (dotted or bare)
    assert match_call("importlib.metadata.entry_points").id == "MS-SEC-ENTRYPOINTS"
    assert match_call("importlib.import_module").id == "MS-SEC-DYNIMPORT"
    assert match_call("__import__").id == "MS-SEC-DYNIMPORT"


def test_detects_planted_sinks_not_benign() -> None:
    with tempfile.TemporaryDirectory() as root:
        _write_fixture(root)
        sinks = find_risk_sinks(root)
        by_id = {s.id for s in sinks}

        expected = {
            "MS-SEC-EVAL", "MS-SEC-EXEC", "MS-SEC-COMPILE", "MS-SEC-PICKLE",
            "MS-SEC-MARSHAL", "MS-SEC-YAML", "MS-SEC-OSSYSTEM",
            "MS-SEC-SUBPROCESS", "MS-SEC-REDUCE",
        }
        assert expected <= by_id, f"missing: {expected - by_id}"

        # exactly the dangerous calls + the __reduce__ def, nothing benign
        assert len(sinks) == len(expected), [s.dotted for s in sinks]

        # a category and rating rode along on each finding
        pickle_sink = next(s for s in sinks if s.id == "MS-SEC-PICKLE")
        assert pickle_sink.category == "deserialization"
        assert pickle_sink.severity == "high" and pickle_sink.confidence == "high"
        assert pickle_sink.module == "mod"


if __name__ == "__main__":
    test_shell_true_elevates_severity()
    test_process_sinks_bandit_parity()
    test_catalog_integrity()
    test_qualifier_keyed_matching()
    test_detects_planted_sinks_not_benign()
    print("OK: security sink-detection self-check passed")
