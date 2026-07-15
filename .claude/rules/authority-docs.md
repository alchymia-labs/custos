# Authority documents

The machine-readable authority manifest is `authority-manifest.json`. Its
required authority snapshot is repository-local at
`docs/authority/ecosystem-authority.json`, so a standalone clone can run the
gate. Workspace authority documents are optional alignment inputs only.

Precedence:

1. ecosystem data ownership;
2. migration rollout and physical database contract;
3. ecosystem domain model;
4. ecosystem architecture;
5. accepted ADRs;
6. local Custos domain and protocol documents.

Custos owns local execution and signed observations only.
deployment_instance_id is the runtime key. ARX authorization and Crucible
business decisions must not be reimplemented in the runner.

`docs/design/strategy-toolkit.md` and the current pre-sign schema indexed by
`docs/authority/strategy-contract-assets-v3.json` are authoritative for the
corrected Custos ArtifactRef ABI. The current type is `StrategyArtifactRefV2`
with `schema_version: 2`; v1/v2 asset collections and `StrategyArtifactRefV1`
are immutable historical, non-production evidence and never a runtime fallback.
Philosophers-Stone produces the canonical release BOM; Crucible owns
StrategyRelease and artifact selection.

The `Custos Plan 18 Task 5c ArtifactRefV2 producer receipt` is producer-only and
must keep handoff/runtime/production false until exact PS and Crucible owner
reviews plus T5d-A/T5d-B/T5e evidence-consumer, command-consumer and verifier
cutover evidence exist. Never invent or pre-register downstream review receipts.

Plan 18 T5d-A is `READY_CONTRACT_CONSUMER_ONLY`. The v4 authority index byte-pins
the complete PS Plan 54 and Crucible Plan 88 producer assets and their clean source
commits. `StrategyArtifactPreImportVerificationReceiptV2` external-references the
owner schemas and adds only Custos-owned digest bindings and an independent
runner-local policy decision. A Crucible local-policy decision is never a Custos
runner-local policy decision. This receipt does not change the production
verifier/parser or authorize runtime or production readiness.

Plan 18 T5d-B and Plan 19 T2 share one
`READY_COMMAND_CONSUMER_CONTRACT_ONLY` receipt. Crucible Plan 89 remains the sole
runner-command schema/golden producer; Custos byte-vendors the corrected current
A2/B2 assets and exports only `CrucibleRunnerDeploymentCommandV1` as its consumer.
The consumer retains exact signed event bytes, excludes signature bytes from the
producer fingerprint, and requires the full BOM, ArtifactRefV2, detached reference,
ArtifactEvidenceV1 and semantic acceptance bindings. Custos publishes no command
schema, and this STOP changes no daemon, reconciler or runtime composition.

Plan 19 T4 is `READY_DURABLE_STATE_STORE_ONLY`. Desired/applied state, exact
command bytes and receipts, outcomes, leases, activation/quarantine, local policy
references, reservations, exposure checkpoints, RunnerFact sequence and pending
PubAck all share the existing RunnerFact SQLite database and outbox. The stream
identity is tenant + mode + runner + `deployment_instance_id`; spec id, spec digest
and generation are signed fencing/provenance only. Legacy spec-keyed streams require
an explicit intake freeze, pending PubAck drain and per-instance sequence
continuation without rewriting or deleting pending signed payloads. This receipt
does not wire engine apply or the daemon and does not claim runtime or production
readiness; Plan 19 T5 is the next gate.

Task 2 remains immutable historical review evidence. After Plan 18 T3, the
current contract implementation is
`packages/custos-strategy-toolkit/src/custos_toolkit/contracts/strategy_execution.py`.
`docs/authority/receipts/custos-plan-18-task-3-distribution-receipt.json` binds that
canonical path to the reviewed Task 2 source digest; the old module path is only
a non-canonical re-export shim.

Run make check-authority after changing ownership or protocols.
