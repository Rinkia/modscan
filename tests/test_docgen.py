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

"""Self-check for the doc generator. FakeProvider only — no network, no cost."""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.docgen import generate_docs  # noqa: E402
from modscan.providers import FakeProvider  # noqa: E402

API_SRC = (
    "from abc import ABC, abstractmethod\n"
    "\n"
    "__all__ = ['Backend']\n"
    "\n"
    "class Backend(ABC):\n"
    "    @abstractmethod\n"
    "    def handle(self, event):\n"
    "        ...\n"
)


def _write_pkg(root: str, pkg: str) -> None:
    d = os.path.join(root, pkg)
    os.makedirs(d)
    open(os.path.join(d, "__init__.py"), "w").close()
    with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
        fh.write(API_SRC)


def _cleanup(pkg: str) -> None:
    for name in list(sys.modules):
        if name == pkg or name.startswith(pkg + "."):
            del sys.modules[name]


def _good_responder(pkg: str):
    good_example = (
        f"```python\nfrom {pkg}.api import Backend\n"
        "class MyBackend(Backend):\n"
        "    def handle(self, event):\n"
        "        return event\n```"
    )

    def responder(system: str, prompt: str) -> str:
        if "EXAMPLE plugin" in prompt:
            return good_example
        if "Architecture Overview" in prompt:
            return "This codebase is extended by subclassing Backend."
        return "Subclass Backend and implement handle()."

    return responder


def test_docgen_verified() -> None:
    pkg = "dgok"
    with tempfile.TemporaryDirectory() as root:
        _write_pkg(root, pkg)
        try:
            provider = FakeProvider(_good_responder(pkg))
            out = os.path.join(root, "modding-docs")
            report = generate_docs(root, provider, out, min_score=0.5)

            # one confirmed point, example verified by actually loading it
            assert len(report.points) == 1
            gp = report.points[0]
            assert gp.fact.point_id == f"{pkg}.api:Backend"
            assert gp.example_status == "verified"
            assert report.verified_count == 1

            # both outputs written
            assert os.path.isfile(os.path.join(out, "index.md"))
            assert os.path.isfile(os.path.join(out, "plugin-guide.md"))
            assert os.path.isfile(os.path.join(out, gp.example_path))
            manifest_path = os.path.join(out, "extension-points.json")
            assert os.path.isfile(manifest_path)

            # manifest content
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            assert manifest["points"][0]["id"] == f"{pkg}.api:Backend"
            assert manifest["points"][0]["example"]["status"] == "verified"

            # grounding: every prompt is built from facts (carries the location),
            # and no method BODY leaks into any prompt
            assert provider.calls
            for _system, prompt in provider.calls:
                assert "return event" not in prompt  # example body never fed back
        finally:
            _cleanup(pkg)

    print("OK: docgen verified-path self-check passed")


def test_docgen_unverified_retries() -> None:
    pkg = "dgbad"
    with tempfile.TemporaryDirectory() as root:
        _write_pkg(root, pkg)
        try:
            # example compiles but defines no Backend subclass -> never validates
            provider = FakeProvider(
                lambda s, p: "```python\nx = 1\n```" if "EXAMPLE plugin" in p else "prose"
            )
            out = os.path.join(root, "modding-docs")
            # ask for 1 retry; must clamp up to the floor of 3
            report = generate_docs(root, provider, out, min_score=0.5, max_example_retries=1)

            gp = report.points[0]
            assert gp.example_status == "unverified"

            # retries clamped to the floor: exactly 3 example attempts for 1 point
            example_calls = sum(1 for _s, p in provider.calls if "EXAMPLE plugin" in p)
            assert example_calls == 3, example_calls

            # unverified is surfaced, not hidden
            index = open(os.path.join(out, "index.md"), encoding="utf-8").read()
            guide = open(os.path.join(out, "plugin-guide.md"), encoding="utf-8").read()
            assert "UNVERIFIED" in index
            assert "WARNING" in guide
        finally:
            _cleanup(pkg)

    print("OK: docgen unverified-retry self-check passed")


PROTO_SRC = (
    "from typing import Protocol, runtime_checkable\n"
    "\n"
    "__all__ = ['StorageBackend']\n"
    "\n"
    "@runtime_checkable\n"
    "class StorageBackend(Protocol):\n"
    "    model: str\n"
    "    def save(self, x) -> None: ...\n"
)


def test_docgen_protocol_seam_does_not_crash() -> None:
    """Regression: issubclass() against a Protocol base must not crash the run."""
    pkg = "dgproto"
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, pkg)
        os.makedirs(d)
        open(os.path.join(d, "__init__.py"), "w").close()
        with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
            fh.write(PROTO_SRC)
        try:
            example = (
                f"```python\nfrom {pkg}.api import StorageBackend\n"
                "class MyStore(StorageBackend):\n"
                "    model = 'm'\n"
                "    def save(self, x):\n"
                "        return None\n```"
            )
            provider = FakeProvider(
                lambda s, p: example if "EXAMPLE plugin" in p else "prose"
            )
            out = os.path.join(root, "modding-docs")
            # must complete without raising the Protocol issubclass TypeError
            report = generate_docs(root, provider, out, min_score=0.5)
            assert os.path.isfile(os.path.join(out, "extension-points.json"))
            # the point resolved to a status (not a crash); Protocol can't validate
            statuses = {p.example_status for p in report.points}
            assert statuses  # non-empty, run finished
        finally:
            _cleanup(pkg)

    print("OK: docgen protocol-seam regression passed")


REG_SRC = "__all__ = ['register']\n\n\ndef register(fn):\n    return fn\n"


def test_docgen_executed_status_for_registration() -> None:
    """Non-subclass seams get 'executed' when the example loads clean."""
    pkg = "dgexec"
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, pkg)
        os.makedirs(d)
        open(os.path.join(d, "__init__.py"), "w").close()
        with open(os.path.join(d, "api.py"), "w", encoding="utf-8") as fh:
            fh.write(REG_SRC)
        try:
            example = (
                f"```python\nfrom {pkg}.api import register\n"
                "@register\n"
                "def my_hook():\n"
                "    return 1\n```"
            )
            provider = FakeProvider(
                lambda s, p: example if "EXAMPLE plugin" in p else "prose"
            )
            out = os.path.join(root, "modding-docs")
            report = generate_docs(root, provider, out, min_score=0.5)
            reg = next(p for p in report.points if p.fact.symbol == "register")
            assert reg.example_status == "executed", reg.example_status
        finally:
            _cleanup(pkg)

    print("OK: docgen executed-status self-check passed")


if __name__ == "__main__":
    test_docgen_verified()
    test_docgen_unverified_retries()
    test_docgen_protocol_seam_does_not_crash()
    test_docgen_executed_status_for_registration()
