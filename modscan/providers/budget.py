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

"""A hard ceiling on how many LLM calls a single run may make.

`max_tokens` caps the size of one response; it does not cap a *run*. A doc
generation makes `1 + points x (1..retries)` calls, so pointing MODScan at a
large codebase without a ceiling is the realistic way to burn a month of credit
in one afternoon.

BudgetProvider wraps any provider and refuses to make call N+1. It raises rather
than returning something fake: a silently truncated run would produce docs that
look complete but are not, which is worse than stopping.

Pair it with `--cache-dir`: cached responses never reach the wrapped provider,
so re-runs while you tune flags cost nothing against the budget.
"""

from __future__ import annotations

import threading

from modscan.providers.base import Provider


class BudgetExceeded(RuntimeError):
    """Raised when a run hits its configured call ceiling."""


class BudgetProvider:
    def __init__(self, inner: Provider, max_calls: int) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        self.inner = inner
        self.model = inner.model
        self.max_calls = max_calls
        self.calls = 0
        self._lock = threading.Lock()  # generate() runs under --concurrency

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.calls)

    def generate(self, system: str, prompt: str) -> str:
        with self._lock:
            if self.calls >= self.max_calls:
                raise BudgetExceeded(
                    f"LLM call budget exhausted after {self.calls} calls "
                    f"(--max-calls {self.max_calls}). Nothing further was sent. "
                    "Narrow the run with --limit / --min-score, reuse work with "
                    "--cache-dir, or raise --max-calls deliberately."
                )
            self.calls += 1
        return self.inner.generate(system, prompt)
