# Changelog

All notable changes to MODScan are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

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

[Unreleased]: https://github.com/Rinkia/modscan/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Rinkia/modscan/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/Rinkia/modscan/releases/tag/v0.0.1
