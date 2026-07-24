# Changelog

All notable changes to MODScan are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`--version` on both CLIs** — `modscan --version` and `modscan-audit --version`
  print the installed version and exit 0. Read from package metadata
  (`modscan.__version__`), never hardcoded, so it cannot drift from
  `pyproject.toml`; a source checkout that is not installed reports
  `0.0.0+unknown` rather than lying.

## [0.1.7] - 2026-07-23

A third language, a second lens over MCP, and two TypeScript front-end defects
found by pointing the benchmark at real packages.

### Added

- **Java front-end** — `modscan detect --language java` (and the docgen and
  security paths that follow the language registry). Java maps onto the shared
  model more directly than any front-end so far: `class`, `interface` and
  `abstract class` are already its vocabulary, `extends`/`implements` are bases,
  annotations play the part decorators do elsewhere, and visibility comes from
  the explicit `public` modifier rather than being inferred. Generic bases are
  reduced to their bare name (`Core<T>` -> `Core`), annotation arguments are
  dropped (`@Plugin(name="x")` -> `Plugin`), and nested classes are deliberately
  not emitted as top-level seams — an inner class is reached through its outer
  one. Optional dependency: `pip install modscan[java]`.

- **The security lens is exposed over MCP** — `modscan-mcp` gains an
  `audit_attack_surface` tool beside `detect_extension_points`, so an AI client
  can map where untrusted code enters as well as where a codebase is extensible.
  It returns exactly the payload `modscan-audit --json` emits, built through the
  same renderer so the two cannot drift — which means the non-coverage disclaimer
  travels with the data and an empty result still says it is not a clean bill of
  health. The two tools keep their own vocabulary: moddability and attack surface
  are different questions, and neither answer is phrased in the other's terms.

- **The security lens covers TypeScript/JavaScript** — `modscan-audit --language
  typescript` (or `javascript`) maps `eval`, `Function`/`new Function`, the `vm`
  module, the `child_process` family, dynamic `require`/`import`, and string-body
  `setTimeout`/`setInterval`, reusing the existing tree-sitter front-end. Modelled
  on `eslint-plugin-security`, the JS counterpart to Bandit: a computed
  `require(name)` is a sink but a literal `require('fs')` is not, matching its
  `detect-non-literal-require` rule. Shell-invoking `child_process.exec` rates
  high, the no-shell family medium — the same split the Python catalog makes.
  Because idiomatic JS destructures (`const {exec} = require('child_process')`),
  each file's `require`/`import` bindings are resolved before matching, so aliased
  and destructured calls are found while `someRegex.exec(str)` and `JSON.parse`
  are not. Binding resolution is file-local: a binding passed through another
  module is not followed.

- **More process sinks, and `shell=True` now raises severity.** Cross-checking the
  security lens against Bandit on real packages surfaced a genuine gap: `os.popen`,
  `os.startfile`, the `os.exec*`/`os.spawn*` family and `commands.getoutput` were
  not catalogued. They are now, split the way Bandit splits B605 from B606 — calls
  that hand a string to a shell (`os.system`, `os.popen`) rate **high**, calls that
  launch a program without one rate **medium**. A `subprocess.*` call passing a
  literal `shell=True` is elevated to **high** (only a literal counts; a variable
  could be either, and guessing would inflate severity on evidence the parser does
  not have). With the gate's `fail-on: high` default, this means a newly-introduced
  `shell=True` now fails a PR while an ordinary `subprocess.run` still does not.

### Fixed

- **CommonJS exports are recognised.** The TypeScript/JavaScript front-end marked
  a symbol public only from the ESM `export` keyword, so every CommonJS file —
  most of npm — reported zero public symbols and contributed no extension points
  at all. `exports.X = X`, `module.exports.X = X`, `module.exports = X` and
  `module.exports = { X, Y }` now mark the named declarations public. Found by
  scanning commander, whose entire `lib/` implementation was invisible.
- **`.d.ts` declaration files are no longer scanned.** A declaration file
  declares types for code defined elsewhere, so scanning it produced a phantom
  copy of every symbol, and option-bag interfaces that exist only as declarations
  outranked the classes a project's documentation actually tells you to subclass.
  Measured on the commander benchmark target: recall@10 0/2 → 2/2, candidates
  25 → 11, with no other target affected.

### Note

- A modscan upgrade that adds catalogue entries can make the attack-surface gate
  report sinks that were always in the code — new to the detector, not to the
  codebase. Pin the Action's `modscan-version` for a baseline that only moves when
  you choose.

## [0.1.6] - 2026-07-23

The security lens grows a memory: it can now compare two snapshots and gate a
pull request on the execution sinks it introduces.

### Added

- **Attack-surface gate GitHub Action** (`Rinkia/modscan/attack-surface`). On a
  pull request it audits the PR and the base branch, diffs them, sticky-comments
  the result, and fails the check when the PR **introduces** new execution sinks.
  It gates the *delta*, never the standing surface — sinks already on base never
  fail it. `fail-on` defaults to **high** (`eval`/`exec`/`pickle.loads`/
  `yaml.load`/`os.system`): measured across real packages, the medium tier is
  dominated by routine `__reduce__`, dynamic-import and subprocess code, so gating
  on it is noisy for exactly the plugin hosts MODScan serves. No LLM, no API key,
  no committed snapshot. MODScan runs it on itself
  (`.github/workflows/attack-surface-gate.yml`).
- **`modscan-audit --fail-on {high,medium,low,none}`** — with `--diff`, exit 1
  when a sink at least that severe is introduced. Defaults to `none`: the CLI
  stays a report, and the policy lives in the gate.
- **`modscan-audit --diff BASE PR`** — compare two `--json` attack-surface
  snapshots and report the execution sinks the second one *introduces*. Sinks are
  identified by `(id, module, call)` and compared as a counted multiset, so moved
  code never registers as a change while a third `eval` added to a module that
  already had two still shows up. On its own it only reports; `--fail-on` turns it
  into a gate. The report carries its own sticky-comment marker, distinct from the
  breaking-change gate's, so a repo running both gets two independent comments.

## [0.1.5] - 2026-07-22

A second lens over the same static analysis: `modscan-audit` maps a codebase's
attack surface, and moddability reasons now carry stable IDs.

### Added

- **Security Lens (`modscan-audit`)** — a sibling command that maps a Python
  codebase's *attack surface*: where untrusted code or data can enter and execute
  (`eval`/`exec`, `pickle`/`marshal`/`yaml` deserialization, `__reduce__`,
  `os.system`/`subprocess`, and dynamic loaders). Findings use a Bandit-style
  catalog — stable `MS-SEC-*` ids rated by **severity × confidence**, separate
  from the moddability score — and rank most-dangerous-first. Offline and free (no
  LLM). Markdown or `--json`. Every report states prominently that it is **not** a
  vulnerability scan: no taint analysis, CVE matching, or secret detection, and an
  empty report is not a clean bill of health. Enumeration only — it locates sinks,
  it does not trace reachability.
- **Stable IDs on moddability signals** — each ranking reason now carries a stable
  `MS-MOD-*` id (presentation only; the score and ranking are unchanged).

## [0.1.4] - 2026-07-22

Downstream polish: scaffolds you can verify, docs that point at them, and a gate
comment that stops repeating itself.

### Changed

- **The breaking-change gate now posts a sticky PR comment.** It finds its own
  prior comment by a hidden marker and updates it in place, instead of stacking a
  fresh comment on every re-push. `render_diff_markdown` emits the marker
  (`DIFF_COMMENT_MARKER`) as its first line.

### Added

- **Docs link to scaffolding, and explain the status badges.** The generated
  plugin guide now prints the exact `modscan scaffold "<id>"` command for each
  extension point, so a reader goes from documentation to a ready-to-edit
  skeleton in one copy. The index carries an example-status legend explaining what
  each badge (`verified`, `executed`, `compiled`, `generated`, `unverified`)
  means. Deterministic — no LLM, no new prompts.
- **`modscan scaffold --verify`** — after writing plugin skeletons, imports the
  target and confirms each base actually subclasses/instantiates (or, for
  hook/registration points, imports and is callable), reusing the layer-5
  validator. Offline and free (no LLM, no API key); exits non-zero if any point
  fails, so it doubles as a CI check that a scaffolded contract still holds. It is
  opt-in because verification executes the target's module code — the default
  scaffold path stays purely deterministic and never imports the target.
- **A live example of the breaking-change gate**, linked from the README:
  [`modscan-gate-example`](https://github.com/Rinkia/modscan-gate-example) shows a
  safe PR passing and a breaking PR failing, with the gate's comments.

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

[Unreleased]: https://github.com/Rinkia/modscan/compare/v0.1.7...HEAD
[0.1.7]: https://github.com/Rinkia/modscan/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/Rinkia/modscan/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/Rinkia/modscan/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/Rinkia/modscan/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/Rinkia/modscan/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Rinkia/modscan/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Rinkia/modscan/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Rinkia/modscan/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/Rinkia/modscan/releases/tag/v0.0.1
