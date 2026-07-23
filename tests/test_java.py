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

"""Self-check for the Java front-end.

Skips cleanly (exit 0) when tree-sitter-java is not installed, so the core CI —
which installs no optional deps — stays green. Install to run:
    pip install modscan[java]
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HAVE_JAVA = (
    importlib.util.find_spec("tree_sitter") is not None
    and importlib.util.find_spec("tree_sitter_java") is not None
)

from modscan.languages import available_languages, get_language_parser  # noqa: E402
from modscan.graph import build_graph  # noqa: E402
from modscan.detector import detect_extension_points  # noqa: E402

# Each trap from the plan appears once: generics on the bases, annotation with
# arguments, a nested class, a package-private class, an interface, a record.
_SRC = """\
package com.example.api;

import com.example.core.Core;
import static com.example.util.Helpers.log;

@Plugin(name = "renderer", priority = 2)
public abstract class BaseMod<T> extends Core<T> implements Hook, com.example.Other {
  public abstract void onTick(long dt);

  private int internal() { return 1; }

  static class Inner {
    public void notASeam() {}
  }
}

public interface RenderPlugin {
  void render(String scene);
}

public record Coords(int x, int y) {}

class PackagePrivate {}
"""


def test_java_registered() -> None:
    assert "java" in available_languages()


def test_java_parses_into_seams() -> int:
    if not _HAVE_JAVA:
        print("SKIP: java front-end (pip install modscan[java] to run)")
        return 0

    with tempfile.TemporaryDirectory() as root:
        pkg = os.path.join(root, "com", "example", "api")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "BaseMod.java"), "w", encoding="utf-8") as fh:
            fh.write(_SRC)

        cb = get_language_parser("java").parse_codebase(root)
        module = cb.modules[0]
        # dotted, package-style qualname so a label id reads like Java does
        assert module.qualname == "com.example.api.BaseMod", module.qualname

        classes = {c.name: c for c in module.classes}

        # nested class is NOT a top-level seam
        assert "Inner" not in classes, "an inner class must not become its own seam"

        base = classes["BaseMod"]
        assert base.is_public is True
        assert base.is_abstract is True
        # generics stripped, package qualifier dropped, both extends+implements kept
        assert base.bases == ("Core", "Hook", "Other"), base.bases
        # annotation reduced to its name, arguments dropped
        assert base.decorators == ("Plugin",), base.decorators
        assert {m.name for m in base.methods} == {"onTick", "internal"}

        # an interface is a contract to implement -> abstract by construction
        assert classes["RenderPlugin"].is_abstract is True
        assert classes["RenderPlugin"].is_public is True

        # a record is concrete
        assert classes["Coords"].is_abstract is False

        # no `public` modifier -> package-private, so not a public seam
        assert classes["PackagePrivate"].is_public is False

        # imports feed the dependency graph; `import static` is handled
        imported = {i.module for i in module.imports}
        assert "com.example.core.Core" in imported
        assert any("Helpers" in m for m in imported), imported
    return 0


def test_detector_ranks_java_seams() -> int:
    if not _HAVE_JAVA:
        print("SKIP: java detector (pip install modscan[java] to run)")
        return 0

    with tempfile.TemporaryDirectory() as root:
        pkg = os.path.join(root, "com", "example", "api")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "BaseMod.java"), "w", encoding="utf-8") as fh:
            fh.write(_SRC)

        points = detect_extension_points(
            build_graph(get_language_parser("java").parse_codebase(root))
        )
        by_name = {p.seam.name: p for p in points}

        # the language-agnostic detector treats them as subclass seams
        assert by_name["BaseMod"].category == "subclass"
        assert by_name["RenderPlugin"].category == "subclass"
        # package-private and nested classes never reach the ranking
        assert "PackagePrivate" not in by_name
        assert "Inner" not in by_name
    return 0


if __name__ == "__main__":
    test_java_registered()
    test_java_parses_into_seams()
    test_detector_ranks_java_seams()
    print("OK: java self-check passed")
