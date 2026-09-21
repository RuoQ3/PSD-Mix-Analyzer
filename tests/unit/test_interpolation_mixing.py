from dataclasses import replace

import pytest

from psd_analyzer.domain.exceptions import BasisMismatchError, DomainValidationError
from psd_analyzer.domain.models.analysis_profile import InterpolationMethod, TailPolicy
from psd_analyzer.domain.models.material import DensityKind
from psd_analyzer.domain.models.psd import PSD, DistributionBasis
from psd_analyzer.domain.services.basis_conversion import mass_to_volume_fractions, resolve_weights
from psd_analyzer.domain.services.interpolation import (
    LinearInterpolator,
    LogLinearInterpolator,
    get_interpolator,
)
from psd_analyzer.domain.services.mixing import mix_psd


@pytest.mark.parametrize(
    "strategy,query,expected",
    [
        (LinearInterpolator(), (1, 5.5, 10), (0, 0.5, 1)),
        (LogLinearInterpolator(), (1, 10, 100), (0, 0.5, 1)),
    ],
)
def test_hand_calculated_interpolation(strategy, query, expected):
    psd = PSD((query[0], query[-1]), (0, 1))
    assert strategy.interpolate(psd, query).cumulative_passing == pytest.approx(expected)


def test_missing_tails_and_explicit_confirmation():
    strict = PSD((10, 100), (0.1, 0.9))
    assert LinearInterpolator().interpolate(strict, (1, 10, 100, 1000)).cumulative_passing == (
        None,
        0.1,
        0.9,
        None,
    )
    known = PSD((10, 100), (0, 1), lower_tail_confirmed=True, upper_tail_confirmed=True)
    assert LogLinearInterpolator().interpolate(known, (1, 10, 100, 1000)).cumulative_passing == (
        0,
        0,
        1,
        1,
    )
    assert LinearInterpolator().interpolate(
        known, (1, 1000), TailPolicy.STRICT
    ).cumulative_passing == (None, None)
    # Endpoint values alone are not evidence of confirmed physical support.
    unknown = PSD((10, 100), (0, 1))
    assert LinearInterpolator().interpolate(unknown, (1, 1000)).cumulative_passing == (None, None)
    with pytest.raises(DomainValidationError):
        LinearInterpolator().interpolate(known, (1,), "other")


def test_strategy_selection():
    assert get_interpolator(InterpolationMethod.LINEAR).method_id == "linear"
    assert get_interpolator(InterpolationMethod.LOG_LINEAR).method_id == "log-linear"
    with pytest.raises(DomainValidationError):
        get_interpolator("cubic")


def mix(components, grid=(1, 10, 100), basis=DistributionBasis.MASS):
    return mix_psd(components, grid, target_basis=basis, interpolator=LogLinearInterpolator())


def test_single_material_identity(component):
    c = component(passing=(0.1, 0.4, 0.9))
    assert mix((c,)).cumulative_passing == c.measurement.psd.cumulative_passing


@pytest.mark.parametrize("w", [0, 0.1, 0.333, 0.8, 1])
def test_identical_materials_any_weights(component, w):
    a = component(weight=w)
    b = component(line="B", weight=1 - w)
    assert mix((a, b)).cumulative_passing == pytest.approx((0, 0.5, 1))


def test_hand_calculated_different_nodes(component):
    a = component(passing=(0, 1), grid=(1, 100), weight=0.25)
    b = component(passing=(0, 0.8, 1), weight=0.75, line="B")
    result = mix((a, b), (1, 10, 100))
    assert result.cumulative_passing == pytest.approx((0, 0.725, 1))
    assert result.complete


def test_positive_weight_missing_data_propagates(component):
    a = component(weight=0.5)
    b = component(grid=(10, 100), passing=(0.2, 0.8), weight=0.5, line="B")
    assert mix((a, b)).cumulative_passing == (None, 0.35, 0.9)
    # Unknown curve at zero fraction has no influence.
    assert mix((replace(a, mass_fraction=1), replace(b, mass_fraction=0))).complete


def test_mix_rejects_invalid_sum_and_duplicate(component):
    with pytest.raises(DomainValidationError):
        mix((component(weight=0.9),))
    with pytest.raises(DomainValidationError):
        mix((component(weight=0.5), component(weight=0.5)))
    with pytest.raises(DomainValidationError):
        mix(())


def test_mass_to_volume_hand_calculation():
    assert mass_to_volume_fractions((0.5, 0.5), (2000, 4000)) == pytest.approx((2 / 3, 1 / 3))
    with pytest.raises(DomainValidationError):
        mass_to_volume_fractions((0.5, 0.5), (2000,))
    with pytest.raises(DomainValidationError):
        mass_to_volume_fractions((1,), (-1,))


def test_volume_mixture_uses_density_weights(component):
    a = component(
        passing=(0, 0.2, 1),
        weight=0.5,
        density=2000,
        density_kind=DensityKind.PARTICLE,
        basis=DistributionBasis.VOLUME,
    )
    b = component(
        passing=(0, 0.8, 1),
        line="B",
        weight=0.5,
        density=4000,
        density_kind=DensityKind.TRUE,
        basis=DistributionBasis.VOLUME,
    )
    assert mix((a, b), basis=DistributionBasis.VOLUME).cumulative_passing == pytest.approx(
        (0, 0.4, 1)
    )
    with pytest.raises(BasisMismatchError):
        mix((a, b))
    approved = (
        replace(a, uniform_density_confirmed=True),
        replace(b, uniform_density_confirmed=True),
    )
    assert mix(approved).cumulative_passing == pytest.approx((0, 0.5, 1))
    assert len(resolve_weights(approved, DistributionBasis.MASS)[2]) == 2


@pytest.mark.parametrize("density,kind", [(None, None), (1000, DensityKind.BULK)])
def test_volume_requires_particle_compatible_density(component, density, kind):
    c = component(density=density, density_kind=kind, basis=DistributionBasis.VOLUME)
    with pytest.raises(BasisMismatchError):
        mix((c,), basis=DistributionBasis.VOLUME)


@pytest.mark.parametrize("basis", [DistributionBasis.UNKNOWN, DistributionBasis.NUMBER])
def test_unsupported_bases(component, basis):
    with pytest.raises(BasisMismatchError):
        mix((component(basis=basis),))
    with pytest.raises(BasisMismatchError):
        resolve_weights((component(),), basis)


def test_mass_curve_to_volume_and_normalization(component):
    c = component(density=2000, density_kind=DensityKind.TRUE, uniform=True)
    assert mix((c,), basis=DistributionBasis.VOLUME).complete
    a = component(weight=0.5)
    b = component(line="B", weight=0.500000001)
    _, total, diagnostics = resolve_weights((a, b), DistributionBasis.MASS)
    assert total == 1.000000001
    assert diagnostics[0].code == "FRACTIONS_NORMALIZED"


def test_bad_interpolator_contract(component):
    class Bad:
        method_id = "bad"

        def interpolate(self, psd, grid, tail_policy):
            return replace(
                LogLinearInterpolator().interpolate(psd, grid, tail_policy),
                cumulative_passing=(0, float("nan"), 1),
            )

    with pytest.raises(DomainValidationError):
        mix_psd(
            (component(),), (1, 10, 100), target_basis=DistributionBasis.MASS, interpolator=Bad()
        )

    class WrongGrid(Bad):
        def interpolate(self, psd, grid, tail_policy):
            return replace(
                LogLinearInterpolator().interpolate(psd, grid, tail_policy),
                particle_size_um=(1, 2, 3),
            )

    with pytest.raises(DomainValidationError):
        mix_psd(
            (component(),),
            (1, 10, 100),
            target_basis=DistributionBasis.MASS,
            interpolator=WrongGrid(),
        )
