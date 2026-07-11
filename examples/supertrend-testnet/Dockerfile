# custos-runner testnet example image.
#
# This example keeps a source-built image because the official v0.2.0 runtime
# image does not yet include the NautilusTrader extra, sops, or age.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends age ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

# sops (static release binary). Pin a known version for reproducibility; adjust
# SOPS_VERSION / arch if your platform differs.
ARG SOPS_VERSION=v3.9.0
RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL -o /usr/local/bin/sops \
        "https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.${arch}" \
    && chmod +x /usr/local/bin/sops

# uv for a reproducible install pinned by the committed uv.lock.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY . /app
# nautilus extra brings NautilusTrader (needs Python 3.12+; base image is 3.13).
RUN uv sync --extra nautilus

ENTRYPOINT ["uv", "run", "arx-runner"]
CMD ["start"]
