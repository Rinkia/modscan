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

"""Opt-in live smoke test — makes a REAL LLM call, so it is OFF by default.

This is the only test that can hit a paid API. It runs only when MODSCAN_LIVE=1
AND a provider key is present in the environment; otherwise it skips cleanly and
returns success. Never add it to the always-on suite loop.

    # PowerShell
    $env:MODSCAN_LIVE = "1"; $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python tests/test_live_smoke.py

Provider is chosen from the environment: Anthropic if ANTHROPIC_API_KEY is set,
otherwise the OpenAI-compatible adapter if OPENAI_API_KEY is set.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.docgen import generate_docs  # noqa: E402
from modscan.providers import get_provider  # noqa: E402

_LIVE_SRC = (
    "from abc import ABC, abstractmethod\n"
    "\n"
    "__all__ = ['Plugin']\n"
    "\n"
    "class Plugin(ABC):\n"
    "    @abstractmethod\n"
    "    def run(self, context):\n"
    "        ...\n"
)


def _pick_provider():
    """Return (provider, name, model) from env, or None if no key is available."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        model = os.environ.get("MODSCAN_MODEL")  # None -> provider default (Opus)
        return get_provider("anthropic", model=model), "anthropic", model
    if os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("MODSCAN_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("OPENAI_BASE_URL")
        return get_provider("openai", model=model, base_url=base_url), "openai", model
    return None


def test_live_smoke() -> int:
    if os.environ.get("MODSCAN_LIVE") != "1":
        print("SKIP: live smoke test (set MODSCAN_LIVE=1 to run a real LLM call)")
        return 0

    picked = _pick_provider()
    if picked is None:
        print("SKIP: MODSCAN_LIVE=1 but no ANTHROPIC_API_KEY/OPENAI_API_KEY set")
        return 0

    provider, name, model = picked
    with tempfile.TemporaryDirectory() as root:
        pkg = os.path.join(root, "livepkg")
        os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").close()
        with open(os.path.join(pkg, "api.py"), "w", encoding="utf-8") as fh:
            fh.write(_LIVE_SRC)

        out = os.path.join(root, "modding-docs")
        report = generate_docs(root, provider, out, min_score=0.5)

        assert report.points, "live run produced no documented points"
        assert report.overview.strip(), "live run produced an empty overview"
        assert os.path.isfile(os.path.join(out, "extension-points.json"))
        try:
            for name_ in list(sys.modules):
                if name_ == "livepkg" or name_.startswith("livepkg."):
                    del sys.modules[name_]
        finally:
            pass

    print(f"OK: live smoke passed via {name} ({model or 'default'}), points={len(report.points)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(test_live_smoke())
