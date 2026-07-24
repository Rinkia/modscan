# Usage cross-check — what real plugins actually extend

A lens cannot validate itself. The security lens is measured against Bandit and
eslint-plugin-security, authorities this project does not control. Moddability
had no equivalent: its ground truth came from **one** source — the host's own
documentation — and MODScan's ranking is the thing being judged, so neither can
validate the other.

This is the missing third source. For each host it parses a pinned set of real
downstream plugins and counts **how many of them subclass each host symbol**.
Nobody involved in this project decides what a plugin author chose to subclass.

```bash
python usage-crosscheck/crosscheck_usage.py --install   # prints the pip commands
python usage-crosscheck/crosscheck_usage.py
```

Offline and free. The downstream packages are **parsed, never imported or
executed**, so `--no-deps --target` is enough and a package that would not
install into this interpreter can still be measured. They are gitignored; the
pins live in [`downstream.json`](downstream.json), which is the lockfile of this
check.

## Result

| Host | Downstream | Top subclassed | MODScan's rank for it | Labelled? |
|---|---|---|---|---|
| marshmallow 4.3.0 | 10 | `Field` (7 plugins) | **26** | yes |
| click 8.4.2 | 11 | `Group`, `Command` (5 each) | 9, 8 | yes |
| flask 3.1.2 | 12 | nothing above 1 | — | — |

Three findings, in descending order of how much they cost to ignore.

### 1. The authority agrees with the labels, and disagrees with the ranking

On both subclass-style hosts the most-subclassed symbols **are** the documented
labels: `Field` and `Schema` for marshmallow, `Group` and `Command` for click.
Two independent sources — maintainer documentation and plugin author behaviour —
picked the same symbols. That is the first evidence the labelling rule captures
something real rather than something plausible.

The ranking is where it breaks. **`Field` is the single most-subclassed symbol in
the marshmallow ecosystem, and MODScan ranks it 26th.** That was already known as
a labelled miss; what is new is that it is not a marginal one. Seven of ten
plugins subclass it.

### 2. Import count is not a substitute, and it is worth saying why

Both counts are printed so this stays checkable. Ranked by *imports*,
marshmallow's top symbol is `ValidationError` — an exception you catch — and
click's is `echo`. Those are exactly the things you *merely call*, which the
labelling rule excludes by name. **An import-count authority would contradict the
rule the labels are built on.** Subclass count does not.

### 3. The control host says what the method cannot see

Flask is in here to fail. It is extended by **registering** against the app
object — `before_request`, `errorhandler`, `template_filter` — not by
subclassing, and the check duly finds nothing above a single occurrence. That
reproduces, from a completely independent direction, the blind spot already
recorded against the flask target in `benchmarks/README.md`: those decorators are
methods on the app object, and the parser only takes top-level defs as seams.

So the scope of this authority is explicit: **it speaks about class seams, in
ecosystems that extend by subclassing.** It says nothing about registration-style
hosts, and marshmallow's three function labels (`validates`, `pre_load`,
`post_dump`) are correctly reported as never subclassed — decorators are called,
not inherited.

## What this is *not*

**Not the rejected "internal subclass count" hypothesis.** That one counted
subclasses *inside the package being scanned* and failed because a package's own
machinery subclasses its own bases constantly — SQLAlchemy's `Dialect` was
re-buried under ~500 co-boosted classes. This counts subclasses in **downstream**
code, which the earlier work explicitly named as the place the evidence lives and
a single-package scan can never reach.

**Not a source of labels.** Symbols that are heavily subclassed but unlabelled —
marshmallow's `List` and `Nested`, click's `Option` and `CommandCollection` — are
printed as *candidates for a documentation check*. A label still needs a quoted
sentence from the host's docs. Adding labels because usage is high would make the
benchmark circular in a new direction, and "add targets, never labels" exists for
exactly this temptation.

**Not a signal, yet.** Turning downstream subclass count into a detector weight
would require the scan to see downstream code, which it does not and will not.
Its value here is as a *judge*: a ranking change can now be asked whether it moves
the symbols real plugins actually extend.

## Choosing the sample

The downstream lists are the most-downloaded plugins for each host, pinned by
version. They were fixed **before** the first run, not adjusted afterwards — a
sample curated toward an answer would measure nothing. Adding a host means adding
an entry to `downstream.json`; extending a list is fine, replacing entries that
gave an inconvenient result is not.
