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

"""Native Google Gemini provider adapter.

Gemini is also reachable through the OpenAI-compatible adapter via base_url;
this native adapter uses the google-generativeai SDK directly for those who
prefer it. Lazy-imports the SDK (optional dep: pip install modscan[gemini]).
API key from GEMINI_API_KEY (or GOOGLE_API_KEY) unless passed explicitly.
"""

from __future__ import annotations

import os


class GeminiProvider:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = (
            api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )

    def generate(self, system: str, prompt: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - trivial guard
            raise RuntimeError(
                "the 'google-generativeai' package is required for the Gemini "
                "provider; install it with: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=self._api_key)
        client = genai.GenerativeModel(self.model, system_instruction=system)
        response = client.generate_content(prompt)
        return response.text or ""
