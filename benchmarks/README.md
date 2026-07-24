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
| commander 14.0.2 (baseline) | 25 | 2 | 11, 15 | **0/2** |
| commander 14.0.2 (current) | 11 | 2 | 3, 7 | **2/2** |

At the baseline both labelled seams landed just outside the top ten. What
occupied the ranking above them was the finding — since resolved, below:

**TypeScript `interface` declarations are scored as abstract classes.** The
front-end treats an interface as "a pure contract to implement", which is
reasonable in the abstract and wrong in practice: commander's top eight are
`ParseOptions`, `HelpContext`, `OutputConfiguration`, `AddHelpTextContext` and
friends — option bags from `typings/index.d.ts` — each scoring 0.70 with
*"meant to be subclassed"*, while the two classes the documentation actually
tells you to subclass sit at 0.10.

This was recorded rather than fixed there, for the same reason the Python signals
were: changing it is a **ranking change**, and a ranking change is judged by the
benchmark, in its own pull request, against this baseline. Fixing it in the
change that introduced the labels would be exactly the circularity the gate on
this directory exists to prevent.

### Resolved: `.d.ts` declaration files are not scanned

*"The interfaces flooding the top come from a type-declaration file, not from
code."* **Measured, adopted.**

Two candidate fixes were swept against the baseline before either was written:

| Variant | commander | Aggregate | Python targets |
|---|---|---|---|
| baseline | 0/2 (ranks 11, 15) | 9/22 | — |
| **B** — `interface` no longer implies abstract | 2/2 (ranks 3, 7) | **11/22** | unchanged |
| **C** — skip `*.d.ts` | 2/2 (ranks 3, 7) | **11/22** | unchanged |
| D — both | 2/2 (ranks 3, 7) | 11/22 | unchanged |

They are **identical**, which is itself the finding: both were describing the
same phenomenon, and combining them adds nothing.

**C is the one adopted**, because B is right about commander for the wrong
reason. A hand-written TypeScript interface genuinely *is* a contract to
implement — the front-end's own fixture has `RenderPlugin`, and B would demote
it. What was actually wrong was reading a **declaration file** at all: a `.d.ts`
declares types for code defined elsewhere, so commander's `Command` and `Help`
were each counted twice, and option bags that exist only as declarations became
candidates. Skipping declaration files also matches the rule these labels already
follow — a seam is recorded where it is *defined*.

Commander's candidate count drops 25 → 11 as the phantom copies disappear, its
median rank goes 13 → 5, and no Python target moves: click stays 4/4, pluggy 3/3.
**Aggregate 9/22 → 11/22.**

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

## The first Java target: a good score that means less than it looks

`junit-jupiter-api` 5.11.3 is the first Java target, fetched from Maven Central
as a version-pinned `-sources.jar`.

| Target | Candidates | Labels | Rank of each label | recall@10 | Median |
|---|---|---|---|---|---|
| junit-jupiter-api 5.11.3 | 61 | 7 | 5, 7, 8, 9, 11, 14, 18 | **4/7** | 9 |

**A prediction was made before this ran, and it was wrong.** The expectation was
a poor showing, because the re-export signal — the one signal measured to
generalize — has no Java analogue: there is no `__init__.py` and no barrel
module. Re-export *is* inert. But Java's extension points are interfaces
(abstract by construction) with role-suffix names (`*Callback`, `*Handler`,
`*Resolver`) extending a role-named base (`Extension`), so **abstract**,
**class-role** and **base-role** stack to a perfect 1.00 instead.

### Why 4/7 is not evidence the ranking works

**Eighteen candidates tie at exactly 1.00**, and inside that band the order is
strictly alphabetical:

```
 1 AfterAllCallback      5 BeforeEachCallback    9 InvocationInterceptor
 2 AfterEachCallback     6 BeforeTestExecutionCallback
 3 AfterTestExecutionCallback                   10 LifecycleMethodExecutionExceptionHandler
 4 BeforeAllCallback     7 ExecutionCondition   11 ParameterResolver
                         8 Extension            ...
```

The top-ten cutoff falls mid-alphabet. `ParameterResolver` (11),
`TestInstancePostProcessor` (14) and `TestWatcher` (18) are "missed" while
scoring **identically** to the four that made it. The 4/7 is decided by the
alphabet.

This is the SQLAlchemy flat band again, in a happier disguise. There, hundreds of
tied symbols buried five real seams. Here almost every tied symbol *is* a real
seam — precision at the top is close to perfect — but recall@10 cannot express
"eighteen equally valid answers, pick ten". That is as much a limit of the metric
as of the ranking, and it is why median rank is reported alongside.

The honest reading: Java's structure suits the existing signals unusually well,
and this target cannot distinguish a ranking that understands JUnit from one that
sorts JUnit's interfaces alphabetically. A target whose extension points are
*not* uniformly shaped would say more.

**Labels come from the package's own Javadoc at the pinned version**, not the
"current" web guide, so they stay checkable against exactly this source — each
quotes a sentence of the form *"defines the API for Extensions that wish to…"*.
The list is deliberately partial: the remaining lifecycle callbacks are
documented identically and are not all labelled.

### Running the Java targets

```bash
python benchmarks/java/fetch.py    # unpacks pinned -sources.jar from Maven Central
pip install modscan[java]
python benchmarks/score.py
```

A Java target declares `"language": "java"` and a `"maven"` coordinate. The
version lives in the unpacked directory name (`junit-jupiter-api-5.11.3/`), so a
mismatch is caught structurally and skipped with a notice — the same discipline
the pip and npm targets follow. Unpacked sources are gitignored.

## Function labels, and why the aggregate jumped

Until 2026-07-23 every label here was a **class**, which left the benchmark
unable to judge any signal that only scores functions. Five function labels were
added to fix that — registration points a user decorates their own function with,
each quoting the target's own docstring:

| Label | Rank | Docstring |
|---|---|---|
| `marshmallow.decorators:validates` | 1 | *"Register a validator method for field(s)."* |
| `marshmallow.decorators:post_dump` | 4 | *"Register a method to invoke after serializing an object."* |
| `marshmallow.decorators:pre_load` | 5 | *"Register a method to invoke before deserializing an object."* |
| `sqlalchemy.event.api:listens_for` | 361 | *"Decorate a function as a listener for the given target + identifier."* |
| `sqlalchemy.ext.compiler:compiles` | 1026 | *"Register a function as a compiler for a given ClauseElement type."* |

**The aggregate went 15/29 → 18/34. That is not a ranking improvement.** Three of
the five were already in their target's top ten, so adding them raised the number
by construction. Stating it plainly because the alternative — letting a jump like
that read as progress — is precisely the abuse the gate on this directory exists
to prevent.

What actually changed is what the benchmark can *see*:

- **A function-name signal is now measurable.** [#15](https://github.com/Rinkia/modscan/issues/15)
  was unjudgeable before this; it now has labels it could move.
- **Two honest hard targets appeared.** `listens_for` (361) and `compiles` (1026)
  are both far outside the top ten. `compiles` is especially pointed: the
  compiler-registration mechanism that the rejected whole-program-resolution work
  kept circling is now a *labelled, measurable* miss rather than an anecdote.

marshmallow moves 1/3 → 4/6, SQLAlchemy 1/5 → **1/7** — it gained two labels and
caught neither.

## Ties: how much of the score the alphabet owns

`detect_extension_points` breaks score ties on `(module, lineno)` — that is,
alphabetically. When a band of equally-scored candidates straddles rank 10, the
alphabet decides which labels count as hits. JUnit made this impossible to
ignore; measuring it across every target showed the problem is not JUnit's.

`score.py` now reports **tie bounds** alongside recall: the score if every tie
broke in the ranking's favour, and if every tie broke against it.

| Target | recall@10 | Tie bounds | Band at the cutoff |
|---|---|---|---|
| click 8.4.2 | 4/4 | 2..4 | 71 tied at 0.8, 6 slots |
| commander 14.0.2 | 2/2 | 0..2 | 11 tied at 0.1, 10 slots |
| junit-jupiter-api 5.11.3 | 4/7 | **0..7** | 18 tied at 1.00, 10 slots |
| marshmallow 4.3.0 | 4/6 | 4..5 | 4 tied at 0.7, 1 slot |
| pluggy 1.6.0 | 3/3 | **0..3** | 13 tied at 0.8, 10 slots |
| flask 3.1.2 | 3/6 | **3..3** | 1 at the cutoff — no ambiguity |
| pygments 2.20.0 | 0/5 | 0..0 | — |
| sqlalchemy 2.0.51 | 1/7 | 0..2 | 50 tied at 1.00, 10 slots |
| **Aggregate** | **21/40** | **9..26** | 17 of 40 labels are tie-decided |

Three consequences, none of them comfortable:

1. **Half the headline is not evidence.** 18/34 is one sample from an interval
   the ranking itself does not narrow. A change is real only if it moves the
   **lower bound**.
2. **The regression canaries were never canaries.** click's perfect 4/4 has a
   lower bound of 2/4 and pluggy's 3/3 a lower bound of **0/3** — no tie order is
   guaranteed by the ranking. Neither can falsify a change on its own. Flask was
   added for exactly this reason; see "Flask: the first target that can falsify
   a change" below.
3. **JUnit and SQLAlchemy are *not* the same problem**, despite looking alike.

### JUnit's band is not noise — the metric is wrong, not the ranking

All eighteen candidates tied at 1.00 live in `org.junit.jupiter.api.extension`
and implement `Extension`. Every one of them is a genuine extension point; the
seven labels are a *partial list of eighteen correct answers*. The ranking put
18/18 real seams in the top 18 and scored 4/7 for it.

No tiebreak signal is warranted here. There is nothing to discriminate.

SQLAlchemy's 50-wide band at 1.00 is the opposite: `Dialect`,
`CreateEnginePlugin` and `TypeDecorator` sit among `NoCursorDQLFetchStrategy`,
`ORMStatementAdapter` and internal fetch strategies. That band *does* need a
discriminator — it is a ranking failure, not a metric artefact.

### Rejected: the unclamped signal sum as a tiebreak

`score` is `min(sum, 1.0)`, so the clamp discards how *much* evidence a point
carried. Using the raw sum as a tiebreak reorders only within a band and can
never move a point across a boundary — a free lever, if it correlates.

**It is anti-correlated. Measured: 18/34 → 15/34.** Ranking by number of signals
instead gives the same 15/34. Inside JUnit's band the extra signal is an override
point, which the *derived* handler interfaces carry and the base `Extension` does
not; in SQLAlchemy it promotes internal machinery that happens to be abstract,
role-named *and* re-exported. More evidence is not better evidence — the
alphabet, chosen arbitrarily, beats both.

Recorded so nobody re-derives it. The clamp is not hiding a usable signal.

## Flask: the first target that can falsify a change

Measuring ties exposed a problem the aggregate had been hiding: **every target
here scores its labels inside a tied band**, so no single target could refute a
heuristic on its own. click's perfect 4/4 has a lower bound of 2/4; pluggy's 3/3
has a lower bound of 0/3. A benchmark of eight targets had, in effect, no
regression guard.

Flask 3.1.2 was added to fix that, and it was chosen **by measurement, not by
taste**. Its score distribution is graded rather than flat:

| Score | 1.00 | 0.90 | 0.85 | 0.80 | 0.60 | … |
|---|---|---|---|---|---|---|
| Candidates | 3 | 6 | **1** | 23 | 1 | |

Exactly one candidate holds the score at the rank-10 cutoff, so **flask's
recall@10 has no tie bounds at all** — worst case equals best case. It is the
only target of the eight whose number is pure evidence.

| Target | Candidates | Labels | Rank of each label | recall@10 | Median |
|---|---|---|---|---|---|
| flask 3.1.2 | 98 | 6 | 2, 3, 10, 38, 39, 98 | **3/6** | 24 |

Aggregate moves to **21/40, bounds 9..26** — the tie-decided share drops from
17/34 to 17/40 because all six new labels are tie-free.

### What it already says about the ranking

- **`MethodView` ranks 98 of 98 — dead last.** It is arguably Flask's most-used
  class-based extension point, and it scores the bare public baseline: it is not
  an ABC, its name ends in no role suffix the catalog knows, its base
  (`View`) likewise, and it is not re-exported under a name the root `__init__`
  advertises as a seam. Every existing signal is blind to it.
- **The implementation outranks the base it implements.**
  `DefaultJSONProvider` is 1st, `JSONProvider` — the class the docstring
  explicitly tells you to subclass — is 10th. The role-suffix and base-role
  signals both reward the concrete subclass more than the contract.
- **Dynamic imports occupy ranks 4–9**, pushing `Flask` and `Blueprint` below
  them. This is the pygments failure again, on a package where the loader sites
  are ordinary `import_string` helpers rather than a plugin registry.

### What it deliberately cannot say

Flask's *largest* extension surface is the decorator methods on the app and
blueprint objects — `before_request`, `errorhandler`, `template_filter`,
`context_processor`. None of them can be labelled, because the parser only takes
**top-level defs** as seams and these are methods. That blind spot is a reason to
add this target, not a reason to avoid it: it is now visible in the labels file
instead of being an unwritten limitation.

Two exclusions, both by the labelling rule:

- **`Flask` itself.** Its shipped docstring describes what the object does and
  never invites subclassing. The web guide is more encouraging, but labels come
  from the docs shipped *at the pinned version*.
- **`Blueprint`.** You construct one and register the instance, which the rule
  counts as calling an API rather than implementing one.

## What this benchmark still cannot measure well

Function labels now exist, but only five of thirty-four — and three of those
already sit near the top of their target. So a signal that scores functions
(`_HOOK_NAME_PARTS`, the registration-decorator patterns, `_W_NAME_HOOK`) is
*judgeable* now, where before it was not, but the evidence is thin: the two
genuinely hard function labels are `listens_for` (361) and `compiles` (1026), and
a signal would have to move one of those a long way to register.

The sweep below was run **before** these labels existed, when the answer could
only ever be "no change or worse". It is kept because the interaction effect it
found is still real — and worth re-running now that there is something to gain.

Sweeping the fourteen hook-name fragments proposed in
[#15](https://github.com/Rinkia/modscan/issues/15), against the 15/29 baseline:

| | aggregate | click |
|---|---|---|
| baseline | 15/29 | 4/4 |
| each fragment **alone** | 15/29 | 4/4 |
| **all fourteen together** | **14/29** | **3/4** |

Individually neutral, collectively harmful — enough non-seam functions get
promoted to push a real click label out of the top ten. Note that this only
became visible because the candidates were measured *together* as well as
separately.

**Before changing a signal, ask which labels it could possibly move.** If the
answer is none, the prerequisite is new labels of that shape — a labels-only pull
request, justified from the targets' documentation like every other label — not a
cleverer heuristic.

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

**Recall@10 is reported with tie bounds, and the lower bound is the honest
reading.** See "Ties: how much of the score the alphabet owns" — 17 of 34 labels
currently sit in a band straddling rank 10, so the headline is one sample from
6..23. A heuristic change that moves only the printed figure moved the alphabet.

**Per-target recall@10 is a regression guard, not a target to maximise.** click
is the canary — it already works, and it must not fall. With a lower bound of
2/4 (pluggy's is 0/3) that guard is weaker than it reads: a canary whose perfect
score no tie order guarantees cannot falsify a change by itself.

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
pip install pluggy==1.6.0 click==8.4.2 sqlalchemy==2.0.51 \
            pygments==2.20.0 marshmallow==4.3.0 flask==3.1.2
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
