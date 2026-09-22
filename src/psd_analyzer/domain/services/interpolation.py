"""Interpolation strategies with one explicit boundary-policy implementation."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..exceptions import CoverageError, DomainValidationError
from ..models.analysis_profile import InterpolationMethod, TailPolicy
from ..models.analysis_result import EvaluatedCurve
from ..models.psd import PSD
from ..protocols import PSDInterpolator
from ..validation import sizes


def _apply_boundary(
    values: NDArray[np.float64],
    grid: NDArray[np.float64],
    psd: PSD,
    policy: TailPolicy,
) -> NDArray[np.float64]:
    """Apply all out-of-range rules here; NaN is an internal missing-value marker only."""
    left = grid < psd.particle_size_um[0]
    right = grid > psd.particle_size_um[-1]
    outside = left | right
    if policy == TailPolicy.ERROR and np.any(outside):
        raise CoverageError("Target particle sizes extend beyond the measured PSD range")
    if policy == TailPolicy.CLAMP:
        values[left] = psd.cumulative_passing[0]
        values[right] = psd.cumulative_passing[-1]
    else:
        values[outside] = np.nan
        if policy == TailPolicy.CONFIRMED:
            if psd.lower_tail_confirmed:
                values[left] = 0.0
            if psd.upper_tail_confirmed:
                values[right] = 1.0
    return values


def _interpolate(
    psd: PSD, requested: Sequence[float], policy: TailPolicy, *, logarithmic: bool
) -> EvaluatedCurve:
    # PSD validates all source invariants at construction and stores immutable tuples.
    if not isinstance(psd, PSD):
        raise DomainValidationError("Interpolation requires a validated PSD object")
    grid = sizes(requested)
    if not isinstance(policy, TailPolicy):
        raise DomainValidationError("Unknown tail policy")
    x = np.asarray(psd.particle_size_um, dtype=np.float64)
    p = np.asarray(psd.cumulative_passing, dtype=np.float64)
    target = np.asarray(grid, dtype=np.float64)
    try:
        with np.errstate(divide="raise", invalid="raise", over="raise"):
            source_x = np.log(x) if logarithmic else x
            target_x = np.log(target) if logarithmic else target
            if np.any(np.diff(source_x) <= 0):
                raise DomainValidationError("Source sizes are not distinguishable in log space")
            values = np.interp(target_x, source_x, p)
    except DomainValidationError:
        raise
    except (ValueError, TypeError, FloatingPointError) as exc:
        raise DomainValidationError(
            "PSD interpolation failed for the supplied numeric data"
        ) from exc
    if not np.all(np.isfinite(values)):
        raise DomainValidationError("Interpolation produced nonfinite cumulative values")
    values = _apply_boundary(values, target, psd, policy)
    result = tuple(None if np.isnan(value) else float(value) for value in values)
    return EvaluatedCurve(grid, result, psd.basis)


@dataclass(frozen=True)
class LinearInterpolator:
    """Piecewise linear P(D); caller explicitly selects any out-of-range extension."""

    method_id: str = "linear"

    def interpolate(
        self,
        psd: PSD,
        particle_size_um: Sequence[float],
        tail_policy: TailPolicy = TailPolicy.CONFIRMED,
    ) -> EvaluatedCurve:
        return _interpolate(psd, particle_size_um, tail_policy, logarithmic=False)


@dataclass(frozen=True)
class LogLinearInterpolator:
    """Piecewise linear P versus natural log ln(D), never log(P); D must be positive."""

    method_id: str = "log-linear"

    def interpolate(
        self,
        psd: PSD,
        particle_size_um: Sequence[float],
        tail_policy: TailPolicy = TailPolicy.CONFIRMED,
    ) -> EvaluatedCurve:
        return _interpolate(psd, particle_size_um, tail_policy, logarithmic=True)


# Task 3 terminology, same class and implementation as the existing public name.
LogSizeLinearInterpolator = LogLinearInterpolator


def get_interpolator(method: InterpolationMethod) -> PSDInterpolator:
    if method == InterpolationMethod.LINEAR:
        return LinearInterpolator()
    if method == InterpolationMethod.LOG_LINEAR:
        return LogLinearInterpolator()
    raise DomainValidationError("Unknown interpolation method")
