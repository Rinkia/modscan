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

"""Generating and validating example plugins, plus the retry policy.

Isolated from orchestration and rendering so the "did this example actually
work?" rules live in one readable place. All code execution is delegated to
`modscan.execution` (or, when sandboxed, a child process running the same code).
"""

from __future__ import annotations

import contextlib
import threading

from modscan.execution import (
    SUBCLASS_KINDS,
    example_defines_working_subclass,
    example_loads,
)
from modscan.factblocks import FactBlock
from modscan.models import ExampleStatus
from modscan.prompts import SYSTEM, example_prompt
from modscan.providers.base import Provider
from modscan.sandbox import validate_in_sandbox

# Example-validation retry bounds (locked in the Task 4 plan).
MIN_RETRIES = 3
MAX_RETRIES = 5
DEFAULT_RETRIES = 4

# Statuses that end the retry loop, strongest first. See models.ExampleStatus
# for what each one means.
OK_STATUSES = (
    ExampleStatus.VERIFIED,
    ExampleStatus.EXECUTED,
    ExampleStatus.COMPILED,
)


def clamp_retries(requested: int) -> int:
    """Retries are bounded on both ends: never fewer than MIN, never more than MAX."""
    return max(MIN_RETRIES, min(MAX_RETRIES, requested))


def extract_code(raw: str) -> str:
    """Pull the body out of a ```python ...``` fence, else return as-is."""
    text = raw.strip()
    if "```" not in text:
        return text
    parts = text.split("```")
    # parts[1] is the first fenced block; drop a leading language tag line.
    block = parts[1] if len(parts) >= 2 else text
    lines = block.splitlines()
    if lines and lines[0].strip().lower() in ("python", "py"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def verify_example(
    root: str,
    fb: FactBlock,
    code: str,
    validate: bool,
    sandbox: bool,
    lock: threading.Lock | None = None,
) -> ExampleStatus:
    """Return an example status: verified | executed | compiled | invalid.

    Loading/execution is delegated to `execution.py` (or, with `sandbox` set, to
    a child process running that same code) so the in-process and sandboxed
    paths can never disagree.

    `lock` serialises IN-PROCESS validation. Importing a target mutates
    process-global state (sys.path, sys.modules) and exec's into it, so it is
    not thread-safe; callers running points concurrently must pass a shared
    lock. Sandboxed validation needs no lock — the child process has its own
    interpreter state.
    """
    try:
        compile(code, "<modscan-example>", "exec")
    except SyntaxError:
        return ExampleStatus.INVALID
    if not validate:
        return ExampleStatus.COMPILED

    is_subclass_seam = fb.kind in SUBCLASS_KINDS
    if sandbox:
        # Child process: isolated interpreter state, safe to run unserialised.
        ok = validate_in_sandbox(root, fb.module, fb.symbol, code, fb.kind)
    else:
        guard = lock if lock is not None else contextlib.nullcontext()
        with guard:
            if is_subclass_seam:
                ok = example_defines_working_subclass(root, fb.module, fb.symbol, code)
            else:
                # hook/registration/api: no subclass to instantiate, but we can
                # still load it to catch bad imports and module-level errors.
                ok = example_loads(root, code)

    if not ok:
        return ExampleStatus.INVALID
    return ExampleStatus.VERIFIED if is_subclass_seam else ExampleStatus.EXECUTED


def make_example(
    provider: Provider,
    root: str,
    fb: FactBlock,
    retries: int,
    validate: bool,
    sandbox: bool,
    lock: threading.Lock | None = None,
) -> tuple[str, ExampleStatus]:
    """Generate and validate an example plugin, retrying up to `retries` times."""
    code = ""
    for _ in range(retries):
        code = extract_code(provider.generate(SYSTEM, example_prompt(fb)))
        status = verify_example(root, fb, code, validate, sandbox, lock)
        if status in OK_STATUSES:
            return code, status
    return code, ExampleStatus.UNVERIFIED
