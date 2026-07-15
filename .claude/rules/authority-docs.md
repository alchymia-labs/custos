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

Plan 18 T5e is `PREPARED_BLOCKED_EXTERNAL_RUNTIME_RECEIPTS`. The corrected
runtime reads only the T4 durable desired command after T3 signature/intake,
independently verifies the signed runner-local policy, derives members only from
the complete PS `StrategyReleaseBomV1`, verifies the detached bundle and Crucible
acceptance evidence, quarantines before atomic activation, commits active state
before any Python import, and constructs a deep-frozen `StrategyExecutionContext`.
`StrategyArtifactRefV1`, historical indexes and path/hash/parameter compatibility
fields are never production fallbacks. `DevelopmentSourceRefV1` is an explicit,
non-promotable sandbox-only union member. Because no real PS bundle receipt or
Crucible C6 acceptance receipt exists yet, capability/runtime/production remain
false; tests may exercise a synthetic future capability but must not publish READY.

Plan 19 T5 is `PREPARED_BLOCKED_ARTIFACT_RUNTIME_CAPABILITY`. It additively
extends the existing engine protocol with typed `EngineReadyReceipt` and
`EngineTerminalEvent`, persists restart budget in `command_in_progress_lease`
inside the same RunnerFact SQLite database, and routes ready or terminal state
through the T4 atomic lifecycle transactions. Timeout, task failure and zombie
disconnect use one bounded restart/backoff/quarantine state machine; restart
replay probes a matching ready engine before deploy. The daemon now fails when
any long-running task exits unexpectedly and shuts down in intake/deployment/
fact-flush/transport order. The team daemon is not composed while the Plan 18
T5e real artifact capability is false, and live remains false.

Plan 19 T6 is `READY_RELIABLE_PORTFOLIO_SEMANTICS_ONLY`.
`NautilusPortfolioSnapshotProvider` is the sole adapter for actual portfolio
equity, trusted marked positions and position PnL consumed by status, breaker and
RunnerFact risk observations. Missing equity or mark is explicitly unreliable and
the breaker fails closed. This receipt does not authorize a runner aggregate cap:
T7 must consume the Crucible Plan 99 signed versioned policy, DeploymentSpec
`risk_config` cannot override it, and live/runtime/production remain false.

Plan 19 T7A is `READY_CONTRACT_CONSUMER_ONLY`. Custos byte-vendors the exact
CR99 producer schema/golden/sidecars and producer-v3 receipt and verifies Rust
struct-order policy digest plus exact-event Ed25519 signature at
`CrucibleRunnerSafetyPolicyAuthenticator`. Authority is tenant + logical mode +
runner UUID. The current producer chain is not yet on crucible-rust main,
migration 0117 is unexecuted, publication is disabled, and the golden signature
is synthetic; therefore durable/runtime policy consumption, daemon, live,
runtime and production remain false.

Plan 19 T8a is `READY_CONTRACT_PRODUCER_CANDIDATE_ONLY`. Custos producer commit
`af8a39123b9c7b4e7b9b51361339a504af1d2096` freezes current coordinate
`custos.runner-fact.v1/candidate-2026-07-15.2`: the instance-keyed,
generation-non-reset RunnerFact v1 schema, signed golden, exact signing-preimage
vector, five-projector capability, 13-kind parity matrix and sequence-continuation
fixture. Runtime-log identities include the complete stream authority; lifecycle
identities use stable command/apply identity and exclude observation time. The
capability loader pins the closed projector map and unknown-kind disposition.
The synthetic signing key is golden evidence only. `.1` and its unchanged receipt
are `NON_CURRENT_SUPERSEDED`. Crucible Phase-A compatibility, runtime RC, real
runtime round trip, engine/daemon, live/runtime and production remain false until
the independent receipts named by Plan 19 arrive. Any asset-byte change requires
a new candidate coordinate and receipt.

Task 2 remains immutable historical review evidence. After Plan 18 T3, the
current contract implementation is
`packages/custos-strategy-toolkit/src/custos_toolkit/contracts/strategy_execution.py`.
`docs/authority/receipts/custos-plan-18-task-3-distribution-receipt.json` binds that
canonical path to the reviewed Task 2 source digest; the old module path is only
a non-canonical re-export shim.

Run make check-authority after changing ownership or protocols.
