# custos-docs-site

Documentation site for **custos.alephain.com** — the non-custodial execution
runner.

Authoritative plan:
[`.forge/plans/2026-07/20-custos-docs-site-scaffold.md`](../.forge/plans/2026-07/20-custos-docs-site-scaffold.md).

## Prerequisites

- Node.js **20+**
- npm (or yarn)

## Local development

```bash
cd docs-site
npm ci
npm start                    # opens http://localhost:3000 in English
npm run start:zh             # opens http://localhost:3000 in 简体中文
```

## Build

```bash
npm run build                # output → docs-site/build/
npm run serve                # preview the production build locally
```

## i18n

- Default locale: `en`
- Alternate: `zh-Hans`
- Regenerate translation JSON (adds new/removed keys):

  ```bash
  npm run write-translations -- --locale zh-Hans
  ```

Translation source: `i18n/zh-Hans/`.

## Versioning (deferred to Plan 20 T11)

After content is stable and the site is deployed once, freeze v0.3.0:

```bash
npm run docusaurus docs:version 0.3.0
```

This snapshots `docs/` into `versioned_docs/version-0.3.0/` and adds
`docsVersionDropdown` to the navbar (uncomment in `docusaurus.config.js`).

## Deploy

CI (`.github/workflows/docs-deploy.yml`, Plan 20 T9) builds on push to `main`
under `docs-site/**` and deploys to the `gh-pages` branch. Custom domain is
`custos.alephain.com`, set via `static/CNAME`.

## Content authority

**`docs/**.md`** at the repo root is SSOT. Chapters here consume that content
verbatim (with a `<!-- source: docs/… -->` provenance header) and never fork.

Do NOT surface `docs/authority/*` receipts on the site — those are internal
artifacts. They may be referenced by digest.

## Naming discipline

Follow
[`the-alephain-guild.github.io/data/naming-authority.md`](https://github.com/the-alephain-guild/the-alephain-guild.github.io/blob/main/data/naming-authority.md):

- ARX canonical positioning: **"the neutral quant operating system"** (do not use aliases)
- custos canonical positioning: **"the non-custodial execution runner"**
- ARX phased integrations (Speculum, Athanor, Argus, Synedrion, etc.) MUST NOT
  be presented as current capabilities — obey Phase 3 / Phase 4 discipline
