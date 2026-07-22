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

"""Language front-end interface + registry.

A LanguageParser turns a source tree into the shared `Codebase` model. Concrete
front-ends register themselves by name; callers resolve one with
`get_language_parser`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from modscan.models import Codebase


@runtime_checkable
class LanguageParser(Protocol):
    name: str

    def parse_codebase(self, root: str, exclude: tuple[str, ...] = ()) -> Codebase:
        """Parse every source file of this language under `root`.

        `exclude` lists directory paths to keep out of the scan — used to skip a
        run's own output directory when it sits inside the scanned tree.
        """
        ...


_REGISTRY: dict[str, LanguageParser] = {}


def register_language(parser: LanguageParser) -> None:
    _REGISTRY[parser.name] = parser


def get_language_parser(name: str) -> LanguageParser:
    try:
        return _REGISTRY[name]
    except KeyError:
        avail = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(f"unknown language {name!r}; available: {avail}") from None


def available_languages() -> list[str]:
    return sorted(_REGISTRY)
