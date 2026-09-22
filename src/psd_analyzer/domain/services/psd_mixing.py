"""Metadata-free cumulative mixing: PSDs, fractions, a grid builder and interpolation.

The public service supports MASS only. The private grid kernel is also reused by
an existing adapter whose already-resolved weights can represent another basis.
Neither the service nor the kernel reads batches, density or supplier information.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from ..exceptions import BasisMismatchError, CoverageError, DomainValidationError
from ..models.analysis_profile import TailPolicy
from ..models.analysis_result import EvaluatedCurve
from ..models.psd import PSD, DistributionBasis
from ..protocols import PSDGridBuilder, PSDInterpolator
from ..validation import CUMULATIVE_ROUNDOFF_TOLERANCE, fractions, sizes
from .grid import ParticleSizeGridBuilder


def _correct_roundoff(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Reject numerical violations first; repair only bounded machine-scale roundoff."""
    tolerance = CUMULATIVE_ROUNDOFF_TOLERANCE
    if not np.all(np.isfinite(values)):
        raise DomainValidationError("Mixed cumulative values must be finite")
    if np.any(values < -tolerance) or np.any(values > 1.0 + tolerance):
        raise DomainValidationError("Mixed cumulative values exceed [0, 1] beyond roundoff")
    corrected = values.copy()
    corrected[corrected < 0.0] = 0.0
    corrected[corrected > 1.0] = 1.0
    if corrected.size:
        monotone = np.maximum.accumulate(corrected)
        if np.any(monotone - corrected > tolerance):
            raise DomainValidationError("Mixed cumulative values decrease beyond roundoff")
        corrected = monotone
    return corrected


def _mix_on_grid(
    psds: Sequence[PSD],
    weights: Sequence[float],
    grid: tuple[float, ...],
    *,
    basis: DistributionBasis,
    interpolator: PSDInterpolator,
    tail_policy: TailPolicy,
) -> EvaluatedCurve:
    """Single weighted-sum implementation; callers validate/resolve weights and basis.

    O(N * G) matrix arithmetic. Only interpolation dispatch loops over components;
    missing nodes in any positive-weight source propagate to the output.
    """
    if len(psds) != len(weights) or not psds:
        raise DomainValidationError("One weight is required for each PSD")
    curves: list[EvaluatedCurve] = []
    active_weights: list[float] = []
    for psd, weight in zip(psds, weights, strict=True):
        if weight == 0:
            continue
        try:
            curve = interpolator.interpolate(psd, grid, tail_policy)
        except DomainValidationError:
            raise
        except (ValueError, TypeError, FloatingPointError) as exc:
            raise DomainValidationError("Interpolation strategy failed during mixing") from exc
        if not isinstance(curve, EvaluatedCurve) or curve.particle_size_um != grid:
            raise DomainValidationError(
                "Interpolator must return an EvaluatedCurve on the given grid"
            )
        if curve.basis != psd.basis:
            raise BasisMismatchError("Interpolation cannot change the source distribution basis")
        curves.append(curve)
        active_weights.append(weight)
    if not curves:
        raise DomainValidationError("At least one positive fraction is required")
    matrix = np.asarray([curve.cumulative_passing for curve in curves], dtype=np.float64)
    covered = np.all(np.isfinite(matrix), axis=0)
    # Missing nodes are masked before multiplication; they remain None in the domain result.
    try:
        with np.errstate(invalid="raise", over="raise"):
            values = np.asarray(active_weights) @ np.where(covered, matrix, 0.0)
    except (ValueError, TypeError, FloatingPointError) as exc:
        raise DomainValidationError("Weighted PSD calculation failed") from exc
    values[covered] = _correct_roundoff(values[covered])
    passing = tuple(
        float(value) if valid else None for value, valid in zip(values, covered, strict=True)
    )
    return EvaluatedCurve(grid, passing, basis)


@dataclass(frozen=True)
class PSDMixingService:
    """Mix validated MASS PSDs onto their union grid, using clamp by default.

    `mix(psds, mass_fractions, interpolator)` returns a new immutable PSD. No
    MaterialBatch, recipe ID, density, q, I/O or presentation object is required.
    Fractions are checked before grid construction; only sum deviations within
    the existing central fraction tolerance are normalized, never an invalid recipe.
    Zero-weight PSDs are validated and included in the union, but do not contribute
    values or missing coverage. STRICT/CONFIRMED require full coverage to return PSD.
    """

    grid_builder: PSDGridBuilder = field(default_factory=ParticleSizeGridBuilder)
    tail_policy: TailPolicy = TailPolicy.CLAMP

    def __post_init__(self) -> None:
        if not isinstance(self.tail_policy, TailPolicy):
            raise DomainValidationError("Unknown mixing boundary policy")

    def mix(
        self,
        psds: Sequence[PSD],
        mass_fractions: Sequence[float],
        interpolator: PSDInterpolator,
    ) -> PSD:
        try:
            sources = tuple(psds)
        except TypeError as exc:
            raise DomainValidationError("Mixing requires a sequence of PSD objects") from exc
        if not sources or any(not isinstance(psd, PSD) for psd in sources):
            raise DomainValidationError("Mixing requires at least one validated PSD")
        weights, _ = fractions(mass_fractions)
        if len(sources) != len(weights):
            raise DomainValidationError("One mass fraction is required for each PSD")
        if any(psd.basis != DistributionBasis.MASS for psd in sources):
            raise BasisMismatchError(
                "PSDMixingService requires MASS distributions; no density conversion"
            )
        try:
            grid = sizes(self.grid_builder.build(sources), minimum_count=2)
        except DomainValidationError:
            raise
        except (ValueError, TypeError, FloatingPointError) as exc:
            raise DomainValidationError("Particle size grid construction failed") from exc
        mixed = _mix_on_grid(
            sources,
            weights,
            grid,
            basis=DistributionBasis.MASS,
            interpolator=interpolator,
            tail_policy=self.tail_policy,
        )
        if not mixed.complete:
            raise CoverageError("Cannot return a complete PSD with unsupported interpolation nodes")
        passing = tuple(value for value in mixed.cumulative_passing if value is not None)
        active = tuple(psd for psd, w in zip(sources, weights, strict=True) if w > 0)
        # Clamp is a numerical convention, not confirmation of unknown physical tails.
        lower_confirmed = passing[0] == 0.0 and all(p.lower_tail_confirmed for p in active)
        upper_confirmed = passing[-1] == 1.0 and all(p.upper_tail_confirmed for p in active)
        return PSD(grid, passing, DistributionBasis.MASS, lower_confirmed, upper_confirmed)
