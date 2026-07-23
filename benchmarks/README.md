# Ranking benchmark — ground truth

MODScan's value rests on *which* extension points reach the top of its ranking.
Everything downstream — the docs, the scaffolds, the breaking-change diff — is a
multiplier on that ordering. This directory holds the labelled truth those
rankings are measured against.

Without it, every heuristic change is a coin flip. With it, a contributor can
answer "did this help?" before opening a pull request.

## The labelling rule

> A symbol is a **real extension point** when the package's own documentation
> presents it as something a user **implements, subclasses, or registers
> against** — not merely calls.

The rule points at one external authority: the maintainers of the target
package. Every label cites the documentation it rests on, so a label can be
challenged with evidence rather than opinion.

### Why the rule is *not* "is it publicly exported?"

Because that is the signal the benchmark exists to judge.

A strong candidate heuristic is "score symbols re-exported from the package's
top-level entry point". If truth were *defined* by public export, that signal
would score perfect recall by construction — flattering numbers that measure
nothing. Truth has to come from somewhere the heuristic cannot reach.

### Explicit exclusions

Excluded even when abstract or public-looking:

- **Test infrastructure** — `TablesTest`, `TestBase`. Widely subclassed, but not
  by the people MODScan serves.
- **Internal machinery** — classes that exist to factor a package's own code.
- **Undocumented seams.** If maintainers never told users to extend it, it is
  not a labelled extension point. This is a deliberate consequence of the rule:
  MODScan serves people extending a project *from its documentation*.

Partial lists are acceptable — SQLAlchemy has more documented seams than are
labelled here. Recall against a partial list is still a valid regression signal.
What matters is that labels are never *silently* added to make a number move.

## Signals judged

### Accepted: re-export from the package's public entry point

*"A symbol the maintainer re-exports from the top-level `__init__` is more likely
a real seam than one buried in a submodule."* **Measured, adopted.**

The detector adds a weight (`_W_REEXPORT`) when a seam's name is re-exported from
the scanned package's root `__init__` — via `__all__` when present, else the
names it imports.

| Target | recall@10 before | recall@10 after | median before | median after |
|---|---|---|---|---|
| pluggy 1.6.0 | 2/3 | **3/3** | 6 | 4 |
| click 8.4.2 | 2/4 | **4/4** | 20 | 6 |
| SQLAlchemy 2.0.51 | 0/5 | 0/5 | 1369 | **290** |
| **Aggregate** | **4/12** | **7/12** | | |

It clears the acceptance bar — recall@10 improves on two targets and regresses
none. Reproduce with `python benchmarks/score.py`.

Two things the measurement made explicit:

- **It is necessary but not sufficient for SQLAlchemy.** SQLAlchemy re-exports
  237 names from its root, so all five labels get the same lift as hundreds of
  other symbols and stay tied outside the top 10 — recall@10 cannot move there at
  any weight. The median dropping 1369 → 290 is the real evidence it helps;
  breaking that tie needs a *second* discriminator, which is the next signal to
  find.
- **The weight is not a knife-edge, but it has a ceiling.** Anything in
  0.5–0.7 clears the bar without regressing a target; pushing to 0.9 starts
  demoting real click seams below re-exported non-seams (`confirmation_option`,
  `version_option`). 0.7 is the adopted value — above the abstract-class weight,
  because public-API membership is a more deliberate signal of intent than
  abstractness, but below the dynamic-import weight, which is still the strongest
  single seam.

### Accepted (partial): a class with an override point

*"A class with a method that raises `NotImplementedError` is a
subclass-and-implement base."* **Measured, adopted, and explicitly partial.**

Milestone 3 lifted SQLAlchemy's five labels into a flat band of ~316 symbols all
scoring 0.80 — re-export moved them up but could not separate them. This signal
reads *inside* the methods: `_W_OVERRIDE_POINT` is added when a class defines a
method whose body raises `NotImplementedError`. It is selective (94 of the public
classes, 22 of the re-exported ones) and non-circular — it reads the code's own
structure, not its docs or its export list.

| Target | recall@10 before | after | median before | after |
|---|---|---|---|---|
| pluggy 1.6.0 | 3/3 | 3/3 | 4 | 4 |
| click 8.4.2 | 4/4 | 4/4 | 6 | 6 |
| SQLAlchemy 2.0.51 | 0/5 | **1/5** | 290 | 270 |
| **Aggregate** | **7/12** | **8/12** | | |

It clears the bar — SQLAlchemy improves, nothing regresses — but the gain is
**one label, not the tie broken**. `Dialect` (129 → 8) and `TypeDecorator`
(253 → 47) both reach the maximum score; only `Dialect` reaches the top ten,
because the maximum-score band is itself ~46 wide. The remaining three labels are
untouched **by design**: `FunctionElement`, `ExecutableDDLElement` and
`UserDefinedType` extend by subclass **and compiler registration**, not by method
override, so they raise no `NotImplementedError`. Surfacing them needs a *third*
discriminator — a registered compiler, or public API exported from a documented
submodule (`UserDefinedType` is not re-exported from the root at all). That is
the next signal to find.

## Does the ranking generalize? (measured on two more packages)

The signals above were judged on pluggy, click and SQLAlchemy — the three they
were shaped near. To test whether they generalize or were overfit, two more
targets with *different* extension mechanisms were labelled by the same
documentation rule and measured. The signals did **not** hold up.

| Target | Candidates | Labels | Rank of each label | recall@10 | Median |
|---|---|---|---|---|---|
| pygments 2.20.0 | 768 | 5 | 21, 23, 46, 75, 694 | **0/5** | 46 |
| marshmallow 4.3.0 | 87 | 3 | 9, 13, 28 | **1/3** | 13 |

Aggregate across all five targets: **9/20**.

Two concrete generalization gaps, both recorded rather than tuned away:

- **pygments — plugin-loader machinery floods the top.** Its entry-point loading
  sites (`pygments.plugin:entry_points`, the `__import__` shims in
  `lexers`/`formatters`) score 0.9 as dynamic imports and occupy the whole top of
  the ranking, burying the real bases. `Filter` (21) and `Lexer` (23) get the
  override-point lift but only to the low twenties; `Style` (694) is caught by
  nothing. The dynamic-import weight, tuned where loaders were rare, is
  miscalibrated for a package built around a plugin registry.
- **marshmallow — override-point is convention-specific.** The signal assumes a
  base signals "override me" by raising `NotImplementedError`. marshmallow 4.x
  defines `Field._serialize`/`_deserialize` as **noops**, so the signal never
  fires and `Field` stays at 28. `Schema` (9) is caught by re-export; `Validator`
  (13) by neither. A base extended by overriding a noop is invisible to a signal
  that looks for a raise.

**Verdict**: the re-export signal generalizes (it caught `Schema` and helps
everywhere); the override-point and dynamic-import weights do **not** — they were
calibrated to the first three packages' conventions. This is the overfitting the
PRD's top risk named, now measured instead of feared. No weight was changed to
hide it: fixing these is a future, separately-measured signal (a plugin-registry
discount, or a broader "documented override" detector), not a quiet re-tune.

### Correctness fix: `__import__` is reflection, not a plugin loader

The pygments measurement above exposed a categorisation bug, now fixed. The
detector scored every dynamic-import site at 0.9 as a `plugin_loader`, but the
builtin `__import__` is a general-purpose reflection / lazy-import primitive —
pygments uses it to lazy-load its own lexer modules, and five such shims flooded
the top of its ranking. It is now scored as weak reflection evidence (still
detected, just no longer ranked as a top extension point); `entry_points`,
`import_string` and the other genuine plugin-discovery loaders are unchanged.

This is **recall-neutral by construction** — no labelled extension point is a
dynamic-import seam, so recall@10 stayed 9/20 across all five targets, with no
regression. The gain is in the *output*: no package's ranking now leads with
`__import__` machinery. (Medians drifted up slightly everywhere as the shims
left the ordering.)

**Deferred, recorded honestly**: after this fix pygments' top three are still
`entry_points` sites. Those are the framework's own plugin-*discovery* code, not
a symbol a user implements — but `entry_points` genuinely *is* a plugin
mechanism, so whether such loader sites should rank as "implement-this" extension
points at all is a larger question, left for a separate, measured change.

## Hypotheses this benchmark has already killed

Recorded so nobody spends a weekend re-deriving them.

### Rejected: ranking by internal subclass count

*"A genuinely extensible seam already has subclasses inside the codebase."*
Wrong in both directions, measured:

- SQLAlchemy — promotes `TablesTest` (61 internal subclasses) and `TestBase`
  (27). Both are test infrastructure.
- click — `ParamType` has **zero** internal subclasses and is the canonical
  extension point. It is meant to be subclassed by *users*, not internally.

The signal rewards internal hierarchies and punishes user-facing API, which is
backwards for this purpose.

### Rejected: a "third discriminator" for SQLAlchemy's last three labels

After the override-point signal, SQLAlchemy sits at 1/5: `Dialect` reaches the
top ten, and `FunctionElement`, `ExecutableDDLElement`, `UserDefinedType` stay
buried. A spike measured three cheap, generic candidates for lifting them —
**none was adopted**:

- **Docstring says "subclass / implement / override / custom / extend".** Catches
  `UserDefinedType` (the rank-1640 outlier) but fires on 130 of SQLAlchemy's
  1705 classes. Added as a weight it **regresses** the benchmark 8/12 → 6/12:
  boosting all 130 buries the labels among them and even overtakes a click label.
- **Extend-docstring AND ≥2 bases** (a selective combination). Neutral — 8/12 at
  every weight, no target moved. No reason to add a signal that changes nothing.
- **≥2 bases alone.** Catches none of the labels.

The two truly-buried seams (`FunctionElement`, `ExecutableDDLElement`) extend by
subclass **and `@compiles` compiler registration**, not by any property visible
in a single class's own structure. Separating them from the hundreds of other
documented multi-base classes needs whole-program subclass resolution the parser
does not have — out of scope for a heuristic. `UserDefinedType` could be lifted
off the floor by broadening re-export to module-level exports (it lives in
`sqlalchemy/types.py`, a module, not a package `__init__`), but that alone does
not reach the top ten.

So SQLAlchemy stays at 1/5 and the aggregate at 8/12. This is recorded, not
hidden: the honest ceiling of structural heuristics on a package whose real
extension contract lives in its compiler registry and its prose.

The whole-program subclass/`@compiles` resolution floated here as the possible
escape was later built and measured — see *"Rejected: whole-program subclass
resolution"* below. It does not surface these seams: their `@compiles` edges live
in downstream user code the scan never sees, and the buried labels have zero
in-package subclasses.

### Rejected: whole-program subclass resolution (and `@compiles`)

*"The buried compiler-registration seams (`FunctionElement`, `ExecutableDDLElement`,
`UserDefinedType`) can be lifted by resolving the whole-program subclass graph and
the `@compiles` registration edges the parser doesn't currently see."* This was
the last lever this file named — a research spike, not a clean task. **Measured,
rejected.**

Two structural findings end it, both from a single-package scan of the pinned
targets:

- **`@compiles` registration is invisible to the scan.** SQLAlchemy's own source
  uses `@compiles(...)` to register compilers against *concrete* elements
  (`greatest`, `utcnow`, `CreateColumn`, `InsertFromSelect`) and its docstring
  examples (`MyColumn`, `SLBigInteger`) — **never** against the public bases.
  Users register against `FunctionElement` / `ExecutableDDLElement` in *their own*
  code, which MODScan never sees when scanning the library. Fourteen classes are
  `@compiles` targets in-package; **none** is a labelled seam. The compiler-
  registration contract the docs describe lives downstream of the scan boundary.
- **The two truly-buried labels have zero in-package subclasses.**
  `FunctionElement` (rank 266) and `UserDefinedType` (rank 1631) are subclassed
  **zero** times inside SQLAlchemy and `@compiles`-registered zero times. No
  subclass-count threshold can move a class with no subclasses.

Wired as a weight anyway and swept, the whole-program subclass-count signal
**regresses a target**, failing the standing accept bar (recall@10 up **and** no
target regresses):

| subclass weight | aggregate | sqlalchemy | pygments | marshmallow | click | pluggy |
|---|---|---|---|---|---|---|
| 0.0 (baseline) | 9/20 | 1/5 | 0/5 | 1/3 | 4/4 | 3/3 |
| 0.5 | 11/20 | **0/5** | 2/5 | 2/3 | 4/4 | 3/3 |
| 0.7 | 11/20 | **0/5** | 2/5 | 2/3 | 4/4 | 3/3 |

Aggregate rises 9→11, but **SQLAlchemy regresses 1/5→0/5**: `Dialect` (rank 8)
drops out of the top ten because ~500 of 1723 classes receive the same boost and
re-bury it. This is the "ranking by internal subclass count" hypothesis —
already rejected above as *wrong in both directions* — reconfirmed with a fresh
number: the flood promotes real seams and non-seams alike, and the one SQLAlchemy
label that worked is the casualty. The pygments/marshmallow gains are real but
cannot be bought at the cost of a per-target regression, and the signal never
touches the buried SQLAlchemy labels it was meant to lift.

**Verdict**: the buried seams' extension contract is genuinely invisible to a
static single-package scan — it lives in downstream user code and in prose. This
is the honest ceiling of structural heuristics on this benchmark, now measured
rather than suspected. The lever is closed; the benchmark stays at **9/20**. No
detector weight was changed.

#### Follow-up rejected: widen the scan to the package's own `test/` + `examples/`

The natural rescue is *"the `@compiles` and subclass evidence lives in the
package's own test suite and doc examples — so scan those too and apply the
evidence to the library symbols."* Measured on SQLAlchemy's 2.0.51 source
tarball (the installed wheel ships no tests). **Rejected — the evidence and the
noise are the same directory.**

Subclass demonstrations of the buried bases do appear once `test/` is scanned —
`UserDefinedType` goes from 0 in-library subclasses to 30, `FunctionElement` to
12. But `test/` is also SQLAlchemy's largest subclass farm, and its base classes
are shipped *inside the library* under `sqlalchemy/testing/`:

| Evidence source | UserDefinedType | FunctionElement | TypeDecorator | Top of the subclass ranking |
|---|---|---|---|---|
| lib + `test/` + examples + doc | 30 | 12 | 113 | `TestBase` 604, `MappedTest` 365, `TablesTest` 187, `AssertsCompiledSQL` 387 — ten test-infra / declarative-boilerplate classes rank above the first real label |
| lib + examples + doc (no `test/`) | **0** | **0** | 6 | clean, but the label evidence has collapsed to nothing |

The two rows bracket it. With `test/` the buried labels finally get real counts
but sit behind ~10–20 test-infrastructure bases — the exact classes the
labelling rule explicitly excludes (*"`TablesTest`, `TestBase` — widely
subclassed, but not by the people MODScan serves"*) — so they still miss the top
ten and the output is flooded with the test framework. Without `test/` the flood
is gone but so is the signal: the demonstrations lived almost entirely in the
tests. Filtering candidates defined under `*/testing/*` removes the flood
*classes* but not the problem — the evidence that would lift the real labels is
in the same files. There is no window where the buried-label evidence is strong
and the test-infra noise is absent, because extension is demonstrated *by
subclassing in the tests*, which is also what the fixtures do en masse.

So widening the scan does not help. Three measured negatives now share one root
cause: these seams' extensibility is expressed by subclassing-in-tests and
registration-in-user-code, both statistically indistinguishable from noise (test
fixtures, concrete elements) to any count-based signal. Ranking is at its honest
ceiling on this benchmark; the way forward is **more targets**, not another
weight on these five.

### At risk: penalising private module paths

*"Seams in `_private` modules are internal, so demote them."* Superficially
sensible, and **pluggy alone refutes it**: `PluginManager` is defined in
`pluggy._manager` and `HookimplMarker` in `pluggy._hooks`. Both are
first-class public API, re-exported from `pluggy/__init__.py`.

A path-based penalty would demote the single most important seam in the package.
If this heuristic is ever attempted, it must be measured against pluggy first.

## The first JavaScript target: does the ranking cross languages?

The five targets above are Python. `commander` 14.0.2 was added to ask whether
the ranking means anything on a second language. **It does not yet**, and the
figure says so plainly:

| Target | Candidates | Labels | Rank of each label | recall@10 |
|---|---|---|---|---|
| commander 14.0.2 | 25 | 2 | 11, 15 | **0/2** |

Both labelled seams land just outside the top ten. What occupies the ranking
above them is the finding:

**TypeScript `interface` declarations are scored as abstract classes.** The
front-end treats an interface as "a pure contract to implement", which is
reasonable in the abstract and wrong in practice: commander's top eight are
`ParseOptions`, `HelpContext`, `OutputConfiguration`, `AddHelpTextContext` and
friends — option bags from `typings/index.d.ts` — each scoring 0.70 with
*"meant to be subclassed"*, while the two classes the documentation actually
tells you to subclass sit at 0.10.

This is recorded rather than fixed here, for the same reason the Python signals
were: changing it is a **ranking change**, and a ranking change is judged by the
benchmark, in its own pull request, against this baseline. Fixing it in the
change that introduced the labels would be exactly the circularity the gate on
this directory exists to prevent.

A second, smaller trap the target exposed: commander ships hand-written type
declarations beside the implementation, so `Command` and `Help` each appear
twice — once in `lib/*.js`, once in `typings/index.d.ts`. Labels point at the
implementation, where the `class` statement is, consistent with rule 3 below.

### Running the JS/TS targets

```bash
cd benchmarks/js && npm install     # pins the targets; node_modules is gitignored
pip install modscan[typescript]     # tree-sitter front-end
python benchmarks/score.py
```

A JS/TS target is declared with `"language": "typescript"` in
`ground_truth.json`; its version is read from the package's own `package.json`,
and it is skipped with a notice if the installed version is not the pinned one.
Ids are target-qualified path form — `commander/lib/help:Help`.

## Adding a target

1. Pick a package with real documentation — the rule depends on it.
2. Record the exact installed version. Labels are only valid for that version;
   the benchmark skips rather than reporting a misleading score against another.
3. For each seam, find where it is **defined** (the module containing the
   `class` statement), not where it is re-exported. Label ids are
   `fully.qualified.module:Symbol` — `pluggy._manager:PluginManager`, not
   `_manager:PluginManager`.

   The parser does **not** emit this form. It reports module paths relative to
   the directory it was pointed at, so scanning an installed `pluggy` yields
   `_manager`, and scanning `sqlalchemy` yields `engine.cursor`. The scorer
   prefixes the target name before comparing. Labels use the qualified form
   because it is the one a human can verify against the documentation.
4. Write a justification naming the documentation that presents it as
   extensible. "It looks important" is not a justification.
5. Run `python tests/test_benchmark_labels.py`.

## Baseline

Measured 2026-07-20 at the pinned versions, before any ranking change.

| Target | Candidates | Labels | Rank of each label | recall@10 | Median rank |
|---|---|---|---|---|---|
| pluggy 1.6.0 | 20 | 3 | 5, 6, 14 | 2/3 | 6 |
| click 8.4.2 | 152 | 4 | **1, 2**, 38, 39 | 2/4 | 20 |
| SQLAlchemy 2.0.51 | 2092 | 5 | 620, 1287, 1369, 1628, 1631 | 0/5 | 1369 |

Aggregate recall@10: **4/12**.

Three things this measurement settled:

- **pluggy's public API is buried, not missing.** `PluginManager`,
  `HookimplMarker` and `HookspecMarker` are all detected. The defect is
  ordering, not discovery — a smaller problem than it looked.
- **click is half right.** `Parameter` and `ParamType` rank 1 and 2. `Command`
  and `Group` are equally documented and sit at 38 and 39.
- **Score ties dominate.** Ten of the twelve labels score exactly `0.1`, the
  signal-sum floor that hundreds of symbols share; only click's `Parameter` and
  `ParamType` reach 0.7. Ranks inside that floor are decided by traversal order,
  not evidence, so SQLAlchemy's ordering today is *arbitrary* rather than wrong.

## What gets reported

**k = 10.**

**Headline: recall@10 aggregated over all twelve labels.** Thirteen levels
rather than the four a single small target gives, and it does not reward
skewing effort at the easiest target.

**Per-target recall@10 is a regression guard, not a target to maximise.** click
is the canary — it already works, and it must not fall.

**Median rank of the labelled seams is reported alongside.** It is continuous
and moves before recall does. This matters because recall@10 is *blind* to real
progress on SQLAlchemy for a long time: labels sit at ranks 620–1631, so a
change lifting `TypeDecorator` to 150 is a large improvement that recall@10
still reports as `0/5`. Several good iterations reading as "no progress" is how
a metric dies of disuse.

**precision@10 is reported but is not the figure to optimise.** With partial
label lists it has a structural ceiling — SQLAlchemy has five labels, so p@10
cannot exceed 0.5 even for a perfect ranker. A metric that cannot reach 1 by
construction invites adding labels instead of improving the heuristic.

If resolution ever genuinely binds, add **targets** — never labels.

## Running it

```bash
pip install pluggy==1.6.0 click==8.4.2 sqlalchemy==2.0.51
python benchmarks/score.py            # all targets
python benchmarks/score.py --target pluggy
```

The versions must be the pinned ones — a target installed at any other version
is skipped with a notice rather than scored, because a score against different
code would be misleading. The command is offline and free: it runs the detector,
never the LLM.

The table it prints is the one above. That is the acceptance test for the
scorer: it reproduces figures that were committed before it existed. If it ever
disagrees, one of the two is wrong — investigate, do not edit the table to
match. (It has already earned its keep once: the median it computes corrected a
by-hand arithmetic slip in this file.)

`tests/test_benchmark_scoring.py` covers the metric maths offline, so CI guards
the logic without needing the target packages installed.

## Keeping labels honest

Labels cannot be made immutable — anyone with write access can edit the file,
and a checksum stored beside them offers no protection, since whoever edits the
labels can recompute it. That would be theatre.

What *is* enforced is that the specific abuse stays visible: a CI check fails
when a single pull request modifies both the ground truth and the ranking code.
Labels can still change — but not quietly, in the same commit as the heuristic
they would flatter. `CODEOWNERS` additionally requires review on this directory.
