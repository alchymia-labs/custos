"""Exceptions for warmup and checkpoint validation."""


class CheckpointValidationError(Exception):
    """
    Raised when checkpoint validation fails.

    This exception indicates that the indicator state after snapshot restore
    does not match the expected values. The strategy should stop running
    to prevent trading with potentially incorrect indicator state.
    """

    pass
