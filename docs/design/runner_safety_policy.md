# Runner safety policy consumer

Crucible-rust owns the versioned aggregate runner-cap policy. Its authority key
is tenant id + logical trading mode + runner UUID. `live`, `sandbox` and
`testnet` are logical modes; the physical sim database role is not a mode.
ARX authorization, DeploymentSpec `risk_config`, deployment commands, Custos
defaults and toolkit manifests cannot create or override this owner policy.

## Exact contract boundary

Custos consumes the signed Crucible runner-safety-policy V1 producer receipt and
its exact schema/golden pins at the runtime boundary; it does not vendor a second
owner asset set. `CrucibleRunnerSafetyPolicyAuthenticator` verifies the Rust
struct-order compact JSON policy digest, exact event bytes, derived subject,
event bindings, fingerprint and Ed25519 signature before validating
tenant/mode/runner scope.
This is not key-sorted JCS. The golden signature is synthetic contract evidence
and is never accepted as runtime signature evidence.

The immutable revision is policy id, policy version, generation, digest,
previous-policy fence, effective time and expiry. Initial policy version and
generation are 1 with no prior. Every successor advances both values by exactly
one and binds the prior id/version/generation/digest. Missing, stale, conflicting,
downgraded, wrong-scope, inactive, not-yet-effective, expired or invalidly signed
policy fails closed.

## Durable code boundary

T7B advances the local implementation to `READY_CONTRACT_CONSUMER_CODE_ONLY`.
After signature verification, exact policy and verification material are stored
in the existing RunnerFact SQLite database. The sole first-production state
schema V1 includes one scoped policy head; it does not add a second database or
outbox. A successor must advance
version and generation by exactly one and match the durable prior fence.
Restart recovery rejects missing, inactive, premature and expired policy.

`LocalCapConfig` and `FallbackBreakerConfig` can only be built from that verified
policy or from the explicit strictest sandbox/testnet fallback. Live has no
fallback. The reconciler never reads DeploymentSpec `risk_config` for these
limits. Risk-reducing intents remain permitted by the local cap contract.

## Current readiness

The signed Crucible V1 producer receipt and exact-byte pin are not yet available,
runtime publication is false, and the daemon has not consumed a real signed policy.
The native engine-boundary order interceptor and full reservation lifecycle are
also open. Therefore code-only readiness does not enable the team daemon, live,
runtime or production capability.
