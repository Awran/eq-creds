"""Shared exception types for the EQ-Creds core layer."""

from __future__ import annotations


class WrongPasswordError(Exception):
    """Raised when a supplied password does not decrypt the target data."""


class VaultNotInitializedError(Exception):
    """Raised when trying to unlock a vault that has never been created."""


class VaultLockedError(Exception):
    """Raised when an operation requires an unlocked vault."""
