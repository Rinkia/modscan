# Changelog

All notable changes to MODScan are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-07-22

A free CI gate that fails a pull request removing or changing a library's
extension points, plus detect polish.

### Added

- **Breaking-change gate GitHub Action** (`Rinkia/modscan/breaking-change`). On a
  pull request it runs `modscan detect` on the PR and on the base branch, diffs
  the two, comments the diff, and fails the check when an extension point is
  removed or its category/kind changed — protecting a library's plugin/mod
  authors from silent breakage. No committed manifest, no LLM, no API key. The
  `examples/ci/breaking-change.yml` recipe is now this free one-liner, and
  MODScan runs the gate on its own API (`.github/workflows/extension-api-gate.yml`).
- **`modscan diff` accepts `detect --json` output** (a flat list) as well as the
  `{"points": [...]}` manifest, so the gate can diff free detect output with no
  LLM step. `category` joins the compared fields; `score` is never compared, so
  re-ranking alone is not a breaking change.
- **`modscan detect --label`** — a header label instead of the scan path, so
  committed or shared output (and the Action job summary) carries no local path.
- **`examples/detect-markdown.md`** — a free, committed `detect` sample on
  Python-Markdown.

### Fixed

- **No absolute scan path in detect ids.** A root-package symbol (empty qualname)
  fell back to the absolute scan path in Markdown and JSON ids and the
  registration location; it now uses the label, else the scan root's basename.
  JSON gains an explicit `module` field (`null` for root-package symbols).
- **The output directory is excluded from the scan.** Writing docs inside the
  scanned tree no longer means a later run parses this run's generated files;
  `parse_codebase` takes an `exclude`, and the run passes its output directory.

### Changed

- **GitHub Actions bumped off deprecated Node 20** — `checkout@v5`,
  `setup-python@v6`, `upload-artifact@v6`, `download-artifact@v7`.

## [0.1.2] - 2026-07-21

Robustness for runs against real, imperfect codebases, and cleaner output.

### Added

- **Pre-flight import probe.** Before a documentation run does expensive work, it
  checks whether the target imports. If the target or its dependencies cannot be
  imported, the run stops immediately — before any LLM call — with a classified
  cause (missing dependency vs. the target itself not importing) and a
  `pip install` remediation, instead of grinding through to empty docs. Rides the
  existing execute-code consent; `--no-validate-examples` skips it.
- **Classified drop reporting.** Extension points that fail validation are no
  longer filtered out silently: they are counted and labelled (`import_failed`,
  often a missing dependency, vs. `validation_failed`) in the CLI summary and in
  a "Not documented" section of `index.md`.
- **`modscan detect`: a separate "Plugin registration points" section.**
  `entry_points`-style loader sites — how a framework discovers plugins — are
  reported apart from the implement-this ranking and de-duplicated, so they no
  longer flood the top of a plugin-registry package's output.

### Changed

- **Runs are isolated.** Modules imported during validation are removed after the
  run, so two consecutive runs against different trees in one process no longer
  contaminate each other via cached modules of the same name.

### Fixed

- **The re-export signal now fires when scanning a parent directory**, not only
  when pointed straight at the package. A real checkout (or the showcase's temp
  copy) has the package nested one level down; the signal keys off filesystem
  structure so re-export ranking and importable, fully-qualified qualnames hold
  together. This is what made the first real documentation run produce zero
  points before the fix.
- **Self-scan guard.** The CLI warns when `--out` resolves inside the scanned
  tree, which would make a later run scan this run's generated files.

## [0.1.1] - 2026-07-21

### Added

- **`modscan detect`** — rank a codebase's extension points using static analysis
  only: no LLM, no API key, no code execution. Emits a Markdown table or `--json`.
  The fast way to try MODScan and the safe way to run it in CI. Mirrors the other
  no-LLM subcommands (`config`/`diff`/`scaffold`).
- **GitHub Action** (`action.yml`) — runs `detect` and writes the ranked
  extension points to a pull request's job summary. Safe on untrusted PRs (no
  LLM, no target-code execution).
- **MCP server** (`modscan[mcp]`, `modscan-mcp`) — exposes the offline detector
  as a tool for AI clients (Claude Desktop, Cursor). Reuses the exact `detect`
  path, so CLI and MCP cannot diverge.
- **Extension-point ranking benchmark** (`benchmarks/`) — a labelled ground truth
  over five real packages with a `score.py` reporting recall@10 and median rank,
  offline. A CI guard blocks any PR that edits both the labels and the ranking
  code in the same change.
- **Spend controls for LLM runs.** `--max-tokens` caps tokens generated per
  call, and `--max-calls` sets a hard ceiling on calls for the whole run,
  refusing to send call N+1 rather than silently producing a truncated
  document. Combine with `--cache-dir` so re-runs while tuning flags are free.
- `examples/generate_showcase.py` — generate a committable example run against a
  real project. Previews the detected points for free with `--dry-run`, prints
  the worst-case call count, requires `--yes` before spending, and caps itself
  at its own estimate.

### Changed

- **Re-export and override-point ranking signals**, each judged on the benchmark:
  re-exported public API and classes with an override point (a method raising
  `NotImplementedError`) now rank higher. Aggregate recall@10 rose from 4/12 to
  8/12 on the original three targets; see `benchmarks/README.md` for the measured
  before/after and the honest generalisation gaps on pygments and marshmallow.

### Fixed

- **Builtin `__import__` is no longer ranked as a plugin loader.** It is a
  general-purpose reflection / lazy-import primitive, not a plugin-discovery
  mechanism, and was flooding the top of the ranking on packages that lazy-load
  their own submodules. Still detected; scored as weak reflection evidence.
- **The OpenAI-compatible and Gemini adapters sent no token limit at all**, so a
  runaway response was unbounded. Every adapter now applies `DEFAULT_MAX_TOKENS`
  (4096) unless told otherwise; previously only the Anthropic one did.

## [0.1.0] - 2026-07-20

Everything since the MVP: more languages, more surfaces, safer execution, and a
substantial internal cleanup.

### Added

- **TypeScript/JavaScript front-end** (experimental, via tree-sitter). Parses
  `.ts/.tsx/.js/.jsx` into the shared model, so the graph, detector and docs work
  on JS/TS too. `--language typescript|javascript`; optional dependency
  `modscan[typescript]`. Example *execution*-validation remains Python-only.
- **Pluggable language front-ends** — `LanguageParser` protocol plus a registry,
  so a new language plugs in without touching the graph, detector or generator.
- **`modscan diff`** — compare two `extension-points.json` manifests and report
  removed / changed / added extension points. Exits non-zero on breaking
  changes, so it can gate CI. A copy-paste workflow that comments the diff on a
  pull request ships in `examples/ci/breaking-change.yml`.
- **`modscan config`** — detect config/data-driven modding surfaces (manifest
  files, drop-in directories) that the AST detector cannot see.
- **`modscan scaffold --all`** — generate plugin skeletons for every point in a
  manifest in one command.
- **Subprocess sandbox** (`--sandbox`) — validate generated examples in an
  isolated child process with a timeout, containing hangs and crashes when the
  target is less trusted.
- **On-disk LLM response cache** (`--cache-dir`) — memoises responses by
  provider, endpoint, model and prompt, making re-runs free and offline.
- **Native Gemini provider** (`--provider gemini`), alongside Anthropic and the
  OpenAI-compatible adapter.
- **Concurrency for the LLM fan-out** (`--concurrency`, default 1). A run is
  dominated by `1 + points x (1..retries)` sequential network round-trips; this
  is where the wall-clock time is. Output is unaffected — results are collected
  in input order and in-process validation is serialised.
- **`executed` example status** — hook/registration examples are now executed,
  not merely compile-checked, so bad imports and runtime errors are caught.
- Continuous integration across Python 3.10–3.13, and an opt-in live smoke test
  (`MODSCAN_LIVE=1`) that is the only test allowed to make a real API call.
- Contributor documentation (`CONTRIBUTING.md`) and README badges.

### Changed

- **Single source of truth for code execution.** Loading a target, executing an
  example, finding a concrete subclass and instantiating it previously existed
  three times — in the validator, in the generator, and again as a Python string
  inside the sandbox runner. It now lives once in `modscan/execution.py`, and the
  sandbox child imports that module instead of carrying a copy.
- **`docgen` split into a package** (`pipeline`, `examples`, `render`, `types`).
  The public API is unchanged.
- **Domain types moved to `models.py`** (`Seam`, `ExtensionPoint`), so layers no
  longer import each other merely to name a type. Old import paths still resolve.
- **Example statuses are an enum** (`models.ExampleStatus`) instead of strings
  re-spelled across four modules. It subclasses `str`, so the JSON manifest is
  byte-for-byte unchanged.
- **One filesystem convention** — `SKIP_DIRS`, source walking and slug
  generation live in `modscan/fsutil.py`.
- Library-safe logging: a `NullHandler` on the package root, plus debug logs
  where failures were previously swallowed without a trace.

### Fixed

- **Crash on `typing.Protocol` seams.** Scanning a codebase that defines a
  `runtime_checkable` Protocol with a data member aborted the run, because
  `issubclass` raises for those and the call sat outside the guard. Found by
  running MODScan on itself.
- **Divergent directory skipping.** `SKIP_DIRS` was defined three times with
  three different values, so the same tree produced different results depending
  on which scanner asked — `dist/` was walked by the Python parser but skipped
  elsewhere, `.venv/` was walked by the TypeScript one. Now unified. *This is a
  deliberate behavior change: build output and virtualenvs are consistently
  skipped.*
- **More dynamic-import calls detected** — `import_string`, `load_entry_point`,
  `iter_entry_points`, `load_module`, `find_spec` and `get_loader` now register
  as plugin-loader seams. Thanks to [@AjibadeHassan](https://github.com/AjibadeHassan)
  for the first external contribution ([#18](https://github.com/Rinkia/modscan/pull/18)).
- **Silent point loss.** Point selection relied on `zip()` truncating against a
  shorter validation list; the limit is now applied explicitly and the zip is
  strict, so a mismatch fails loudly.
- `javascript` examples are written as `.js` with a `javascript` code fence
  (previously `.ts`/`typescript`).
- Cache keys include the provider and endpoint, so the same model and prompt
  against two different backends can no longer collide.
- Removed a dead import left behind by the language-front-end integration.

### Known limitations

- Imported target modules are never unloaded, so a long-lived process
  accumulates them and a second scan of a different tree using the same package
  name reuses the first. Restoring `sys.modules` safely needs its own change.
- Generating docs *into* the tree being scanned makes the next run pick up its
  own generated examples. Write the output elsewhere, or ignore the output
  directory.

## [0.0.1] - 2026-07-16

Initial MVP: the full pipeline, end to end.

### Added

- AST parser and extension graph for Python — deterministic facts only.
- Extension-point detector with transparent signal-sum scoring and moddability
  ranking.
- Validator that proves a seam by actually loading a probe plugin into it.
- Grounded doc generator: facts from the parser, prose from an LLM, correctness
  from the validator. The model only ever sees structured fact blocks, never raw
  source. Generated examples are re-validated, with retries, and anything that
  cannot be confirmed is labelled `unverified`.
- Provider-agnostic LLM layer (Anthropic default, OpenAI-compatible adapter),
  with SDKs as optional, lazily imported dependencies.
- Markdown documentation plus a versioned, machine-readable
  `extension-points.json` manifest.
- `modscan <path>` CLI and `modscan scaffold <id>` for generating plugin
  skeletons from the manifest.
- Apache-2.0 licensing.

[Unreleased]: https://github.com/Rinkia/modscan/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/Rinkia/modscan/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Rinkia/modscan/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Rinkia/modscan/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Rinkia/modscan/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/Rinkia/modscan/releases/tag/v0.0.1
