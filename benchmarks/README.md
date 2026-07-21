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

### At risk: penalising private module paths

*"Seams in `_private` modules are internal, so demote them."* Superficially
sensible, and **pluggy alone refutes it**: `PluginManager` is defined in
`pluggy._manager` and `HookimplMarker` in `pluggy._hooks`. Both are
first-class public API, re-exported from `pluggy/__init__.py`.

A path-based penalty would demote the single most important seam in the package.
If this heuristic is ever attempted, it must be measured against pluggy first.

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
