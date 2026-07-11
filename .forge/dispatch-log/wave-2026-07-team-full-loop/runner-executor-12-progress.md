# Plan 12 progress marker — runner-executor-12

Worktree: `.worktree/plan-12-runner`
Branch: `custos/plan-12/runner`
Base SHA: `b8021ad`

## Pre-flight gates
- Gate 1: `git log --oneline | grep -q 'plan 11 t8'` PASS
- Gate 2: `grep '^arx-runner = "custos.cli.subcommands:main"' pyproject.toml` PASS
- Gate 3: `grep -c 'SopsAgeVault' src/custos/core/credential_vault.py` = 0 PASS

## T1 — pyproject lts extras + hatch build hook
- SHA: 68fe6cf
- Files: 4 (pyproject.toml + uv.lock + hatch_build.py + tests/test_pyproject_scripts_declared.py)
- Tests: 5/5 new pass (test_pyproject_scripts_declared.py)
- Notes: Plan 11 T8 already registered `arx-runner` script + bumped 0.2.0; T1 layers on `lts` extras + hatch custom hook + pytest markers. Added `[tool.uv].prerelease = "allow"` to unblock sigstore transitive resolution.
- Pre-existing baseline: `test_toolkit_provenance` fails on `b8021ad` (pkg_resources missing without `nautilus` extra) — unrelated to Plan 12.

## T2 — Dockerfile multi-stage + non-root USER 1000 + VOLUME
- SHA: 509c127
- Files: 6 (Dockerfile + .dockerignore + Makefile + 3 test files)
- Tests: 3/3 new docker-marker gates green (image size 160 MB / USER 1000:1000 / entrypoint help exit 0)
- Notes: `pip install /tmp/*.whl` (explicit path, not `--no-index --find-links`) so transitive deps resolve from PyPI while the custos wheel is pinned to the local build.

## T3 — sigstore keyless wheel signing
- SHA: 0b72d59
- Files: 2 (.github/workflows/scripts/sign-wheel.sh + tests/test_wheel_signature.py)
- Tests: 2 new ci_only gates skip locally (no OIDC), CI-gated on release workflow
- Notes: sign-wheel.sh does `sigstore sign --help | grep -- --output-signature` verification (H6 fail-loud) before signing; test asserts bundle exists + `sigstore verify identity` against tag-driven cert-identity (FM8).

## T4 — CI release workflow (wheel + docker + sig + verify)
- SHA: f68e581
- Files: 3 (.github/workflows/release.yml + verify-release.sh + tests/test_release_workflow_shape.py)
- Tests: 5/5 shape-lock tests pass (plain-text assertions, no pyyaml dep)
- Notes: 8-job DAG in documented order (H5), plural permissions (H2), stable-tag pattern (M6), build-docker consumes signed wheel artifact (H1). CI first real run deferred to first v0.2.0 tag push (T4 landing = workflow definition landed).

## T5 — CHANGELOG.md scaffold + README trim Not Included Yet
- SHA: 446c9ef
- Files: 2 (CHANGELOG.md + README.md)
- Tests: no new tests (T6 test_lts_commitment_doc downstream indirectly checks; T4 release-notes CI job depends on CHANGELOG structure)
- Notes: Single 0.2.0 entry integrates Plan 11 (Removed/Changed BREAKING) + Plan 12 (Added) — Cross H1 fix. README §Not Included Yet keeps only telemetry-uplink-bridge + 1.0.0-promote follow-ups.

## T6 — LTS commitment + upgrade path docs
- SHA: 8222281
- Files: 3 (docs/lts-commitment.md + docs/upgrade-path.md + tests/test_lts_commitment_doc.py)
- Tests: 3/3 pass (doc exists / required sections / EOL date row per L1)
- Notes: Includes Key Rotation Protocol (sigstore keyless — rotation surface = workflow cert-identity template), Deprecation Grace, Deviations log. Upgrade path covers 0.1.x→0.2.0 operator steps + 0.x→1.0 promote checklist.

## T7 — Gateway contract v1 JSON Schema + backward-compat golden gate
- SHA: d570e31
- Files: 10 (4 v1 schemas + README + 4 golden fixtures + 1 test)
- Tests: 9/9 pass (4 additive-only checks vs golden + 3 BLK-5 negative shape tests + 2 presence)
- Notes: Enrollment schema `required = {token_hash, runner_id, agent_version}` (Plan 11 T4 wire + R2-C1 fix). Deployment status phase enum `{pending, running, degraded, stopped}` (per docs/domain.md §106 authoritative vocab). Telemetry money fields Decimal-string per red line 0.4.

## T8 — Reproducible build (SOURCE_DATE_EPOCH + bytes-identical rebuild test)
- SHA: df389f1
- Files: 2 (docs/reproducible-build.md + tests/test_reproducible_build.py)
- Tests: 1 pass + 1 xfail(strict=True) — identical-with-epoch passes in ~19s; differ-without-epoch xfails because hatchling ≥1.20 native deterministic (Plan 12 M4 pre-anticipated finding).
- Notes: Epoch pin is defence-in-depth. xfail(strict=True) means a hatchling regression that reintroduces host-clock leakage will surface as unexpected pass = surfaced regression.

## T9 — Close-out (CONTRIBUTING + SECURITY + docker mount doc + status flip)
- SHA: 4950a50 + 6b31a58 (SHA backfill)
- Files: 6 (CONTRIBUTING + SECURITY + docs/ops/05-deployment.md + CLAUDE.md + .forge/README.md + plan 12 md)
- Tests: no new tests; T9 is documentation + status flip
- Notes: Plan 11 T9 gap discovered — `docs/ops/05-deployment.md` still has pre-Plan-11 content (`python -m custos`, `~/.custos/`, `--sops-file`). Plan 12 T9 append-only Docker Runtime Volume Mount section per R2-M1 scope discipline; registered DEV-12-T9-PLAN-11-T9-DOCS-OPS-GAP as follow-up.

## Summary
- 9/9 Tasks ✅
- Commit range: 68fe6cf..6b31a58 (10 commits total including T9 SHA backfill)
- All red-line gates satisfied (no runtime code touched)
- Baseline pre-existing failure `test_toolkit_provenance` remains (unrelated to Plan 12)
- 4 all-low DEV entries logged
- 11 failure-mode contract tests across 8 new test files + 3 negative-shape unit tests (BLK-5)
