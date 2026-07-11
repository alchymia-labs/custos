# Changelog

All notable changes to `custos-runner` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The complete versioning contract — what is allowed / forbidden per MAJOR /
MINOR / PATCH bump, LTS window, security patch SLA, key-rotation protocol —
lives in [`docs/lts-commitment.md`](docs/lts-commitment.md) and
[`docs/upgrade-path.md`](docs/upgrade-path.md).

## [Unreleased]

## [0.2.0] - 2026-07-11

The 0.2.0 release combines the Plan 11 clean-break CLI redesign with the
Plan 12 distribution-and-contract-versioning work. Existing 0.1.x operators
must run through [`docs/upgrade-path.md`](docs/upgrade-path.md) — the state
namespace has moved from `~/.custos/` to `~/.arx/` and the legacy
`SopsAgeVault` multi-credential-in-one-JSON sops file has been replaced by
per-key `.enc` files under `~/.arx/vault/`.

### Added

- `[project.scripts].arx-runner` — single console-script entry
  (`arx-runner enroll` / `arx-runner vault put | verify | list` /
  `arx-runner start`) dispatching through `custos.cli.subcommands:main`.
- Multi-stage `Dockerfile` — Python 3.12-slim `builder` + slim `runtime`,
  non-root `USER 1000:1000`, `VOLUME ["/home/custos/.arx"]` for persistent
  state, OCI provenance labels (`org.opencontainers.image.*`). Published as
  `ghcr.io/the-alephain-guild/custos:v0.2.0`.
- Sigstore keyless wheel signing — `.github/workflows/scripts/sign-wheel.sh`
  emits `<wheel>.sigstore` bundles verifiable against the tag-driven
  cert-identity via `sigstore verify identity`.
- Cosign keyless docker-image signing — `.github/workflows/release.yml`
  `sign-docker` job attaches an OIDC signature to the pushed image.
- 8-job release workflow — build-wheel → sign-wheel → build-docker →
  sign-docker → publish-pypi → publish-ghcr → verify-release →
  release-notes. Triggered by `v[0-9]+.[0-9]+.[0-9]+` stable tags only;
  RC tags run on a separate pre-release workflow.
- `docs/lts-commitment.md` — LTS window (EOL ≥ 12 months per minor line),
  security patch SLA (30 days), release cadence (quarterly best-effort),
  key-rotation protocol, deprecation grace window.
- `docs/upgrade-path.md` — 0.x → 1.0 promote checklist and minor-line
  upgrade template.
- `docs/reproducible-build.md` — `SOURCE_DATE_EPOCH` + `uv.lock` freeze,
  double-build bytes-identical verification.
- `docs/gateway-contract/v1/` — JSON Schemas for the four CustosGateway
  payloads (`enrollment`, `deployment_status`, `telemetry_snapshot`,
  `heartbeat`) with a golden-snapshot backward-compat gate.
- `docs/ops/05-deployment.md` §Docker Runtime Volume Mount — append-only
  section documenting `docker run -v ~/.arx:/home/custos/.arx …` and the
  fail-loud message when the volume is missing.
- `CONTRIBUTING.md` + `SECURITY.md` — public-repo façade (test runner,
  PR flow, vulnerability disclosure, Apache-2.0 as-is disclaimer).
- `[project.optional-dependencies].lts` — release-engineering toolchain
  (`sigstore>=3.0,<4.0` + `pytest-docker>=3`).
- `[tool.hatch.build.hooks.custom]` + `hatch_build.py` — reproducible-
  build defence-in-depth hook honouring `SOURCE_DATE_EPOCH`.
- Pytest markers `docker` / `ci_only` / `slow` — registered for the
  distribution-level gates so unregistered marks no longer emit warnings.

### Changed (BREAKING — Plan 11)

- State namespace `~/.custos/` → `~/.arx/`. `~/.custos/enrollment.json`
  and `~/.custos/state/` must be moved before the first `arx-runner
  start` on 0.2.0; the daemon does NOT auto-migrate (CEO clean-break
  directive 2026-07-10).
- Vault storage model: the multi-credential-in-one-JSON `SopsAgeVault`
  file is replaced by per-key `.enc` files under `~/.arx/vault/`.
  Existing operators must `sops --decrypt` their old vault manually and
  re-add each key via `arx-runner vault put`.

### Removed (BREAKING — Plan 11)

- Legacy `python -m custos` entry point — now `sys.exit(2)` with a
  pointer to `arx-runner start`.
- Legacy `custos` console script — removed to avoid long-term dual-CLI
  drift; `arx-runner` is the single entry.
- `SopsAgeVault` class + supporting code paths in
  `src/custos/core/credential_vault.py` (`_BaseVault` / `AuditEvent`
  preserved; only the sops-file model is retired).
- `--sops-file` and `--age-key-file` CLI flags.

### Fixed

- No externally reported bugs — 0.2.0 is the first tagged release since
  the initial extraction; the `Fixed` section will populate from 0.2.1
  onwards.

### Security

- No CVEs published against 0.1.x. Vulnerability disclosure now goes
  through GitHub Security Advisories (see `SECURITY.md`) with a 30-day
  best-effort patch SLA (see `docs/lts-commitment.md`).

[Unreleased]: https://github.com/the-alephain-guild/custos/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/the-alephain-guild/custos/releases/tag/v0.2.0
