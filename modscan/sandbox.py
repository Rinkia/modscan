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

"""Subprocess sandbox for example validation.

In-process validation (execution.py) runs target and generated code in the host
interpreter — fine for code you trust. When the target is less trusted,
`validate_in_sandbox` performs the *same* check in a short-lived child process
with a timeout, so a hang or crash can't take down the host and the blast radius
is one disposable process.

The child does not carry its own copy of the validation logic: it imports
`modscan.execution.validate_example`, the same function the in-process path
calls. Host and sandbox therefore cannot drift apart — a fix to the loading
logic lands in both at once.

ponytail: a subprocess with a timeout — not a real security boundary (no seccomp,
namespaces, or resource caps). It contains hangs and crashes, not malice. A true
sandbox (container / gVisor) is the upgrade path; this is the pragmatic first
step and enough for "I mostly trust this, but don't want a runaway import."
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_DEFAULT_TIMEOUT = 10

# Runs in the child: read a job from stdin, delegate to the shared validator,
# report via exit code. Deliberately trivial — all real logic lives in
# modscan.execution so there is exactly one implementation.
_RUNNER = r"""
import json, sys

job = json.loads(sys.stdin.read())
sys.path.insert(0, job["package_path"])
try:
    from modscan.execution import validate_example
    ok = validate_example(
        job["root"], job["module"], job["symbol"], job["code"], job["kind"]
    )
except Exception:
    ok = False
sys.exit(0 if ok else 1)
"""


def _package_path() -> str:
    """Directory containing the `modscan` package, so the child can import it."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def validate_in_sandbox(
    root: str,
    module: str,
    symbol: str,
    code: str,
    kind: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> bool:
    """Validate an example in a child process. True if it loaded/instantiated."""
    job = json.dumps(
        {
            "root": root,
            "module": module,
            "symbol": symbol,
            "code": code,
            "kind": kind,
            "package_path": _package_path(),
        }
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _RUNNER],
            input=job,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0
