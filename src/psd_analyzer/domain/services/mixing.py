"""Pure interpolation and weighted mixing with explicit coverage masks."""

from collections.abc import Sequence
from math import fsum

from ..exceptions import DomainValidationError
from ..models.analysis_profile import TailPolicy
from ..models.analysis_result import EvaluatedCurve
from ..models.psd import DistributionBasis
from ..models.recipe import MixtureComponent
from ..protocols import PSDInterpolator
from ..validation import sizes
from .basis_conversion import resolve_weights


def mix_psd(
    components: Sequence[MixtureComponent],
    particle_size_um: Sequence[float],
    *,
    target_basis: DistributionBasis,
    interpolator: PSDInterpolator,
    tail_policy: TailPolicy = TailPolicy.CONFIRMED,
) -> EvaluatedCurve:
    grid = sizes(particle_size_um)
    if len({c.line_id for c in components}) != len(components):
        raise DomainValidationError("Mixture line IDs must be unique")
    weights, _, _ = resolve_weights(components, target_basis)
    curves = [
        (weight, interpolator.interpolate(c.measurement.psd, grid, tail_policy))
        for c, weight in zip(components, weights, strict=True)
        if weight > 0
    ]
    for _, curve in curves:
        if curve.particle_size_um != grid or len(curve.cumulative_passing) != len(grid):
            raise DomainValidationError("Interpolator returned a mismatched grid")
    mixed: list[float | None] = []
    for index in range(len(grid)):
        values = [(weight, curve.cumulative_passing[index]) for weight, curve in curves]
        if any(value is None for _, value in values):
            mixed.append(None)
        else:
            value = fsum(weight * value for weight, value in values if value is not None)
            mixed.append(min(1.0, max(0.0, value)))  # round-off only; inputs already validated
    return EvaluatedCurve(grid, tuple(mixed), target_basis)
