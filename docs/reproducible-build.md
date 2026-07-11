# Reproducible builds

`custos-runner` publishes byte-for-byte reproducible wheels so an external
auditor can rebuild from source, compare hashes against the published
artifact, and prove the running binary is a deterministic function of the
audited source tree. This is the technical foundation for the Non-Custodial
red line "audit-able open source": the on-wire wheel is what the source
audit covers.

## The three knobs

1. **`SOURCE_DATE_EPOCH`** — a Unix timestamp (seconds) that hatchling
   uses in place of the host clock when stamping file mtimes into the
   wheel's ZIP metadata. Without this pin, every rebuild embeds "now"
   and the resulting wheels have different byte hashes even though the
   source is identical.
2. **`uv.lock`** — the committed lock file freezes every transitive
   dependency to a specific version + digest. `uv build` reads it via
   `[tool.uv].package = true` so a stale lock is caught immediately.
3. **`hatch_build.py`** — a custom `BuildHookInterface` subclass wired
   through `[tool.hatch.build.hooks.custom]`. hatchling ≥ 1.20 already
   honours `SOURCE_DATE_EPOCH` natively, so the hook body is a no-op —
   its job is to *log* whether the epoch is set (so an operator running
   `uv build` locally can see it engaged) and to be a stable place to
   grow real behaviour if hatchling regresses on native determinism.

## Manual reproduction (auditor workflow)

```bash
# 1. clone the repo at the tag you want to verify
git clone https://github.com/the-alephain-guild/custos.git
cd custos
git checkout v0.2.0

# 2. pin the epoch to the tagger date at midnight UTC (or copy the value
#    the release workflow used, exposed as the tag's commit timestamp).
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct v0.2.0)"

# 3. build; the resulting wheel MUST hash-match the released wheel.
uv build --out-dir /tmp/verify
sha256sum /tmp/verify/*.whl
```

Then compare against the SHA256SUMS attachment on the corresponding
[GitHub Release](https://github.com/the-alephain-guild/custos/releases).
A mismatch means either the epoch is wrong (check the release notes for
the exact value the workflow used), or the source has been tampered
with — in which case the sigstore attestation would also fail against
the cert-identity.

## Automated verification

`tests/test_reproducible_build.py` runs two `uv build` cycles with the
epoch pinned and asserts hash equality. It's `@pytest.mark.slow`
because a double build takes tens of seconds; it is not part of
`make verify` but runs on the nightly CI job.

A companion test (`test_wheel_bytes_differ_without_epoch`) is
`xfail(strict=True)` today because hatchling ≥ 1.20 is natively
deterministic — an epoch-less rebuild already produces identical wheel
bytes on the currently pinned hatchling. This is why the epoch pin
here is *defence-in-depth* rather than the sole knob: it defends
against a future hatchling regression that reintroduces host-clock
leakage. If such a regression lands, the epoch-less test would then
correctly differ, the xfail would fire, and we'd notice.

## Docker image reproducibility

Docker image reproducibility is a separate workstream (buildkit
timestamp normalization is not stable across buildkit versions).
For 0.2.0 the image side of "audit the binary" is served by:

- OCI labels — `org.opencontainers.image.revision = <commit sha>` and
  `org.opencontainers.image.created = <tag timestamp>` are baked into
  the image at CI time.
- Cosign keyless signature — the pushed image digest is signed with the
  workflow's cert-identity, so the digest itself is auditable.
- `verify-release.sh` re-pulls the image and runs `docker inspect` +
  `docker run --help` to prove the digest and the runtime behaviour
  match what CI saw.

A follow-up plan (tracked in
[`upgrade-path.md`](upgrade-path.md#follow-up)) will pin the image
build to a specific buildkit + `SOURCE_DATE_EPOCH` combination for
bit-for-bit image reproducibility as well.
