"""Separate distribution-basis assumptions from the weighted sum."""

from collections.abc import Sequence
from math import fsum, isfinite

from ..exceptions import BasisMismatchError, DomainValidationError
from ..models.analysis_result import Diagnostic
from ..models.material import DensityKind
from ..models.psd import DistributionBasis
from ..models.recipe import MixtureComponent
from ..validation import fractions, positive


def mass_to_volume_fractions(
    mass_fractions: Sequence[float], densities_kg_m3: Sequence[float]
) -> tuple[float, ...]:
    weights, _ = fractions(mass_fractions)
    if len(weights) != len(densities_kg_m3):
        raise DomainValidationError("One density is required per fraction")
    densities = tuple(positive(d, "density_kg_m3") for d in densities_kg_m3)
    volumes = tuple(w / d for w, d in zip(weights, densities, strict=True))
    total = fsum(volumes)
    if not isfinite(total) or total <= 0:
        raise DomainValidationError("Density conversion exceeds numerical range")
    return tuple(v / total for v in volumes)


def resolve_weights(
    components: Sequence[MixtureComponent], target: DistributionBasis
) -> tuple[tuple[float, ...], float, tuple[Diagnostic, ...]]:
    if target not in (DistributionBasis.MASS, DistributionBasis.VOLUME):
        raise BasisMismatchError("Target basis must be mass or volume")
    weights, original_sum = fractions(c.mass_fraction for c in components)
    diagnostics: list[Diagnostic] = []
    densities: list[float] = []
    for component, weight in zip(components, weights, strict=True):
        if weight == 0:
            densities.append(1.0)  # zero contributes neither mass nor volume
            continue
        basis = component.measurement.psd.basis
        if basis not in (DistributionBasis.MASS, DistributionBasis.VOLUME):
            raise BasisMismatchError(f"{component.line_id}: unsupported PSD basis {basis}")
        if basis != target:
            if not component.uniform_density_confirmed:
                raise BasisMismatchError(
                    f"{component.line_id}: mass/volume conversion requires uniform particle density"
                )
            diagnostics.append(
                Diagnostic(
                    "UNIFORM_DENSITY_ASSUMPTION",
                    f"{component.line_id}: particle density assumed independent of size",
                )
            )
        if target == DistributionBasis.VOLUME:
            batch = component.batch
            if batch.density_kg_m3 is None or batch.density_kind not in (
                DensityKind.PARTICLE,
                DensityKind.TRUE,
            ):
                raise BasisMismatchError(
                    f"{component.line_id}: particle-compatible density required, bulk not accepted"
                )
            densities.append(batch.density_kg_m3)
    if original_sum != 1.0:
        diagnostics.append(
            Diagnostic(
                "FRACTIONS_NORMALIZED", f"Input sum {original_sum!r} normalized within tolerance"
            )
        )
    if target == DistributionBasis.VOLUME:
        weights = mass_to_volume_fractions(weights, densities)
    return weights, original_sum, tuple(diagnostics)
