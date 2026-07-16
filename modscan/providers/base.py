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

"""Provider Protocol + registry + a FakeProvider for tests.

A provider is anything with `generate(system, prompt) -> str`. Real adapters
(anthropic, openai_compat) lazy-import their SDK so MODScan has no hard LLM
dependency — you install only the provider you use. API keys come from env vars,
never hardcoded.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

# Default model for the doc generator (layer 4). Anthropic's Opus 4.8.
DEFAULT_MODEL = "claude-opus-4-8"

# Provider names accepted by get_provider().
_ANTHROPIC = "anthropic"
_OPENAI_COMPAT = {"openai", "openai-compat", "openai_compat"}
_GEMINI = "gemini"
_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"


@runtime_checkable
class Provider(Protocol):
    """Minimal LLM interface the doc generator depends on."""

    model: str

    def generate(self, system: str, prompt: str) -> str:
        """Return the model's text completion for `prompt` under `system`."""
        ...


class FakeProvider:
    """Deterministic provider for tests — no network.

    `responder` is either a fixed string or a callable (system, prompt) -> str.
    Every call is recorded in `.calls` so tests can assert what was sent (e.g.
    that only fact blocks, never raw source, reach the model).
    """

    def __init__(
        self,
        responder: str | Callable[[str, str], str] = "",
        model: str = "fake",
    ) -> None:
        self._responder = responder
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if callable(self._responder):
            return self._responder(system, prompt)
        return self._responder


def get_provider(
    name: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> Provider:
    """Resolve a provider by name.

    - "anthropic" -> native Claude adapter
    - "openai" / "openai-compat" -> OpenAI-compatible adapter (set `base_url` to
      target OpenAI, Gemini, OpenRouter, DeepSeek, Mistral, Ollama, etc.)
    - "gemini" -> native Google Gemini adapter

    The SDK is imported lazily inside the adapter, so an unknown-but-uninstalled
    provider only fails when you actually call it.
    """
    key = name.lower()
    if key == _ANTHROPIC:
        from modscan.providers.anthropic import AnthropicProvider

        return AnthropicProvider(model=model or DEFAULT_MODEL, api_key=api_key)
    if key in _OPENAI_COMPAT:
        from modscan.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            model=model or DEFAULT_MODEL, api_key=api_key, base_url=base_url
        )
    if key == _GEMINI:
        from modscan.providers.gemini import GeminiProvider

        return GeminiProvider(model=model or _GEMINI_DEFAULT_MODEL, api_key=api_key)
    raise ValueError(
        f"unknown provider {name!r}; expected 'anthropic', 'openai', or 'gemini'"
    )
