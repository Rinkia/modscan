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

"""Pluggable language front-ends.

Each language turns source into the same `Codebase` model (models.py) that the
rest of the pipeline — graph, detector, doc generator — already consumes. This
package is the seam that lets non-Python languages (JS/TS next) plug in without
touching layers 2-5.

Importing this package registers the built-in Python front-end.
"""

from modscan.languages.base import (
    LanguageParser,
    available_languages,
    get_language_parser,
    register_language,
)
from modscan.languages import python as _python  # noqa: F401 — registers "python"
from modscan.languages import (  # noqa: F401 — registers "typescript"/"javascript"
    typescript as _typescript,
)

__all__ = [
    "LanguageParser",
    "available_languages",
    "get_language_parser",
    "register_language",
]
