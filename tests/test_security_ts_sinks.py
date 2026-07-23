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

"""Self-check for the TypeScript/JavaScript security sinks (M4).

Skips cleanly when the tree-sitter extra is not installed, like
tests/test_typescript.py — CI does not always install optional dependencies.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tree_sitter  # noqa: F401
    import tree_sitter_typescript  # noqa: F401
except ImportError:
    print("SKIP: tree-sitter not installed (pip install modscan[typescript])")
    sys.exit(0)

from modscan.security.detect import find_risk_sinks  # noqa: E402
from modscan.security.sinks_ts import all_ts_specs  # noqa: E402

# Every catalogued sink, in the forms real code uses them, plus benign
# look-alikes that must never fire.
_FIXTURE = """\
import * as vm from 'vm';
import { execFile } from 'child_process';
const cp = require('child_process');
const { exec } = require('child_process');
const fs = require('fs');

export function danger(userInput, name) {
  eval(userInput);                       // MS-SEC-EVAL
  const f = new Function(userInput);     // MS-SEC-JSFUNCTION (new)
  const g = Function(userInput);         // MS-SEC-JSFUNCTION (bare call)
  vm.runInThisContext(userInput);        // MS-SEC-VM (namespace import)
  cp.exec(userInput);                    // MS-SEC-CHILDPROC (aliased require)
  exec(userInput);                       // MS-SEC-CHILDPROC (destructured)
  execFile(name, []);                    // MS-SEC-CHILDPROC-NOSHELL (named import)
  require(name);                         // MS-SEC-DYNREQUIRE (computed)
  setTimeout('doEvil()', 10);            // MS-SEC-STRINGTIMER (string body)
  return [f, g];
}

export function benign(text, re) {
  JSON.parse(text);                      // safe - the json.loads analogue
  re.exec(text);                         // a REGEX exec, not child_process
  require('fs');                         // literal - a static import
  fs.readFileSync('a.txt');              // ordinary fs use
  setTimeout(() => run(), 10);           // function body, not a string
  const obj = { eval: 1 };               // a property named eval
  return obj;
}
"""


def _write(root: str) -> None:
    with open(os.path.join(root, "app.ts"), "w", encoding="utf-8") as fh:
        fh.write(_FIXTURE)


def test_catalog_integrity() -> None:
    specs = all_ts_specs()
    ids = [s.id for s in specs]
    assert all(i.startswith("MS-SEC-") for i in ids)
    assert len(set(ids)) == len(ids), "duplicate spec ids"
    assert all(s.severity in ("high", "medium", "low") for s in specs)


def test_detects_ts_sinks_and_ignores_benign() -> None:
    with tempfile.TemporaryDirectory() as root:
        _write(root)
        sinks = find_risk_sinks(root, language="typescript")
        found = {s.id for s in sinks}

        expected = {
            "MS-SEC-EVAL", "MS-SEC-JSFUNCTION", "MS-SEC-VM", "MS-SEC-CHILDPROC",
            "MS-SEC-CHILDPROC-NOSHELL", "MS-SEC-DYNREQUIRE", "MS-SEC-STRINGTIMER",
        }
        assert expected <= found, f"missing: {expected - found}"

        # the benign half must contribute nothing
        lines = {s.lineno for s in sinks}
        benign_start = _FIXTURE.splitlines().index("export function benign(text, re) {") + 1
        assert not [ln for ln in lines if ln > benign_start], (
            "a benign call was flagged: "
            f"{[(s.dotted, s.lineno) for s in sinks if s.lineno > benign_start]}"
        )

        # shell vs no-shell severity split is preserved
        by_id = {s.id: s for s in sinks}
        assert by_id["MS-SEC-CHILDPROC"].severity == "high"
        assert by_id["MS-SEC-CHILDPROC-NOSHELL"].severity == "medium"
        assert by_id["MS-SEC-EVAL"].category == "code_exec"


def test_javascript_alias_and_unknown_language() -> None:
    with tempfile.TemporaryDirectory() as root:
        _write(root)
        # 'javascript' shares the front-end
        assert find_risk_sinks(root, language="javascript")
    try:
        find_risk_sinks(".", language="cobol")
    except ValueError as exc:
        assert "unknown language" in str(exc)
    else:
        raise AssertionError("expected ValueError for an unknown language")


if __name__ == "__main__":
    test_catalog_integrity()
    test_detects_ts_sinks_and_ignores_benign()
    test_javascript_alias_and_unknown_language()
    print("OK: TypeScript security-sink self-check passed")
