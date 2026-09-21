"""Errors callers can translate into user-facing diagnostics."""


class DomainValidationError(ValueError):
    """Invalid domain input."""


class CoverageError(DomainValidationError):
    """A requested size is outside supported measured coverage."""


class BasisMismatchError(DomainValidationError):
    """Distribution bases cannot be reconciled with available assumptions."""


class IncompatibleComparisonError(DomainValidationError):
    """Results were produced under incompatible conventions."""


class RecipeLockedError(DomainValidationError):
    """A production recipe invariant would be changed."""
