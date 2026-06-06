# Mintlify — deploy the docs site (`docs/`)

The docs are Mintlify. Config is `docs/docs.json` (NOT `mint.json`). The CLI is `mint`
(NOT `mintlify`).

## 1. Onboard via the dashboard

1. Go to https://mintlify.com/start and sign in with GitHub.
2. Connect this repo and set the docs directory to `docs/`.
3. Mintlify installs a GitHub app; it auto-deploys on every push to the default branch.

## 2. Local preview

From the `docs/` directory:

```bash
cd docs
mint dev
```

(Install the CLI with `npm i -g mint` if you don't have it.) Preview at the URL `mint`
prints. `mint dev` reads `docs.json` and hot-reloads the `.mdx` files.

## 3. Validate before pushing

```bash
mint broken-links     # catch dead internal links
```

## 4. Custom domain

In the Mintlify dashboard → Settings → Domain → `docs.keepalive.club`. Add the CNAME they
show to DNS.

## Notes

- Navigation is defined in `docs.json` under `navigation.groups`. Add a new page = create
  the `.mdx` and list it in the right group.
- Theme is `mint`, dark-first, amber accent (`#f59e0b`). Don't switch the schema to
  `mint.json` — that's the legacy format.
