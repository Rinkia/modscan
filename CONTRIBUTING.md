# Contributing to MODScan

Thanks for your interest. MODScan turns a source-available codebase into
plugin/mod documentation. Contributions are welcome — read this first so your
change lands smoothly.

## Getting started

```bash
git clone https://github.com/Rinkia/modscan
cd modscan
python -m pip install -e .            # core, no LLM SDK required
# optional, only if you touch a real provider:
python -m pip install -e .[anthropic] # or .[openai]
```

Python 3.10+ is required. The core has **no runtime dependencies**; LLM SDKs are
optional extras, imported lazily.

## Running the tests

No test framework is required — each self-check runs standalone:

```bash
for t in parser detector validator providers factblocks manifest docgen cli scaffold; do
  python tests/test_$t.py
done
```

They are also discoverable by `pytest` if you prefer. **The suite makes no
network calls** — LLM providers are exercised through `FakeProvider`. Never add a
test that hits a real API to the always-on suite.

The one exception is `tests/test_live_smoke.py`: an opt-in end-to-end check that
makes a **real, paid LLM call**. It is off by default and skips unless you set
`MODSCAN_LIVE=1` and provide a provider key:

```bash
MODSCAN_LIVE=1 ANTHROPIC_API_KEY=sk-ant-... python tests/test_live_smoke.py
```

## Architecture (know before you change)

MODScan is a layered pipeline. Keep the boundaries:

| Layer | File | Rule |
| --- | --- | --- |
| 1 Parse | `parser.py` | Deterministic AST facts only |
| 2 Graph | `graph.py` | Module deps + seam inventory |
| 3 Detect | `detector.py` | Transparent signal-sum scoring, no magic numbers |
| 4 Docs | `docgen.py`, `providers/`, `prompts.py` | LLM writes prose **only** from fact blocks |
| 5 Validate | `validator.py` | Confirms a seam by loading a probe plugin |
| — Manifest | `manifest.py` | Deterministic `extension-points.json` |
| — Scaffold | `scaffold.py` | Deterministic; **no LLM** |

**The golden rule:** facts come from the parser, prose comes from the LLM,
correctness comes from the validator. The model only ever sees fact blocks
(`factblocks.py`) — never raw source. Don't route real source text into a prompt.

## Trust boundary

`validator.py` and `docgen.py` **import and execute target code** to confirm
plugins load. This is deliberate and opt-in. Don't make it automatic on
parse/scan, and don't remove the warnings.

## Code style

- PEP 8; type annotations on function signatures.
- Format with **black**, lint with **ruff**.
- Prefer small, focused files and `@dataclass(frozen=True)` for value objects.
- Add the Apache-2.0 header to every new `.py` file (copy it from any existing
  source file).
- Non-trivial logic ships with a runnable self-check (`tests/test_*.py`,
  assert-based, no fixtures/frameworks unless needed).

## Pull requests

1. Branch from `master`.
2. Keep the diff focused; one concern per PR.
3. Make the full self-check suite pass.
4. Use clear commit messages (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`).
5. Describe what changed and how you verified it.

## License

By contributing, you agree your contributions are licensed under the
[Apache License 2.0](LICENSE), the project's license.
