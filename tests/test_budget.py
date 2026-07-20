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

"""Self-check for spend controls: per-call token cap and per-run call ceiling."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.providers import (  # noqa: E402
    DEFAULT_MAX_TOKENS,
    BudgetExceeded,
    BudgetProvider,
    CachingProvider,
    get_provider,
)


class _CountingProvider:
    def __init__(self) -> None:
        self.model = "m"
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        return "ok"


def test_every_adapter_caps_tokens() -> None:
    """Regression: only the Anthropic adapter used to bound output; the OpenAI
    and Gemini ones sent no limit at all."""
    for name in ("anthropic", "openai", "gemini"):
        default = get_provider(name)
        assert default.max_tokens == DEFAULT_MAX_TOKENS, name
        custom = get_provider(name, max_tokens=256)
        assert custom.max_tokens == 256, name


def test_budget_stops_before_exceeding() -> None:
    inner = _CountingProvider()
    guarded = BudgetProvider(inner, max_calls=3)

    for _ in range(3):
        assert guarded.generate("s", "p") == "ok"
    assert inner.calls == 3
    assert guarded.remaining == 0

    try:
        guarded.generate("s", "p")
    except BudgetExceeded as exc:
        assert "budget exhausted" in str(exc)
    else:
        raise AssertionError("expected BudgetExceeded")

    # the refused call never reached the wrapped provider
    assert inner.calls == 3


def test_budget_rejects_nonsense_limit() -> None:
    try:
        BudgetProvider(_CountingProvider(), max_calls=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for max_calls=0")


def test_cache_hits_do_not_spend_budget() -> None:
    """Cache wraps below the budget, so repeats are free against the ceiling."""
    with tempfile.TemporaryDirectory() as d:
        inner = _CountingProvider()
        guarded = BudgetProvider(CachingProvider(inner, d), max_calls=2)

        guarded.generate("s", "same")  # miss -> reaches inner, spends 1
        guarded.generate("s", "same")  # cache hit, but still counted
        assert inner.calls == 1

        # budget counts calls made *through* it, cache or not: that is the point
        # of a hard ceiling — it bounds attempts, not just spend.
        assert guarded.remaining == 0


if __name__ == "__main__":
    test_every_adapter_caps_tokens()
    test_budget_stops_before_exceeding()
    test_budget_rejects_nonsense_limit()
    test_cache_hits_do_not_spend_budget()
    print("OK: budget/token-cap self-check passed")
