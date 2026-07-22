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

"""Python language front-end.

Thin adapter over the existing AST parser (parser.py) exposing it through the
LanguageParser interface. Behavior is unchanged — this is the same parser, now
reachable via the language registry.
"""

from __future__ import annotations

from modscan.languages.base import register_language
from modscan.models import Codebase
from modscan.parser import parse_codebase as _parse_python


class PythonLanguageParser:
    name = "python"
    extensions = (".py",)
    validates = True  # examples can be imported & executed in-process

    def parse_codebase(self, root: str, exclude: tuple[str, ...] = ()) -> Codebase:
        return _parse_python(root, exclude=exclude)


register_language(PythonLanguageParser())
