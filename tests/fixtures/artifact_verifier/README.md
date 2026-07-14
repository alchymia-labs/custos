# Artifact verifier fixtures

The first T5 kernel slice uses real Ed25519 signatures and real wheel ZIP bytes
generated inside focused tests. It intentionally does not check in a fabricated
Sigstore bundle.

A real offline Sigstore bundle, matching subject bytes and pinned trusted-root
snapshot remain a T5 blocker. Until that fixture and the production Sigstore adapter
land, the kernel accepts only an explicitly injected capability and production
composition must fail closed when that capability is absent.

The checked-in `sigstore-production-trusted-root.json` is the unmodified trusted-root
metadata shipped by the locally locked `sigstore==3.6.7` distribution. Its detached
SHA-256 protects the test fixture from drift. There is still no real DSSE bundle in the
repository, so tests using this root prove offline root loading and fail-closed bundle
rejection, not successful cryptographic acceptance.

The additive public pre-import receipt contract is also still blocked. The current
`PreImportVerificationResult` is internal-only and cannot replace or populate the
existing public receipt's `loaded_entry_point`. Plan 18 Task 5 therefore remains open
until both the real offline Sigstore adapter and coordinated public receipt land.
