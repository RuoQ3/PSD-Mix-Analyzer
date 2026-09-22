"""Task 3 acceptance tests: union grid + mass-only mixing, independent of batch metadata."""

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from psd_analyzer.domain.exceptions import BasisMismatchError, CoverageError, DomainValidationError
from psd_analyzer.domain.models.analysis_profile import TailPolicy
from psd_analyzer.domain.models.analysis_result import EvaluatedCurve
from psd_analyzer.domain.models.psd import PSD, DistributionBasis
from psd_analyzer.domain.services.grid import ParticleSizeGridBuilder
from psd_analyzer.domain.services.interpolation import (
    LinearInterpolator,
    LogLinearInterpolator,
    LogSizeLinearInterpolator,
)
from psd_analyzer.domain.services.psd_mixing import PSDMixingService, _correct_roundoff
from psd_analyzer.domain.validation import CUMULATIVE_ROUNDOFF_TOLERANCE, fractions


@pytest.fixture
def source():
    return PSD((10.0, 100.0, 1000.0), (0.2, 0.6, 1.0))


@pytest.mark.parametrize("strategy", [LinearInterpolator(), LogSizeLinearInterpolator()])
def test_01_single_material_identity_and_new_object(source, strategy):
    result = PSDMixingService().mix((source,), (1.0,), strategy)
    assert isinstance(result, PSD)
    assert result == source
    assert result is not source


def test_02_identical_psds(source):
    result = PSDMixingService().mix((source, source), (0.3, 0.7), LinearInterpolator())
    assert result.particle_size_um == source.particle_size_um
    assert result.cumulative_passing == pytest.approx(source.cumulative_passing)


def test_03_hand_calculated_p100_is_point_48(source):
    b = PSD((10, 100, 1000), (0, 0.4, 1))
    result = PSDMixingService().mix((source, b), (0.4, 0.6), LinearInterpolator())
    assert result.cumulative_passing == pytest.approx((0.08, 0.48, 1))
    assert result.cumulative_passing[result.particle_size_um.index(100)] == pytest.approx(0.48)


def test_04_union_grid_and_different_node_mixture(source):
    b = PSD((20, 200, 2000), (0.1, 0.5, 0.9))
    expected_grid = (10, 20, 100, 200, 1000, 2000)
    assert ParticleSizeGridBuilder().build((source, b)) == expected_grid
    result = PSDMixingService().mix((source, b), (0.4, 0.6), LinearInterpolator())
    assert result.particle_size_um == expected_grid
    # At D=100: A=.6, B=.1 + (80/180)*.4.
    assert result.cumulative_passing[2] == pytest.approx(0.4 * 0.6 + 0.6 * (0.1 + 80 / 180 * 0.4))
    assert result.cumulative_passing[0] == pytest.approx(0.4 * 0.2 + 0.6 * 0.1)
    assert result.cumulative_passing[-1] == pytest.approx(0.4 * 1 + 0.6 * 0.9)


def test_05_linear_manual_midpoint():
    source = PSD((10, 100), (0.2, 0.8))
    curve = LinearInterpolator().interpolate(source, (10, 55, 100), TailPolicy.CLAMP)
    assert curve.cumulative_passing == pytest.approx((0.2, 0.5, 0.8))


def test_06_log_size_manual_midpoint():
    source = PSD((10, 1000), (0.2, 0.8))
    curve = LogSizeLinearInterpolator().interpolate(source, (10, 100, 1000), TailPolicy.CLAMP)
    assert curve.cumulative_passing == pytest.approx((0.2, 0.5, 0.8))
    linear = LinearInterpolator().interpolate(source, (100,), TailPolicy.CLAMP)
    assert linear.cumulative_passing[0] == pytest.approx(0.2 + 90 / 990 * 0.6)
    assert LogSizeLinearInterpolator is LogLinearInterpolator  # alias, not a duplicate strategy


@pytest.mark.parametrize(
    "weights",
    [
        (0.4, 0.3, 0.2),
        (-0.1, 0.4, 0.7),
        (0, 0, 0),
        (float("nan"), 0, 1),
        (float("inf"), 0, 1),
        (1e308, 1e308, 1e308),
    ],
)
def test_07_08_invalid_weights_are_domain_errors(source, weights):
    with pytest.raises(DomainValidationError):
        PSDMixingService().mix((source, source, source), weights, LinearInterpolator())


@pytest.mark.parametrize(
    "grid,passing",
    [
        ((), ()),
        ((10,), (0.2,)),
        ((10, 100, 1000), (0.2, 0.7, 0.6)),
        ((10, 10, 100), (0.1, 0.2, 1)),
        ((0, 10), (0, 1)),
        ((-1, 10), (0, 1)),
        ((100, 10), (0.2, 0.8)),
        ((10, 100), (0.2,)),
        ((10, 100), (-0.1, 1)),
        ((10, 100), (0, 1.1)),
        ((10, float("nan")), (0, 1)),
        ((10, float("inf")), (0, 1)),
        ((10, 100), (0, float("nan"))),
        ((10, 100), (0, float("inf"))),
        (None, (0, 1)),
        ((10, 100), None),
    ],
)
def test_09_10_11_source_validation_precedes_interpolation(grid, passing):
    with pytest.raises(DomainValidationError):
        PSD(grid, passing)


@pytest.mark.parametrize("strategy", [LinearInterpolator(), LogSizeLinearInterpolator()])
def test_12_clamp_uses_actual_endpoints_not_zero_one(strategy):
    source = PSD((10, 100), (0.2, 0.8))
    curve = strategy.interpolate(source, (1, 10, 100, 1000), TailPolicy.CLAMP)
    assert curve.cumulative_passing == (0.2, 0.2, 0.8, 0.8)


def test_13_float_weights_and_small_sum_roundoff(source):
    result = PSDMixingService().mix((source, source, source), (0.1, 0.2, 0.7), LinearInterpolator())
    assert result.cumulative_passing == pytest.approx(source.cumulative_passing)
    # Existing 1e-8 policy is preserved, not broad normalization of bad recipes.
    result = PSDMixingService().mix((source, source), (0.5, 0.500000001), LinearInterpolator())
    assert result.cumulative_passing == pytest.approx(source.cumulative_passing)
    with pytest.raises(DomainValidationError):
        PSDMixingService().mix((source, source), (0.5, 0.500001), LinearInterpolator())


@pytest.mark.parametrize("strategy", [LinearInterpolator(), LogSizeLinearInterpolator()])
def test_14_output_monotonic_range_and_typical_scale(strategy):
    rng = np.random.default_rng(43)
    psds = []
    for i in range(30):
        grid = np.geomspace(1 + i * 0.1, 1000 + i * 10, 500)
        passing = np.cumsum(rng.uniform(0.001, 1, len(grid)))
        passing /= passing[-1]
        psds.append(PSD(tuple(grid), tuple(passing)))
    result = PSDMixingService().mix(psds, (1 / 30,) * 30, strategy)
    assert len(result.particle_size_um) <= 15000
    assert np.all(np.diff(result.particle_size_um) > 0)
    assert np.all(np.diff(result.cumulative_passing) >= 0)
    assert all(0 <= p <= 1 for p in result.cumulative_passing)


def test_zero_weight_has_no_effect_but_retains_union_nodes(source):
    zero = PSD((1, 20, 2000), (0.1, 0.4, 0.8))
    result = PSDMixingService().mix((source, zero), (1, 0), LinearInterpolator())
    assert result.particle_size_um == (1, 10, 20, 100, 1000, 2000)
    expected = LinearInterpolator().interpolate(source, result.particle_size_um, TailPolicy.CLAMP)
    assert result.cumulative_passing == expected.cumulative_passing


def test_input_and_result_are_immutable(source):
    snapshot = source
    result = PSDMixingService().mix((source,), (1,), LinearInterpolator())
    assert source == snapshot
    with pytest.raises(FrozenInstanceError):
        result.cumulative_passing = (0.3, 0.7, 1)


def test_mass_service_rejects_other_bases_even_at_zero_weight(source):
    for basis in (DistributionBasis.VOLUME, DistributionBasis.NUMBER, DistributionBasis.UNKNOWN):
        with pytest.raises(BasisMismatchError):
            PSDMixingService().mix((replace(source, basis=basis),), (1,), LinearInterpolator())
        with pytest.raises(BasisMismatchError):
            PSDMixingService().mix(
                (source, replace(source, basis=basis)), (1, 0), LinearInterpolator()
            )


def test_grid_deduplicates_between_sources_only(source):
    assert ParticleSizeGridBuilder().build((source, source)) == source.particle_size_um
    with pytest.raises(DomainValidationError):
        ParticleSizeGridBuilder().build(())
    with pytest.raises(DomainValidationError):
        ParticleSizeGridBuilder().build(("not a PSD",))


@pytest.mark.parametrize("psds,weights", [((), ()), (("bad",), (1,))])
def test_invalid_service_inputs(psds, weights):
    with pytest.raises(DomainValidationError):
        PSDMixingService().mix(psds, weights, LinearInterpolator())


def test_component_weight_lengths_and_boundary_value_are_validated(source):
    with pytest.raises(DomainValidationError):
        PSDMixingService().mix((source, source), (1,), LinearInterpolator())
    with pytest.raises(DomainValidationError):
        PSDMixingService(tail_policy="clamp")


def test_error_policy_and_partial_coverage_rules(source):
    for strategy in (LinearInterpolator(), LogSizeLinearInterpolator()):
        assert strategy.interpolate(source, (10, 1000), TailPolicy.ERROR).complete
        with pytest.raises(CoverageError):
            strategy.interpolate(source, (1, 10000), TailPolicy.ERROR)
    other = PSD((20, 2000), (0.1, 0.9))
    for policy in (TailPolicy.STRICT, TailPolicy.CONFIRMED, TailPolicy.ERROR):
        with pytest.raises(CoverageError):
            PSDMixingService(tail_policy=policy).mix(
                (source, other), (0.5, 0.5), LinearInterpolator()
            )


def test_tail_flags_are_preserved_only_with_physical_confirmation():
    a = PSD((10, 100), (0, 1), lower_tail_confirmed=True, upper_tail_confirmed=True)
    b = PSD((20, 200), (0, 1), lower_tail_confirmed=True, upper_tail_confirmed=True)
    result = PSDMixingService(tail_policy=TailPolicy.CONFIRMED).mix(
        (a, b), (0.5, 0.5), LinearInterpolator()
    )
    assert result.lower_tail_confirmed and result.upper_tail_confirmed
    unconfirmed = replace(b, lower_tail_confirmed=False, upper_tail_confirmed=False)
    result = PSDMixingService().mix((a, unconfirmed), (0.5, 0.5), LinearInterpolator())
    assert not result.lower_tail_confirmed and not result.upper_tail_confirmed


def test_grid_and_interpolator_are_injected(source):
    calls = []

    class ExplicitGrid:
        def build(self, psds):
            calls.append(("grid", len(psds)))
            return (10, 55, 100, 1000)

    class RecordingLinear:
        method_id = "recording"

        def interpolate(self, psd, particle_size_um, tail_policy):
            calls.append(("interpolate", tuple(particle_size_um), tail_policy))
            return LinearInterpolator().interpolate(psd, particle_size_um, tail_policy)

    result = PSDMixingService(grid_builder=ExplicitGrid()).mix((source,), (1,), RecordingLinear())
    assert result.particle_size_um == (10, 55, 100, 1000)
    assert calls == [("grid", 1), ("interpolate", (10, 55, 100, 1000), TailPolicy.CLAMP)]


def test_invalid_fractions_stop_before_grid_or_interpolation(source):
    class NeverCalled:
        def build(self, psds):
            raise AssertionError("grid should not run")

    with pytest.raises(DomainValidationError):
        PSDMixingService(grid_builder=NeverCalled()).mix((source,), (0.9,), LinearInterpolator())


@pytest.mark.parametrize("grid", [(0, 10), (10, 10), (100, 10), (10,), ()])
def test_invalid_custom_grid_is_rejected(source, grid):
    class InvalidGrid:
        def build(self, psds):
            return grid

    with pytest.raises(DomainValidationError):
        PSDMixingService(grid_builder=InvalidGrid()).mix((source,), (1,), LinearInterpolator())


def test_numpy_style_errors_do_not_escape(source, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("numpy implementation detail")

    monkeypatch.setattr("psd_analyzer.domain.services.interpolation.np.interp", fail)
    with pytest.raises(DomainValidationError, match="interpolation failed"):
        LinearInterpolator().interpolate(source, (10, 100))

    class BadStrategy:
        method_id = "bad"
        interpolate = fail

    with pytest.raises(DomainValidationError, match="strategy failed"):
        PSDMixingService().mix((source,), (1,), BadStrategy())

    class BadGrid:
        build = fail

    with pytest.raises(DomainValidationError, match="grid construction failed"):
        PSDMixingService(grid_builder=BadGrid()).mix((source,), (1,), LinearInterpolator())


def test_wrong_interpolator_output_cannot_be_accepted(source):
    class BadBasis:
        method_id = "bad"

        def interpolate(self, psd, grid, tail_policy):
            return EvaluatedCurve(grid, psd.cumulative_passing, DistributionBasis.VOLUME)

    with pytest.raises(BasisMismatchError):
        PSDMixingService().mix((source,), (1,), BadBasis())

    class BadType:
        method_id = "bad"

        def interpolate(self, *args):
            return np.array([0, 0.5, 1])

    with pytest.raises(DomainValidationError):
        PSDMixingService().mix((source,), (1,), BadType())


def test_interpolation_validates_source_and_positive_targets(source):
    with pytest.raises(DomainValidationError):
        LinearInterpolator().interpolate("invalid", (10, 100))
    for grid in [(0, 10), (-1, 10), (10, 10), (10, float("nan")), (10, float("inf"))]:
        with pytest.raises(DomainValidationError):
            LogSizeLinearInterpolator().interpolate(source, grid, TailPolicy.CLAMP)


def test_log_nodes_that_collapse_in_floating_point_are_rejected():
    first = 1e100
    source = PSD((first, np.nextafter(first, np.inf)), (0, 1))
    with pytest.raises(DomainValidationError, match="log space"):
        LogSizeLinearInterpolator().interpolate(source, source.particle_size_um)


def test_roundoff_correction_is_bounded_and_never_hides_real_violations():
    eps = CUMULATIVE_ROUNDOFF_TOLERANCE
    result = _correct_roundoff(np.array([-eps / 4, 0.5, 0.5 - eps / 4, 1 + eps / 4]))
    assert tuple(result) == (0, 0.5, 0.5, 1)
    for values in (
        [-2 * eps, 0.5],
        [0.5, 1 + 2 * eps],
        [0.5, 0.5 - 2 * eps],
        [float("nan")],
        [float("inf")],
    ):
        with pytest.raises(DomainValidationError):
            _correct_roundoff(np.array(values))
    # Several individually small decreases must not cumulatively exceed tolerance.
    with pytest.raises(DomainValidationError):
        _correct_roundoff(np.array([0.5, 0.5 - 0.6 * eps, 0.5 - 1.2 * eps]))


def test_non_sequence_weights_are_domain_error():
    with pytest.raises(DomainValidationError):
        fractions(None)


def test_nested_arrays_and_non_sequence_sources_raise_domain_errors():
    with pytest.raises(DomainValidationError, match="scalar"):
        PSD(np.array([[10.0], [100.0]]), (0, 1))
    with pytest.raises(DomainValidationError, match="sequence"):
        PSDMixingService().mix(None, (1,), LinearInterpolator())
