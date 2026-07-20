# Releasing

MODScan publishes to PyPI with **Trusted Publishing (OIDC)**. No API token is
generated, stored, or pasted anywhere — PyPI verifies the GitHub Actions
workflow identity directly. A leaked token is the most common way a package gets
hijacked, so the safest token is the one that does not exist.

## One-time setup (must be done by a project owner, in a browser)

This part cannot be automated — it is an account action on PyPI.

1. Sign in to <https://pypi.org> and go to
   **Your projects → Publishing → Add a new pending publisher**.
   ("Pending" is the right choice while the project does not exist on PyPI yet —
   it reserves the name on first publish.)
2. Fill in exactly:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `modscan` |
   | Owner | `Rinkia` |
   | Repository name | `modscan` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. Optionally repeat on <https://test.pypi.org> with environment `testpypi`, so
   dry runs are possible before the real thing.
4. In GitHub → **Settings → Environments**, create environments named `pypi`
   (and `testpypi`). Adding a required reviewer to `pypi` means no release can
   publish without a human approving it — recommended.

## Publishing a release

1. Make sure `master` is green and the working tree is clean.
2. Bump `version` in `pyproject.toml`.
3. Move the accumulated `## [Unreleased]` entries in `CHANGELOG.md` into a new
   dated version section, and open a fresh empty `Unreleased`.
4. Commit, then tag:

   ```bash
   git commit -am "chore: release X.Y.Z"
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin master vX.Y.Z
   ```

5. Publish a GitHub Release for the tag (body from the CHANGELOG section). That
   is what triggers `publish.yml`.

The workflow builds an sdist and a wheel, runs `twine check --strict`, installs
the wheel into a clean virtualenv and runs the CLI, and only then publishes.

### Dry run first

Before the first real publish, use **Actions → Publish to PyPI → Run workflow**
with target `testpypi`, then verify:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ modscan
```

The extra index is needed because the optional dependencies live on real PyPI.

## Versioning

Semantic versioning. While on `0.x` the API may still change between minor
versions — that is signalled by keeping GitHub Releases marked as
**pre-release** until the ranking heuristics are trustworthy enough to promise
stability.
