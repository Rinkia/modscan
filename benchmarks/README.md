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
| click 8.4.2 | 152 | 4 | **1, 2**, 38, 39 | 2/4 | 20.5 |
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

## Keeping labels honest

Labels cannot be made immutable — anyone with write access can edit the file,
and a checksum stored beside them offers no protection, since whoever edits the
labels can recompute it. That would be theatre.

What *is* enforced is that the specific abuse stays visible: a CI check fails
when a single pull request modifies both the ground truth and the ranking code.
Labels can still change — but not quietly, in the same commit as the heuristic
they would flatter. `CODEOWNERS` additionally requires review on this directory.
