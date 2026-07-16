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

"""OpenAI-compatible provider adapter.

One adapter, many backends: point `base_url` at any OpenAI-compatible endpoint —
OpenAI itself (default), Google Gemini's compat endpoint, OpenRouter, DeepSeek,
Mistral, or a local Ollama / LM Studio server. Lazy-imports the `openai` SDK so
it stays an optional dependency. API key from OPENAI_API_KEY unless passed.
"""

from __future__ import annotations

import os


class OpenAICompatProvider:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url  # None -> the SDK's default (api.openai.com)

    def generate(self, system: str, prompt: str) -> str:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - trivial guard
            raise RuntimeError(
                "the 'openai' package is required for the OpenAI-compatible "
                "provider; install it with: pip install openai"
            ) from exc

        client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""
