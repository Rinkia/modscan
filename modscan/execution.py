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

"""The single implementation of "load target code and try to plug into it".

This logic previously existed three times — in the validator, in the doc
generator, and a third time as a Python string inside the sandbox runner. That
string copy could not be imported, linted, or tested, and the three drifted:
when `typing.Protocol` was found to make `issubclass` raise, the fix had to be
applied to two of them and the third only survived by accident.

Everything that executes foreign code now goes through here, so a fix lands
once. The sandbox child imports this same module rather than carrying a copy.

SECURITY / TRUST BOUNDARY
-------------------------
Every function here IMPORTS and EXECUTES code from the scanned target. That is
the point — a plugin is only proven by loading it — but it means callers must
only point this at code they trust, or route it through `sandbox.py` to contain
crashes and hangs in a child process.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import sys
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# Class kinds whose seams are validated by building/finding a concrete subclass.
SUBCLASS_KINDS = ("class", "abstract_class")


@contextlib.contextmanager
def sys_path(entry: str) -> Iterator[None]:
    """Temporarily prepend `entry` to sys.path so target modules import."""
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(entry)


def load_symbol(root: str, module_qualname: str, name: str) -> Any:
    """Import the target module (with `root` importable) and return an attribute.

    Raises on import failure or missing attribute; callers translate that into
    their own result type rather than letting it propagate to the user.
    """
    with sys_path(root):
        module = importlib.import_module(module_qualname)
    return getattr(module, name)


def is_concrete_subclass(candidate: Any, base: type) -> bool:
    """True if `candidate` is a strict subclass of `base`.

    `issubclass` raises TypeError for a runtime_checkable Protocol carrying
    non-method members, so the check is guarded — the whole reason this helper
    exists instead of an inline call.
    """
    if not isinstance(candidate, type) or candidate is base:
        return False
    try:
        return issubclass(candidate, base)
    except Exception:  # noqa: BLE001 — a base that rejects issubclass is a "no"
        return False


def instantiate_probe_subclass(cls: type) -> tuple[bool, str]:
    """Build a concrete subclass of `cls` with abstract methods stubbed, and
    instantiate it. Returns (ok, detail).

    Used to prove a detected seam is genuinely subclassable, without any
    author-provided code.
    """
    abstract = getattr(cls, "__abstractmethods__", frozenset())
    namespace = {name: (lambda self, *a, **k: None) for name in abstract}
    try:
        # Subclass creation itself can raise (e.g. Protocol with data members),
        # so it belongs inside the guard alongside instantiation.
        probe = type(f"_ModScanProbe_{cls.__name__}", (cls,), namespace)
        probe()
    except Exception as exc:  # noqa: BLE001
        return False, f"subclass did not instantiate: {exc!r}"
    stubbed = f" (stubbed {len(abstract)} abstract method(s))" if abstract else ""
    return True, f"probe subclass of {cls.__name__} instantiated{stubbed}"


def exec_example(root: str, code: str) -> dict:
    """Execute example source in a fresh namespace with `root` importable.

    Returns the resulting namespace. Raises if the code does not load.
    """
    namespace: dict = {}
    with sys_path(root):
        exec(compile(code, "<modscan-example>", "exec"), namespace)  # noqa: S102
    return namespace


def example_loads(root: str, code: str) -> bool:
    """True if the example executes cleanly (imports resolve, no top-level error)."""
    try:
        exec_example(root, code)
    except Exception:  # noqa: BLE001 — any failure means the example didn't load
        # Swallowed on purpose (the caller only needs a verdict), but a failed
        # example is exactly what you want to see when debugging a bad run.
        logger.debug("example did not load under %s", root, exc_info=True)
        return False
    return True


def example_defines_working_subclass(
    root: str, module_qualname: str, symbol: str, code: str
) -> bool:
    """True if the example defines a concrete subclass of the seam that instantiates.

    This is the check behind a "verified" example: the generated plugin is not
    merely syntactically valid, it actually plugs into the target.
    """
    try:
        base = load_symbol(root, module_qualname, symbol)
        namespace = exec_example(root, code)
    except Exception:  # noqa: BLE001
        logger.debug(
            "example for %s:%s did not load", module_qualname, symbol, exc_info=True
        )
        return False
    if not isinstance(base, type):
        return False
    try:
        for value in namespace.values():
            if is_concrete_subclass(value, base):
                value()
                return True
    except Exception:  # noqa: BLE001 — instantiation failure means "not working"
        return False
    return False


def validate_example(
    root: str, module_qualname: str, symbol: str, code: str, kind: str
) -> bool:
    """Validate an example against a seam, dispatching on the seam kind.

    Class-like seams must yield a working concrete subclass; every other kind
    only has to load cleanly. Shared by the in-process path and the sandbox
    child so both answer identically.
    """
    if kind in SUBCLASS_KINDS:
        return example_defines_working_subclass(root, module_qualname, symbol, code)
    return example_loads(root, code)
