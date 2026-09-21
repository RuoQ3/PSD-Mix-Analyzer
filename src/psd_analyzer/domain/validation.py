"""Shared numeric and identifier invariants; no silent data repair."""

from collections.abc import Iterable
from math import fsum, isfinite

from .exceptions import DomainValidationError

FRACTION_TOLERANCE = 1e-8


def finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise DomainValidationError(f"{name} must be a finite number, not bool")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DomainValidationError(f"{name} must be numeric") from exc
    if not isfinite(result):
        raise DomainValidationError(f"{name} must be finite")
    return result


def positive(value: float, name: str) -> float:
    result = finite(value, name)
    if result <= 0:
        raise DomainValidationError(f"{name} must be positive")
    return result


def identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be a nonempty string")


def vector(values: Iterable[float], name: str) -> tuple[float, ...]:
    return tuple(finite(v, name) for v in values)


def sizes(values: Iterable[float], *, minimum_count: int = 1) -> tuple[float, ...]:
    result = vector(values, "particle_size_um")
    if len(result) < minimum_count or any(v <= 0 for v in result):
        raise DomainValidationError("Particle sizes must be positive and nonempty")
    if any(a >= b for a, b in zip(result, result[1:], strict=False)):
        raise DomainValidationError(
            "Particle sizes must be strictly increasing; duplicates forbidden"
        )
    return result


def fractions(values: Iterable[float]) -> tuple[tuple[float, ...], float]:
    raw = vector(values, "mass_fraction")
    total = fsum(raw)
    if not raw or any(v < 0 for v in raw) or abs(total - 1.0) > FRACTION_TOLERANCE:
        raise DomainValidationError("Nonnegative mass fractions must sum to 1 (tolerance 1e-8)")
    return tuple(v / total for v in raw), total
