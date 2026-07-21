# MODScan Roadmap

Where the project is, what it does well, where it is weak, and where it goes
next. Kept honest on purpose — a roadmap that only lists wins is a sales page.

## Where it stands

The MVP is complete and published (`pip install modscan`, PyPI 0.1.0): a layered
pipeline — parse → graph → detect → validate → docgen → scaffold — that turns a
source-available codebase into grounded modding documentation. A Python and an
experimental TypeScript front-end, five LLM providers, sandboxed example
validation, breaking-change diffs, and spend controls all work end to end.

The core value is the **ranking**: which extension points reach the top. That
ranking is now instrumented by a labelled benchmark (`benchmarks/`) and measured,
not asserted.

## What the benchmark taught us (measured, not assumed)

Across six real packages, the ranking's quality is uneven and the reasons are
understood:

| Package | recall@10 | Why |
|---|---|---|
| click | 4/4 | Subclass + re-export signals fit it cleanly |
| pluggy | 3/3 | Marker/manager API is re-exported and public |
| sqlalchemy | 1/5 | Real seams extend via compiler registration, invisible to structural heuristics |
| marshmallow | 1/3 | `Field` bases use noop overrides, not `NotImplementedError` |
| pygments | 0/5 | Bases live in submodules, not root; plugin-registry style |
| markdown | (same pattern) | Over-ranks concrete `*Extension` implementations, under-ranks the abstract processor bases |

**The systematic finding**: MODScan is strong at surfacing the extension
*surface* (re-exported, role-named, override-point classes) and weak at
pinpointing abstract bases that use a framework's own conventions
(compiler registries, noop overrides, submodule entry points). The re-export
signal generalises; the override-point and dynamic-import weights were calibrated
to the first three packages and do not. This is written up in
`benchmarks/README.md`, including the signals that were **rejected** on evidence.

## Recently shipped

- **`modscan detect`** — offline extension-point ranking, no LLM, no API key, no
  code execution. The fast, safe way to try MODScan and to run it in CI.
- **GitHub Action** (`action.yml`) — ranked extension points in every PR's job
  summary, safe on untrusted PRs.
- **MCP server** (`modscan[mcp]`, `modscan-mcp`) — the detector as a tool for AI
  clients (Claude Desktop, Cursor).

*These go live for `pip install` users on the next PyPI release (0.1.1).*

## Near-term

1. **Cut the 0.1.1 release** so `detect`, the Action and the MCP server reach
   PyPI users. (Trusted Publishing is already wired; the release is a tag.)
2. **A real-target documentation showcase.** Run the full LLM pipeline on a
   package with an active plugin community and commit the output — the honest
   "does this help a plugin author?" proof. Costs API credits, so it is a
   deliberate, confirmed run.

## Directions, by leverage

The project's real risk is not code — it is adoption. It is a well-built tool
with no external users yet. The directions below are ordered by how much they
move that.

### 1. Prove and sharpen value on real targets *(highest leverage)*
The six-package finding says the ranking works on some extension styles and not
others. The next improvement should be driven by a **real plugin author** saying
what they expected at the top — not by chasing the benchmark number. Candidate
work, each measured against the benchmark before adoption:
- Should a framework's plugin-*discovery* loader sites (`entry_points`) rank as
  extension points at all? (Deferred from the `__import__` fix.)
- A "documented override" signal that catches noop-override bases (marshmallow)
  and submodule-exported bases (pygments) without regressing click/pluggy.

### 2. Lower the barrier further
`detect`, the Action and MCP are in. Remaining: a demo GIF/asciinema in the
README, and promoting the two pinned good-first-issues so the contribution loop
starts turning.

### 3. Security lens *(different audience, same engine)*
A security-weighted mode over the same seams — rank by execution risk
(`eval`, `pickle.loads`, deserialisation) and emit an attack-surface report for
dependency audits and threat modelling. Drafted in
`.claude/prds/security-lens.prd.md`. Needs validation with a real reviewer
before building — the open question is whether risk-ranked enumeration is enough
without shallow taint analysis.

### 4. Robustness for real use
Small gaps that bite the first serious user: graceful degradation when a target
won't import, the self-scan hazard, `sys.modules` restoration after validation.

### 5. Breadth (only after depth)
TypeScript/JavaScript ranking (the parser exists; the ranking work is
Python-only), more benchmark targets, a web UI. Deferred until the Python
ranking generalises — breadth before depth would bake in the current bias.

## How to contribute

The ranking is the place changes matter most, and it is now safe to experiment
on: `python benchmarks/score.py` tells you whether a heuristic change helped
before you open a PR. A CI guard blocks any PR that edits both the labels and the
ranking code in the same change, so the benchmark cannot be quietly bent to
flatter a heuristic. Start with the pinned good-first-issues on GitHub.
