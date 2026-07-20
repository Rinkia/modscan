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
