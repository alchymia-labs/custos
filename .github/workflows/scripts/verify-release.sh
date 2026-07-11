#!/usr/bin/env bash
# Plan 12 T4: post-publish release verification.
#
# Independent Layer-3 smoke on top of the CI job's own build. Downloads the
# wheel from PyPI, downloads the image from GHCR, verifies both signatures
# against the tag-driven cert identity, then invokes the image with `--help`
# to prove the ENTRYPOINT actually starts (FM2 Layer 3, no dead branch),
# and asserts the image runs as a non-root user.
#
# Usage: bash .github/workflows/scripts/verify-release.sh <version>
#   e.g. bash .github/workflows/scripts/verify-release.sh 0.2.0

set -euo pipefail

VERSION="${1:?version required (e.g. 0.2.0)}"

# Allow the repository owner to be overridden via env (useful for
# fork-based verification runs). Defaults to the canonical Alephain Guild
# path so an operator running this locally against a public release doesn't
# need extra flags.
: "${GITHUB_REPOSITORY:=the-alephain-guild/custos}"
: "${IMAGE_NAME:=ghcr.io/${GITHUB_REPOSITORY}}"

CERT_IDENTITY="https://github.com/${GITHUB_REPOSITORY}/.github/workflows/release.yml@refs/tags/v${VERSION}"
CERT_OIDC_ISSUER="https://token.actions.githubusercontent.com"

echo "== Layer 3: pull + verify wheel signature =="
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
pip download "custos-runner==${VERSION}" --no-deps -d "${TMP}"

if ! command -v sigstore >/dev/null 2>&1; then
    echo "sigstore CLI not on PATH; install with: uv sync --extra lts" >&2
    exit 2
fi

# Fetch the bundle from the GitHub Release attachments; PyPI hosts the wheel
# but not the .sigstore bundle.
whl_name="$(basename "${TMP}"/custos_runner-*.whl)"
bundle_url="https://github.com/${GITHUB_REPOSITORY}/releases/download/v${VERSION}/${whl_name}.sigstore"
curl -fsSL "${bundle_url}" -o "${TMP}/${whl_name}.sigstore"

sigstore verify identity \
    --bundle "${TMP}/${whl_name}.sigstore" \
    --cert-identity "${CERT_IDENTITY}" \
    --cert-oidc-issuer "${CERT_OIDC_ISSUER}" \
    "${TMP}/${whl_name}"

echo "== Layer 3: pull + verify image signature =="
docker pull "${IMAGE_NAME}:v${VERSION}"

cosign verify "${IMAGE_NAME}:v${VERSION}" \
    --certificate-identity "${CERT_IDENTITY}" \
    --certificate-oidc-issuer "${CERT_OIDC_ISSUER}"

echo "== Layer 3: docker run --help smoke (BLK-4 fix, FM2 Layer 3) =="
# ENTRYPOINT is `["arx-runner", "start"]`, so `--help` becomes
# `arx-runner start --help` and prints subcommand help; exit 0 proves the
# entrypoint chain actually resolves and doesn't crash on module import.
docker run --rm "${IMAGE_NAME}:v${VERSION}" --help >/dev/null

echo "== Layer 3: image runs as non-root =="
user="$(docker inspect --format '{{.Config.User}}' "${IMAGE_NAME}:v${VERSION}")"
if [ "${user}" = "root" ] || [ "${user}" = "0" ] || [ -z "${user}" ]; then
    echo "image published as root user (${user@Q}); refusing release" >&2
    exit 1
fi

echo "OK: v${VERSION} wheel + image signatures verify; image runs as ${user}."
