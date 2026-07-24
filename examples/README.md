# Examples

## `generate_showcase.py` — MODScan run against a real project

An example output committed in the repository is the most convincing thing this
project can show: real code, real extension points, and an honest view of what
the ranking gets right and wrong.

```bash
# Free: see what would be documented, no API calls at all
python examples/generate_showcase.py --dry-run

# Real run (makes PAID API calls)
export ANTHROPIC_API_KEY=sk-ant-...
python examples/generate_showcase.py --target click --yes
```

Output lands in `examples/showcase-<target>/`. Review it before committing —
particularly whether the ranking surfaced the seams a real plugin author would
care about.

### Spend controls

This script calls a paid API, so it defaults to being careful:

| Control | Default | What it does |
|---|---|---|
| `--dry-run` | — | Preview detected points for free; nothing is sent |
| `--yes` | required | A real run refuses to start without it |
| `--limit` | 8 | How many extension points get documented |
| `--max-tokens` | 2048 | Cap on tokens generated *per call* |
| `--cache-dir` | `.showcase-cache/` | Re-runs while tuning flags are free and offline |
| (automatic) | — | A hard `BudgetProvider` ceiling equal to the printed worst case, so the run cannot exceed its own estimate |

The worst-case call count is printed before anything is sent:
`1 + points x (1 + retries)`.

### Choosing a target

`--target` accepts an installed package name or a path to a source tree. An
installed package is copied to a temp dir as `<tmp>/<pkg>/` so module qualnames
match what `import` expects — the same layout a repo checkout has.

Good showcase targets are mid-sized projects with a clear extension story.
`click` works well: MODScan surfaces `ParamType` and `Parameter`, which really
are how you extend it.

Large applications (Home Assistant, Django) need more care:

- **Install the target first** (`pip install -e .` in its checkout). Validation
  *imports* target modules; without their dependencies installed, most imports
  fail and those points get filtered out, leaving thin docs.
- **Scan a subtree, not the whole repo.** Thousands of modules means thousands
  of candidate points and a matching API bill.
- **Write output outside the scanned tree**, or the next run will scan the
  examples the previous one generated.

## Committed example: `showcase-click/`

A real MODScan run against click 8.4.2 (`--limit 4`), committed so you can see
what it produces without spending anything. It is an honest sample, not a
cherry-picked one:

- **`ParamType`** is documented with a **verified** example — the generated
  `MyParamType(ParamType)` subclass was executed and loaded successfully. This is
  the seam a real click user extends, and MODScan both found it and produced
  working code for it.
- Two decorator hooks (`confirmation_option`, `version_option`) are documented
  with generated examples.
- **`Parameter` (ranked #1) does not appear**: its example failed validation, so
  it was dropped rather than documented on faith. MODScan documents what it can
  prove — a thinner but honest result is the design.

## Committed example: `detect-markdown.md` (free, no API key)

[`detect-markdown.md`](detect-markdown.md) is a real `modscan detect` run against
Python-Markdown 3.10.2 — static analysis only, no LLM, no API key. It is the free
counterpart to the click showcase above: nothing to spend, instant to reproduce,
on a package with a large third-party extension community.

Honest reading, not cherry-picked:

- MODScan locks onto markdown's **extension surface**: the top rows are all
  `*Extension` classes. But those are the built-in *implementations*; the base
  `Extension` and the processor bases a plugin author actually subclasses
  (`Treeprocessor`, `BlockProcessor`, …) rank lower — the same generalisation gap
  measured in [`../benchmarks/README.md`](../benchmarks/README.md).
- The **Plugin registration points** section shows how markdown discovers plugins
  (`entry_points`, plus `import_module`/`find_spec` loader sites), reported apart
  from the implement-this ranking rather than flooding it.
- The note under the header is the honest part: **eighteen candidates tie at
  1.00 and the run shows twelve**, so the six left out were cut by module name,
  not by evidence. Without that line the twelve rows read as a ranking. They are
  a band with an alphabetical cut through it.

Reproduce it (free):

```bash
pip install markdown==3.10.2
# fully-qualified ids (markdown.*) need the package under a parent dir, as a real
# checkout has it — copy it into an empty dir, then scan that:
python - <<'PY'
import os, importlib, shutil, tempfile, subprocess
md = os.path.dirname(importlib.import_module("markdown").__file__)
tmp = tempfile.mkdtemp(); shutil.copytree(md, os.path.join(tmp, "markdown"))
subprocess.run(["modscan", "detect", tmp, "--min-score", "0.5",
                "--limit", "12", "--label", "markdown 3.10.2"])
PY
```

`--label` keeps the local scan path out of the output, so the committed file is
exactly what the command prints.
