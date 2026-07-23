# Security-lens cross-check — validating against Bandit

The security lens cannot validate itself. Judging `modscan-audit` by its own
output would be exactly the circularity the moddability benchmark exists to
avoid, where a heuristic that defines truth scores perfectly by construction.

So this check measures the lens against an **external authority it does not
control**: [Bandit](https://github.com/PyCQA/bandit), the established Python
security linter. The question it answers is narrow and honest:

> Within the sinks the lens *claims* to cover, does it find what Bandit finds?

```bash
pip install "modscan[crosscheck]"
python security-crosscheck/crosscheck.py
python security-crosscheck/crosscheck.py --target click --target pygments
```

Offline and free apart from the target packages: no LLM, no API key.

## What is compared, and what is not

Only the sinks the lens claims: **code execution**, **deserialization**,
**process spawning**. Bandit's other tests — weak crypto, `assert`, SQL
injection, hardcoded passwords — are excluded on purpose. The lens explicitly
does not cover them, so counting them would measure a promise never made and
make the number meaningless.

| Bandit test | Lens category |
|---|---|
| B102 `exec_used`, B307 `eval` | code_exec |
| B301 pickle, B302 marshal, B506 `yaml.load` | deserialization |
| B602–B606 subprocess / shell / start-process | process |

The lens's **dynamic_load** category (`import_module`, `entry_points`) has no
Bandit counterpart, so it is left out rather than counted against either tool.

## Two asymmetries that are not defects

- **"lens-only" is not a false-positive count.** Bandit has no test for
  `__reduce__` or the builtin `compile`, both of which the lens catalogues. On
  SQLAlchemy this is most of the difference (35 `__reduce__` definitions). It is
  extra coverage, not noise.
- **Line attribution differs on multi-line calls.** Bandit sometimes reports a
  continuation line where the lens reports the line the call starts on. A
  three-line tolerance absorbs this; without it, one finding looks like a miss on
  one side *and* a false positive on the other.

## What it found (the reason this harness exists)

Its first run earned its keep. Against Bandit on click, pygments and SQLAlchemy
the lens matched **26 of 27** in-scope findings. The single miss was real:
`os.startfile` was not in the catalog. That gap — and its neighbours `os.popen`,
the `os.exec*`/`os.spawn*` family and `commands.getoutput` — were added as a
direct result, along with raising a `subprocess.*` call to high severity when it
passes a literal `shell=True`.

## What this does and does not settle

**Settles:** catalog completeness. The lens is at parity with — and in places
broader than — the tool security reviewers already trust.

**Does not settle:** whether a reviewer finds risk-ranked enumeration
*actionable*, or whether they would want shallow taint ("is this `eval`
reachable from input?"). That needs a human, and is tracked in
[#60](https://github.com/Rinkia/modscan/issues/60). Bandit's own wide adoption
*without* taint analysis is meaningful prior evidence, but it is not the same as
a reviewer trying this tool on a dependency they know.
