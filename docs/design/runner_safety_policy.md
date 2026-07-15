# Runner safety policy consumer

Crucible-rust owns the versioned aggregate runner-cap policy. Its authority key
is tenant id + logical trading mode + runner UUID. `live`, `sandbox` and
`testnet` are logical modes; the physical sim database role is not a mode.
ARX authorization, DeploymentSpec `risk_config`, deployment commands, Custos
defaults and toolkit manifests cannot create or override this owner policy.

## Exact contract boundary

Custos byte-vendors the current CR99 schema, golden, sidecars and producer-v3
receipt. `CrucibleRunnerSafetyPolicyAuthenticator` verifies the Rust struct-order
compact JSON policy digest, exact event bytes, derived subject, event bindings,
fingerprint and Ed25519 signature before validating tenant/mode/runner scope.
This is not key-sorted JCS. The golden signature is synthetic contract evidence
and is never accepted as runtime signature evidence.

The immutable revision is policy id, policy version, generation, digest,
previous-policy fence, effective time and expiry. Initial policy version and
generation are 1 with no prior. Every successor advances both values by exactly
one and binds the prior id/version/generation/digest. Missing, stale, conflicting,
downgraded, wrong-scope, inactive, not-yet-effective, expired or invalidly signed
policy fails closed.

## Current readiness

T7A is `READY_CONTRACT_CONSUMER_ONLY`. The producer chain is currently on
`codex/cr99-runner-policy`, not crucible-rust main. Migration 0117 is prepared
but not executed, ordinary migrator wiring and runtime publication are false,
and Custos has not yet durably consumed a runtime policy. Contract readiness
therefore does not enable the daemon, live, runtime or production capability.
