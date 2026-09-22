"""Compatibility adapter for batch-aware analysis; numerical mixing lives in psd_mixing.

Existing callers keep their signature, explicit grid, basis resolution and coverage
semantics. The metadata-free PSDMixingService never imports or invokes this adapter.
"""

from collections.abc import Sequence

from ..exceptions import DomainValidationError
from ..models.analysis_profile import TailPolicy
from ..models.analysis_result import EvaluatedCurve
from ..models.psd import DistributionBasis
from ..models.recipe import MixtureComponent
from ..protocols import PSDInterpolator
from ..validation import sizes
from .basis_conversion import resolve_weights
from .psd_mixing import _mix_on_grid


def mix_psd(
    components: Sequence[MixtureComponent],
    particle_size_um: Sequence[float],
    *,
    target_basis: DistributionBasis,
    interpolator: PSDInterpolator,
    tail_policy: TailPolicy = TailPolicy.CONFIRMED,
) -> EvaluatedCurve:
    """Adapt existing component snapshots and resolved weights to the shared kernel."""
    grid = sizes(particle_size_um)
    if len({c.line_id for c in components}) != len(components):
        raise DomainValidationError("Mixture line IDs must be unique")
    weights, _, _ = resolve_weights(components, target_basis)
    return _mix_on_grid(
        tuple(c.measurement.psd for c in components),
        weights,
        grid,
        basis=target_basis,
        interpolator=interpolator,
        tail_policy=tail_policy,
    )
