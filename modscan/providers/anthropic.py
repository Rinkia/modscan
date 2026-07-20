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

"""Native Anthropic (Claude) provider adapter.

Lazy-imports the `anthropic` SDK so it is an optional dependency. Install with
`pip install modscan[anthropic]` (or `pip install anthropic`). The API key comes
from the ANTHROPIC_API_KEY env var unless passed explicitly.
"""

from __future__ import annotations

import os

from modscan.providers.base import DEFAULT_MAX_TOKENS


class AnthropicProvider:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def generate(self, system: str, prompt: str) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - trivial guard
            raise RuntimeError(
                "the 'anthropic' package is required for the Anthropic provider; "
                "install it with: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        # Response content is a list of blocks; concatenate the text ones.
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
