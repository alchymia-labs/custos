"""Pre-import strategy artifact verification kernel.

This package deliberately has no runtime composition or engine activation. The
public cross-repository verification receipt remains owned by the coordinated
contract plan; this first slice returns only an internal typed result.
"""

from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from custos.artifacts.verifier import (
    ArtifactVerifierKernel,
    PreImportVerificationRequest,
    PreImportVerificationResult,
    SigstoreVerifierCapability,
)

__all__ = [
    "ArtifactVerificationCode",
    "ArtifactVerificationError",
    "ArtifactVerifierKernel",
    "PreImportVerificationRequest",
    "PreImportVerificationResult",
    "SigstoreVerifierCapability",
]
