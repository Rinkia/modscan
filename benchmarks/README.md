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
   `defining.module:Symbol`, matching what the parser produces.
4. Write a justification naming the documentation that presents it as
   extensible. "It looks important" is not a justification.
5. Run `python tests/test_benchmark_labels.py`.

## Keeping labels honest

Labels cannot be made immutable — anyone with write access can edit the file,
and a checksum stored beside them offers no protection, since whoever edits the
labels can recompute it. That would be theatre.

What *is* enforced is that the specific abuse stays visible: a CI check fails
when a single pull request modifies both the ground truth and the ranking code.
Labels can still change — but not quietly, in the same commit as the heuristic
they would flatter. `CODEOWNERS` additionally requires review on this directory.
