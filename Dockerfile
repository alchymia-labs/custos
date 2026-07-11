# custos-runner Docker image (Plan 12 T2).
#
# Multi-stage: `builder` installs the wheel + LTS extras against Python 3.12
# (nautilus_trader ≥ 1.227 only publishes wheels for 3.12+, see tech-stack.md).
# `runtime` copies site-packages + the `arx-runner` console script over into
# a slim base and switches to the non-privileged `custos` user (UID/GID 1000).
#
# The builder stage consumes a locally built wheel (Plan 12 H1 fix): before
# `docker build` the operator runs `uv build` so `dist/custos_runner-*.whl`
# exists at the build context root. This decouples the image from PyPI
# publication — during the first release cut the wheel isn't uploaded yet,
# and the CI job explicitly stages the wheel artifact from the `build-wheel`
# job (see .github/workflows/release.yml).

FROM python:3.12-slim AS builder

# Copy the pre-built wheel (see Makefile `docker-build` target) and install
# by explicit file path so pip never falls back to the last-published
# `custos-runner` on PyPI. Transitive deps (nats-py, pydantic, structlog,
# uuid6) still resolve from PyPI — they're upstream and unrelated to the
# non-custodial provenance boundary, and `uv.lock` locks their versions at
# release time.
COPY dist/custos_runner-*.whl /tmp/
RUN pip install --root-user-action=ignore /tmp/custos_runner-*.whl

FROM python:3.12-slim AS runtime

# Non-root user (UID/GID 1000). We create a real HOME so that `PerKeyVault`,
# the reconcile loop's state file, and any structured logs can land under
# `~/.arx/` inside the container (which then maps out via VOLUME).
RUN useradd --uid 1000 --create-home --home-dir /home/custos custos
ENV HOME=/home/custos

# Copy the installed wheel from the builder stage (site-packages + the
# generated `arx-runner` console script). We intentionally do NOT re-run
# `pip install` here — a duplicate install is the classic multi-stage
# builder leak that FM11 / `test_docker_image_size.py` guards against.
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/arx-runner /usr/local/bin/arx-runner

# Persist runtime state on the host. `docs/ops/05-deployment.md` §Docker
# Runtime Volume Mount documents the `-v ~/.arx:/home/custos/.arx` pattern
# so operator-provisioned KEK vaults survive container restarts.
VOLUME ["/home/custos/.arx"]

# Pre-create the mount point owned by `custos` (Plan 12 R2-M2 fix): without
# this an anonymous volume mount inherits root ownership, and the first
# `arx-runner enroll` write to `~/.arx/runner.toml` fails with EACCES because
# we run as UID 1000.
RUN mkdir -p /home/custos/.arx /home/custos/.arx/vault /home/custos/.arx/state \
    && chown -R custos:custos /home/custos

USER 1000:1000
WORKDIR /opt/custos

# Plan 11 clean-break locks `arx-runner` as the single entry point; the
# legacy `python -m custos` path is removed. The container's primary purpose
# is the reconcile daemon, so `start` is baked into ENTRYPOINT. One-shot
# management commands (`enroll` / `vault put`) still work via
# `docker run --rm --entrypoint arx-runner <image> enroll <token>`.
ENTRYPOINT ["arx-runner", "start"]

# OCI provenance labels (Plan 12 DP6): let auditors trace a running image
# back to source. The concrete `revision` / `created` values are injected by
# the CI workflow via `docker build --label` overrides at release time.
LABEL org.opencontainers.image.title="custos-runner" \
      org.opencontainers.image.description="Non-custodial self-hosted execution runner (Alephain Guild)" \
      org.opencontainers.image.source="https://github.com/the-alephain-guild/custos" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="The Alephain Guild"
