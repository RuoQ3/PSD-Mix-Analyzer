"""Interpolation leaves unsupported tails missing instead of fabricating data."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..exceptions import DomainValidationError
from ..models.analysis_profile import InterpolationMethod, TailPolicy
from ..models.analysis_result import EvaluatedCurve
from ..models.psd import PSD
from ..protocols import PSDInterpolator
from ..validation import sizes


def _interpolate(
    psd: PSD, requested: Sequence[float], policy: TailPolicy, *, logarithmic: bool
) -> EvaluatedCurve:
    grid = sizes(requested)
    if not isinstance(policy, TailPolicy):
        raise DomainValidationError("Unknown tail policy")
    x, p = np.asarray(psd.particle_size_um), np.asarray(psd.cumulative_passing)
    transform = np.log if logarithmic else np.asarray
    values = np.interp(transform(grid), transform(x), p)
    result: list[float | None] = []
    for d, value in zip(grid, values, strict=True):
        if d < x[0]:
            result.append(
                0.0 if policy == TailPolicy.CONFIRMED and psd.lower_tail_confirmed else None
            )
        elif d > x[-1]:
            result.append(
                1.0 if policy == TailPolicy.CONFIRMED and psd.upper_tail_confirmed else None
            )
        else:
            result.append(float(value))
    return EvaluatedCurve(grid, tuple(result), psd.basis)


@dataclass(frozen=True)
class LinearInterpolator:
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
    method_id: str = "log-linear"

    def interpolate(
        self,
        psd: PSD,
        particle_size_um: Sequence[float],
        tail_policy: TailPolicy = TailPolicy.CONFIRMED,
    ) -> EvaluatedCurve:
        return _interpolate(psd, particle_size_um, tail_policy, logarithmic=True)


def get_interpolator(method: InterpolationMethod) -> PSDInterpolator:
    if method == InterpolationMethod.LINEAR:
        return LinearInterpolator()
    if method == InterpolationMethod.LOG_LINEAR:
        return LogLinearInterpolator()
    raise DomainValidationError("Unknown interpolation method")
