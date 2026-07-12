# custos-runner — Upgrade Path

The authoritative upgrade guide. Every minor / major release adds a section
here in reverse-chronological order; the top of the file always describes
the current recommended path.

## 0.2.x → 0.3.0 (complete runtime clean break)

0.3.0 replaces the boolean engine switch with `--engine nautilus|noop`, makes
Nautilus the default, validates every desired-state message through the strict
`DeploymentSpec`, and provides the complete runtime as a verified local image.

1. From the Custos checkout, run `make verify-local-v030` to build and gate
   `custos-runner:v0.3.0`; remove any derived Custos Dockerfile used only to
   add NautilusTrader, PyYAML, sops, or age.
2. Replace the removed boolean engine flag with `--engine nautilus`. Use
   `--engine noop` only for non-live contract tests.
3. Add `generation >= 1`, `lifecycle_state`, and `strategy_config` to every
   spec; validate with `arx-runner deployment validate --spec-file <path>`.
4. For standalone NATS, run `arx-runner nats bootstrap --profile standalone`
   before the runner. Do not expect `start` to create streams.
5. Publish through `arx-runner deployment publish` and gate readiness with
   `arx-runner health`.

PS Plan 49 remains blocked until this upgrade is complete. PS consumes the
verified local image directly, maintains no derived Custos Dockerfile, and
owns only strategy code plus `strategy_config` assembly. Remote release is
deferred and is not a prerequisite for local PS integration.

## 0.1.x → 0.2.0 (Plan 11 + 12 breaking release)

0.2.0 is the first clean-break release since the 0.1.x extraction. The
`CHANGELOG.md` 0.2.0 entry is the canonical summary; the exact operator
steps are:

```bash
# 1. install the new wheel
pip install --upgrade custos-runner              # or: uv sync --extra dev

# 2. move state
mkdir -p ~/.arx
mv ~/.custos/enrollment.json ~/.arx/enrollment.json  # if present
mv ~/.custos/state           ~/.arx/state            # if present

# 3. re-provision every key one at a time (per-key .enc replaces the
#    single sops JSON; there is deliberately no auto-migration)
sops --decrypt ~/.old-vault/vault.json > /tmp/legacy.json
# read /tmp/legacy.json, then for each { key_id, key_material } pair:
arx-runner vault put --key-id <id>
# ... and after the last one:
shred -u /tmp/legacy.json

# 4. drop the old --sops-file / --age-key-file CLI flags
#    from any systemd unit / launchd plist / docker-compose service.

# 5. verify a paper reconcile before enabling live
arx-runner start --paper-only
```

Docker operators must additionally mount the new `~/.arx` volume so
per-key `.enc` files persist across container restarts. The Dockerfile
declares `VOLUME ["/home/custos/.arx"]`; the operator side is:

```bash
docker run --rm \
  -v ~/.arx:/home/custos/.arx \
  ghcr.io/the-alephain-guild/custos:v0.2.0
```

See [`ops/05-deployment.md`](ops/05-deployment.md) §Docker Runtime Volume
Mount for the full pattern including `--user "$(id -u):$(id -g)"` when
mounting a host directory whose ownership doesn't match container UID/GID.

## 0.x → 1.0 Promote Checklist

The 0.x → 1.0 promote is contractually gated on ALL of:

- [ ] arx-side wire ready: the `CustosGatewayImpl` in
      `arx/backend/crates/coordination/src/custos.rs` no longer returns
      `CoordinationError::Unavailable`; the four methods really persist +
      forward payloads (arx-79 wire close-out).
- [ ] Three consecutive minor releases (`0.Y.0`, `0.Y+1.0`, `0.Y+2.0`)
      with zero breaking changes to `gateway-contract/v1/*.schema.json`
      or `[project.scripts]`.
- [ ] `gateway-contract/v1/` covers 100% of the four CustosGateway
      typed methods (already the case; keep true).
- [ ] `docs/lts-commitment.md` has at least one row already inside its
      EOL window (i.e. we've kept the LTS promise on a prior line).
- [ ] Council-level RFC: 1.0 promote is a MAJOR SEMVER bump and
      requires a Council debate + ADR entry per the workspace
      `deviation-protocol.md`.

Once all boxes are checked, the promote itself is:

1. Bump `pyproject.toml [project].version = "1.0.0"`.
2. Add a `## [1.0.0] - YYYY-MM-DD` section to `CHANGELOG.md`.
3. Tag `v1.0.0`; the standard release workflow handles the rest.
4. Update `docs/lts-commitment.md` with a `1.0.x` row.

## Minor-line upgrade template

Copy this into a new section for each minor bump:

```
## 0.<prev>.x → 0.<next>.0

### What changed

- {feature | fix | breaking? summary}

### Migration steps

- {commands the operator must run}

### Rollback

- `pip install "custos-runner==0.<prev>.*"` — configuration remains
  backward-compatible within a minor line, so rollback is a wheel bump.
```
