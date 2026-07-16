# MODScan

**Scan a codebase, get everything you need to write plugins and mods for it.**

MODScan reads a source-available project, finds where it can be *extended* —
hooks, event systems, dynamic loading, dependency injection, config-driven
behavior — and generates modding/plugin documentation grounded in real static
analysis. It doesn't just describe the code (Doxygen already does that); it maps
the **seams** a modder actually hooks into, then writes a "how to build a plugin"
guide and a **working example plugin that it validates by loading it for real**.

> Status: **MVP core complete.** All five analysis layers work (parse → graph →
> detect → validate → generate). The CLI wrapper is the next step.

---

## Why

Great mods and plugins have turned plain games and apps into masterpieces. But
getting started modding a project is painful: you have to reverse-engineer the
architecture yourself to find where you're even allowed to plug in. MODScan
automates that discovery step.

## What makes it different

Existing tools generate API docs from source. MODScan focuses on the hard,
valuable part everyone skips: **extension-point discovery**.

- Detects hooks, event/callback systems, dynamic import / plugin discovery,
  registration decorators, subclassable interfaces (ABCs / Protocols), and
  config/data-driven behavior.
- Ranks seams by how *moddable* they are.
- Grounds all generated docs in static analysis — **facts come from the parser,
  prose comes from the LLM, nothing is invented.**
- Closes the loop: the example plugin it generates must actually load into the
  target for the docs to be considered correct.

## How it works

```
source
  -> [1] AST Parser          deterministic, no LLM
  -> [2] Extension Graph     call graph, public seams
  -> [3] Extension Detector  heuristics + moddability ranking
  -> [5] Validator           generate an example plugin, actually load it
  -> [4] Doc Generator       LLM, grounded on the graph
  -> modding-docs/
```

Layers 1-3 are deterministic and verifiable. The LLM (layer 4) only explains
what the analysis found. The Validator (layer 5) is built *before* the doc
generator so every later stage is measurable against a plugin that really loads.

## Scope (MVP)

| In scope | Out of scope (for now) |
|---|---|
| Source-available codebases | Closed binaries / reverse engineering |
| Python (first target) | Every language at once |
| Core library + thin CLI | Web app / SaaS UI |

> **Note on closed / binary apps.** Modding a compiled, closed-source
> application (a typical commercial game) means decompilation and reverse
> engineering, which carries real legal implications (EULA, DMCA). That is
> deliberately **out of the MVP**. MODScan starts with code you are allowed to
> read and modify.

## LLM providers

The doc generator is provider-agnostic. Pick your model; SDKs are optional deps
imported lazily, so you install only what you use. API keys come from env vars,
never hardcoded.

| Provider | Install | Covers |
|---|---|---|
| `anthropic` (default) | `pip install modscan[anthropic]` | Claude (default model: `claude-opus-4-8`) |
| `openai` | `pip install modscan[openai]` | OpenAI, plus any OpenAI-compatible endpoint via `base_url`: Gemini, OpenRouter, DeepSeek, Mistral, local Ollama / LM Studio |

## Output

Two artifacts, one for humans and one for tools:

- `modding-docs/*.md` — architecture overview + per-seam plugin guide with a
  validated example plugin.
- `modding-docs/extension-points.json` — a versioned, machine-readable manifest
  of every validated extension point. This is the contract that will power
  `modscan scaffold <id>`, editor tooling, and breaking-change diffs.

Every generated example is re-loaded against the target to confirm it works;
ones that can't be validated are clearly marked `unverified`.

## Roadmap

1. ✅ AST parser + extension graph (Python)
2. ✅ Extension detector + moddability ranking
3. ✅ Validator — load a real example plugin against a detected seam
4. ✅ Doc generator (LLM, grounded) — Markdown + JSON manifest
5. ✅ `modscan ./path` CLI wrapper, end to end
6. ✅ `modscan scaffold <id>` — generate a plugin skeleton from the JSON manifest
7. Later: more languages (JS/TS), web UI, and — only with proper legal
   guardrails — the binary case

## Usage

```bash
pip install -e .[anthropic]        # or .[openai]
export ANTHROPIC_API_KEY=sk-...    # keys come from the environment, never flags

modscan ./path/to/project
# -> writes modding-docs/: index.md, plugin-guide.md, examples/*.py,
#    and extension-points.json
```

Common flags:

```bash
modscan ./proj --provider openai --model gpt-x --base-url http://localhost:11434/v1
modscan ./proj --min-score 0.6 --limit 20 --retries 5
modscan ./proj --no-validate-examples   # skip importing/executing target code
```

Then scaffold a ready-to-edit plugin from any documented extension point (no LLM,
reads the JSON manifest):

```bash
modscan scaffold "pkg.mod:Symbol" --manifest modding-docs/extension-points.json
# -> writes pkg_mod_Symbol_plugin.py: a concrete subclass with stubbed methods

modscan scaffold --all --out plugins/   # skeletons for every documented point
```

> **Trust note:** by default MODScan imports and executes code under the scanned
> path (and runs generated examples) to validate that plugins really load. Run it
> only on code you trust, or pass `--no-validate-examples`.

## License

[Apache License 2.0](LICENSE). Permissive, with an explicit patent grant — the
extension-point detection is the core value, so the patent clause is worth the
extra verbosity. See also [`NOTICE`](NOTICE).

---

*Planning docs live in [`.claude/plans/modscan.plan.md`](.claude/plans/modscan.plan.md).*
