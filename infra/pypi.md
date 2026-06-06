# PyPI — publish the `keepalive` library

We publish with **trusted publishing** (OIDC via GitHub Actions). No long-lived PyPI token
in the repo.

## 1. Register the pending publisher BEFORE the first release

PyPI must know about the GitHub workflow before the project exists. On PyPI:

1. Log in → Your projects → **Publishing** → "Add a new pending publisher".
2. Fill in exactly:
   - **PyPI Project Name:** `keepalive`
   - **Owner:** the GitHub org/user that owns this repo
   - **Repository name:** this repo's name
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`

The environment name **must** match `environment: pypi` in `release.yml`, or OIDC auth is
rejected.

## 2. The load-bearing permission

The publish job must have:

```yaml
permissions:
  id-token: write
```

This is what lets `pypa/gh-action-pypi-publish` mint the OIDC token PyPI trusts. Without it,
the publish fails even with everything else correct.

## 3. Build from the library package

The library lives at `packages/keepalive` (uv workspace, `uv_build` backend, src/ layout,
ships `py.typed`). Build it specifically:

```bash
uv build packages/keepalive
```

This produces the sdist + wheel in `packages/keepalive/dist/`, which the workflow uploads.

## 4. Cut a release

1. Bump the version in `packages/keepalive/pyproject.toml`.
2. Create a GitHub Release (tag it). `release.yml` triggers on `release: published`.
3. The build job runs `uv build packages/keepalive`; the publish job (environment `pypi`,
   `id-token: write`) uploads to PyPI.

## 5. Verify

```bash
pip install keepalive
python -c "import keepalive; print(keepalive.__version__)"
```
