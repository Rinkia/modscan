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

"""On-disk response cache wrapper for any provider.

Doc generation makes several LLM calls per run; re-running (after tweaking
--min-score, iterating on a target, or debugging) repeats identical prompts.
CachingProvider wraps any Provider and memoizes responses to disk keyed by
(model, system, prompt), so repeats are free and offline.

ponytail: content-addressed files under a directory — no expiry, no size cap.
The key includes the model, so switching models never returns a stale answer;
delete the cache dir to invalidate. Good enough for a dev-time cache; add
eviction only if the directory actually gets large.
"""

from __future__ import annotations

import hashlib
import os

from modscan.providers.base import Provider


class CachingProvider:
    def __init__(self, inner: Provider, cache_dir: str) -> None:
        self.inner = inner
        self.model = inner.model
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _key(self, system: str, prompt: str) -> str:
        # Include the provider identity and endpoint so the same model+prompt
        # against a different backend (e.g. two OpenAI-compatible base_urls, or a
        # different provider) never returns a cross-wired cached answer.
        provider_id = type(self.inner).__name__
        base_url = getattr(self.inner, "_base_url", "") or ""
        digest = hashlib.sha256()
        # NUL separators keep the fields unambiguous in the hashed material.
        material = f"{provider_id}\0{base_url}\0{self.model}\0{system}\0{prompt}"
        digest.update(material.encode("utf-8"))
        return digest.hexdigest()

    def generate(self, system: str, prompt: str) -> str:
        path = os.path.join(self.cache_dir, self._key(system, prompt) + ".txt")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        result = self.inner.generate(system, prompt)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(result)
        return result
