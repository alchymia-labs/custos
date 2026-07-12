# custos-runner complete official runtime image.
#
# Multi-stage: `builder` installs the wheel + Nautilus extra against Python 3.12
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
# `custos-runner` on PyPI. Transitive Python dependencies still resolve from
# PyPI during this pip step, which does not consume `uv.lock`; bit-for-bit image
# reproducibility remains a separate workstream. The release trust anchor is
# the candidate image digest: CI tests that digest, promotes the same digest to
# stable tags, and signs it with cosign.
COPY dist/custos_runner-*.whl /tmp/
RUN set -eux; \
    wheel="$(find /tmp -name 'custos_runner-*.whl' -print -quit)"; \
    test -n "$wheel"; \
    pip install --root-user-action=ignore "${wheel}[nautilus]"

FROM python:3.12-slim AS runtime

# The vault runtime shells out to age and sops. Keep curl and CA roots in the
# final image for operator diagnostics and explicit standalone bootstrap use.
RUN apt-get update \
    && apt-get install -y --no-install-recommends age ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# sops is not packaged in Debian stable. Pin its upstream binary, map Docker's
# architecture names explicitly, and verify the release SHA-256 before install.
# Checksums: https://github.com/getsops/sops/releases/tag/v3.13.2
ARG TARGETARCH
ARG SOPS_VERSION=3.13.2
ARG SOPS_SHA256_AMD64=154dfe4cd70554bdd82b98e4cd4acf191d43d01ead6f00a73477aa44c4ac42ef
ARG SOPS_SHA256_ARM64=78abf2e15c86250a1553ae6f53aba96be6b2a8126f160b1534959add3467ad76
RUN set -eux; \
    architecture="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$architecture" in \
        amd64) checksum="$SOPS_SHA256_AMD64" ;; \
        arm64) checksum="$SOPS_SHA256_ARM64" ;; \
        *) echo "unsupported sops architecture: $architecture" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.${architecture}"; \
    curl --fail --location --silent --show-error "$url" --output /usr/local/bin/sops; \
    echo "$checksum  /usr/local/bin/sops" | sha256sum --check --strict -; \
    chmod 0755 /usr/local/bin/sops

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

# Keep the executable and default action separate so management commands work
# without overriding the entrypoint while the no-argument path remains the
# reconcile daemon.
ENTRYPOINT ["arx-runner"]
CMD ["start"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["arx-runner", "health"]

# OCI provenance labels (Plan 12 DP6): let auditors trace a running image
# back to source. The concrete `revision` / `created` values are injected by
# the CI workflow via `docker build --label` overrides at release time.
LABEL org.opencontainers.image.title="custos-runner" \
      org.opencontainers.image.description="Non-custodial self-hosted execution runner (Alephain Guild)" \
      org.opencontainers.image.source="https://github.com/the-alephain-guild/custos" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="The Alephain Guild"
