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

"""Self-check for the provider layer. No network: FakeProvider only."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modscan.providers import DEFAULT_MODEL, FakeProvider, Provider, get_provider  # noqa: E402


def test_providers() -> None:
    # FakeProvider satisfies the Protocol and records calls
    fake = FakeProvider("hello", model="fake-1")
    assert isinstance(fake, Provider)
    assert fake.generate("sys", "prompt") == "hello"
    assert fake.calls == [("sys", "prompt")]

    # callable responder sees system + prompt
    echo = FakeProvider(lambda system, prompt: f"{system}|{prompt}")
    assert echo.generate("S", "P") == "S|P"

    # registry resolves both provider families without importing SDKs
    anth = get_provider("anthropic")
    assert anth.model == DEFAULT_MODEL
    assert type(anth).__name__ == "AnthropicProvider"

    for name in ("openai", "openai-compat", "openai_compat"):
        oai = get_provider(name, model="gpt-x", base_url="http://localhost:1234/v1")
        assert type(oai).__name__ == "OpenAICompatProvider"
        assert oai.model == "gpt-x"

    # gemini resolves and defaults to a Gemini model (not the Claude default)
    gem = get_provider("gemini")
    assert type(gem).__name__ == "GeminiProvider"
    assert gem.model.startswith("gemini-")
    assert get_provider("gemini", model="gemini-1.5-pro").model == "gemini-1.5-pro"

    # unknown provider fails clearly
    try:
        get_provider("nope")
    except ValueError as exc:
        assert "unknown provider" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown provider")

    print("OK: provider layer self-check passed")


if __name__ == "__main__":
    test_providers()
