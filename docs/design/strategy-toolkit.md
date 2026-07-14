# Strategy toolkit and execution contract

**Status:** authoritative for Custos execution ABI and artifact verification.

## Ownership

Custos owns the strategy execution ABI, toolkit implementation, artifact
verification schema, and local fail-closed verifier. Philosophers-Stone owns
strategy source and produces canonical release BOM bytes. Crucible owns
StrategyRelease, artifact selection, DeploymentSpec, effective configuration,
and business risk policy.

The legacy Philosophers-Stone `build-image.sh` to Crucible Python publication
and deployment path remains an independent compatibility lane. It cannot
produce a v1.team receipt or act as a fallback for this contract.

## Runtime and configuration

`deployment_instance_id` is the only runtime address. `deployment_spec_id`,
`deployment_spec_digest`, and `generation` are provenance and ordering inputs.
Catalog aliases never authorize or address execution. The fixed entry-point
group is `alephain.strategy_runtime.v1`.

The adapter receives final effective config from a verified signed Crucible
command. Custos parses JSON numbers as `Decimal`, rejects duplicates and
non-finite numbers, recursively freezes containers, and recomputes
`effective_config_digest`. Adapters cannot merge defaults or mutate config.

`sha256-canonical-json-v1` uses UTF-8, recursively sorted object keys, preserved
array order, finite Decimal numbers, and no insignificant whitespace.

## Artifact boundary

`StrategyManifestV1` is artifact-local compatibility metadata.
`StrategyArtifactRefV1` describes exact executable and manifest bytes, runtime
artifacts, attestation, SBOM, and contract schema. Neither contains release,
deployment, approval, or selection state.

Custos does not define canonical `StrategyReleaseBomV1`. It consumes the PS BOM
and requires a lossless member projection from Crucible with base/contracts,
Nautilus, and strategy wheels plus manifest, attestation bundle, SBOM, contract
schema, normalized source tree, and every runtime artifact.

The signed command binds runtime identity, spec provenance, generation,
StrategyRelease id, BOM digest/member table, ArtifactRef, and effective config
digest. The verifier receipt echoes the full binding and verified member table.

Trust roots and expected issuer/workflow/policy come from signed immutable local
Custos release configuration. Artifact metadata may reference, but cannot
select, trust roots. Verification and safe extraction precede import.

## Python and inventory

The `custos-strategy-toolkit` base/contracts distribution supports Python
>=3.11. The separate `custos-strategy-toolkit-nautilus` distribution requires
Python >=3.12,<3.13, exact matching base version, and `nautilus-trader==1.230.0`;
Python 3.11 resolution must fail rather than omit NT.

`docs/authority/strategy-toolkit-inventory-v1.json` classifies every current
deterministic input below legacy `shared/` and `vendor/`. There are 241 inputs:
91 shared and 150 private-vendor files. Earlier Plan prose counted 459 general
filesystem entries; that is not the deterministic extraction set.

Task 1 moves no production source. The vendored tree remains the single runtime
authority until receipt-backed cutover. Extraction may not retain top-level
`shared`/`pandas_ta`, mutate `sys.path`, fake a distribution, or leave two
writable canonical copies.

Run `make strategy-contract-assets` to generate schema, inventory, golden, and
digest-index assets. `make check-strategy-contract-assets` detects drift.

The canonical handoff name is `Custos Plan 18 Task 2 schema receipt`. Its draft
must remain pending until exact producer commit, clean-worktree state,
Crucible/PS review receipts, asset-index digest, and fresh `make check-authority`
evidence are recorded.
