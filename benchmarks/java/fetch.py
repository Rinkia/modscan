#!/usr/bin/env python
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

"""Fetch the pinned Java benchmark targets from Maven Central.

Java has no `pip install` or `npm install` that leaves readable sources on disk,
but Maven Central publishes a version-pinned ``-sources.jar`` for most
artifacts — which is a jar of exactly the source the benchmark needs.

    python benchmarks/java/fetch.py

Each target is unpacked to ``benchmarks/java/<name>-<version>/``. The version is
carried in the directory name rather than a metadata file, so the scorer can
check it structurally and skip a target installed at the wrong version, the same
discipline the pip and npm targets follow. Extracted sources are gitignored.
"""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
GROUND_TRUTH = os.path.join(os.path.dirname(HERE), "ground_truth.json")
MAVEN_CENTRAL = "https://repo1.maven.org/maven2"


def sources_url(coordinate: str, version: str) -> str:
    """Maven Central URL of the -sources.jar for `group:artifact` at `version`."""
    group, artifact = coordinate.split(":", 1)
    return (
        f"{MAVEN_CENTRAL}/{group.replace('.', '/')}/{artifact}/{version}/"
        f"{artifact}-{version}-sources.jar"
    )


def target_dir(name: str, version: str) -> str:
    return os.path.join(HERE, f"{name}-{version}")


def fetch(name: str, coordinate: str, version: str) -> None:
    dest = target_dir(name, version)
    if os.path.isdir(dest):
        print(f"{name} {version}: already present")
        return
    url = sources_url(coordinate, version)
    print(f"{name} {version}: fetching {url}")
    try:
        raw = urllib.request.urlopen(url, timeout=120).read()
    except OSError as exc:
        print(f"  ! failed: {exc}", file=sys.stderr)
        return
    os.makedirs(dest, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(raw)).extractall(dest)
    print(f"  -> {dest}")


def main() -> int:
    with open(GROUND_TRUTH, encoding="utf-8") as fh:
        truth = json.load(fh)

    java_targets = {
        name: t
        for name, t in truth["targets"].items()
        if t.get("language") == "java" and t.get("maven")
    }
    if not java_targets:
        print("no java targets declared in ground_truth.json")
        return 0
    for name, t in sorted(java_targets.items()):
        fetch(name, t["maven"], t["version"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
