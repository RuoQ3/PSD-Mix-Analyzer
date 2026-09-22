from dataclasses import replace

import pytest

from psd_analyzer.domain.exceptions import DomainValidationError, IncompatibleComparisonError
from psd_analyzer.domain.models.analysis_profile import InterpolationMethod
from psd_analyzer.domain.models.analysis_result import FitStatus
from psd_analyzer.domain.models.psd import DistributionBasis
from psd_analyzer.domain.services.analysis import analyze_mixture
from psd_analyzer.domain.services.comparison import compare_results
from psd_analyzer.domain.services.grid import build_grid
from psd_analyzer.domain.services.packing_models import ModifiedAndreasen


def generated(component, profile, q, **kwargs):
    grid = build_grid(profile)
    passing = ModifiedAndreasen().evaluate_q(
        grid, q=q, d_min_um=profile.d_min_um, d_max_um=profile.d_max_um
    )
    return component(passing=passing, grid=grid, **kwargs)


def test_full_analysis_and_target_separation(component, profile):
    c = generated(component, profile, 0.37)
    result = analyze_mixture((c,), profile)
    assert result.fit.equivalent_q == pytest.approx(0.37, abs=1e-6)
    assert result.fit_metrics.rmse < 1e-8
    assert result.target_metrics.rmse > 0.001
    assert result.key_passing[-1].cumulative_passing is None
    assert result.key_passing[-1].reason == "outside_supported_coverage"
    assert result.actual_weights == (1,)
    assert result.profile is profile and result.components == (c,)


def test_no_target_q(component, profile):
    result = analyze_mixture((component(),), replace(profile, target_q=None))
    assert result.target_curve is None and result.target_metrics is None


def test_incomplete_analysis_retains_partial_psd(component, profile):
    result = analyze_mixture((component(grid=(10, 100), passing=(0.2, 0.9)),), profile)
    assert result.fit.status == FitStatus.INSUFFICIENT_COVERAGE
    assert result.fit.equivalent_q is None
    assert result.mixed_curve.cumulative_passing[0] is None
    assert result.mixed_curve.cumulative_passing[-1] == 0.9
    assert result.target_curve is not None and result.target_metrics is None


def test_substitution_comparison_hand_calculation(component, profile):
    # Identical recipe weights; replacement changes PSD only.
    base = analyze_mixture((component(passing=(0, 0.3, 1)),), profile)
    current = analyze_mixture(
        (component(passing=(0, 0.6, 1), material="domestic", batch_id="new"),), profile
    )
    difference = compare_results(current, base)
    at10 = difference.particle_size_um.index(10.0)
    assert difference.delta_psd[at10] == pytest.approx(0.3)
    assert difference.max_absolute_deviation == pytest.approx(0.3)
    assert difference.key_delta[1].cumulative_passing == pytest.approx(0.3)
    assert difference.key_delta[-1].cumulative_passing is None


def test_successful_delta_q(component, profile):
    base = analyze_mixture((generated(component, profile, 0.3),), profile)
    current = analyze_mixture((generated(component, profile, 0.4, batch_id="new"),), profile)
    diff = compare_results(current, base)
    assert diff.delta_q == pytest.approx(0.1, abs=1e-6)


@pytest.mark.parametrize(
    "change",
    [
        {"version": "2"},
        {"d_min_um": 0.5},
        {"grid_points": 21},
        {"interpolation": InterpolationMethod.LINEAR},
        {"q_bounds": (0.05, 2)},
    ],
)
def test_comparison_requires_same_profile(component, profile, change):
    a = analyze_mixture((component(),), profile)
    b = analyze_mixture((component(),), replace(profile, **change))
    with pytest.raises(IncompatibleComparisonError):
        compare_results(a, b)


def test_comparison_rejects_changed_protocol_and_weights(component, profile):
    a = analyze_mixture((component(),), profile)
    b = analyze_mixture((component(protocol="different"),), profile)
    with pytest.raises(IncompatibleComparisonError):
        compare_results(a, b)
    b = analyze_mixture((component(weight=0.5), component(line="B", weight=0.5)), profile)
    with pytest.raises(IncompatibleComparisonError):
        compare_results(a, b)
    with pytest.raises(IncompatibleComparisonError):
        compare_results(a, replace(a, algorithm_version="2"))
    with pytest.raises(IncompatibleComparisonError):
        compare_results(
            a, replace(a, mixed_curve=replace(a.mixed_curve, basis=DistributionBasis.VOLUME))
        )


def test_incomplete_comparison_blocked_and_bound_delta_unavailable(component, profile):
    a = analyze_mixture((component(grid=(10, 100), passing=(0.2, 0.9)),), profile)
    with pytest.raises(IncompatibleComparisonError):
        compare_results(a, a)
    b = analyze_mixture((generated(component, profile, profile.q_bounds[0]),), profile)
    difference = compare_results(b, b)
    assert difference.delta_q is None
    assert difference.diagnostics[0].code == "DELTA_Q_UNAVAILABLE"


def test_component_order_does_not_change_result(component, profile):
    a = component(weight=0.4)
    b = component(line="B", weight=0.6)
    one = analyze_mixture((a, b), profile)
    two = analyze_mixture((b, a), profile)
    assert one == two


def test_non_q_model_can_supply_target(component, profile):
    class CustomTarget:
        model_id = "custom-target"

        def cumulative_passing(self, grid, *, q, d_min_um, d_max_um):
            return tuple((d - d_min_um) / (d_max_um - d_min_um) for d in grid)

    p = replace(profile, model_id="custom-target", target_q=None)
    result = analyze_mixture((component(),), p, model=CustomTarget())
    assert result.fit.status == FitStatus.NOT_APPLICABLE
    assert result.target_metrics is not None and result.fit.equivalent_q is None
    with pytest.raises(DomainValidationError):
        analyze_mixture((component(),), p)


def test_loss_can_be_replaced(component, profile):
    class MAE:
        loss_id = "mae"

        def __call__(self, observed, predicted):
            return sum(abs(a - b) for a, b in zip(observed, predicted, strict=True)) / len(observed)

    p = replace(profile, loss_id="mae")
    c = generated(component, p, 0.37)
    result = analyze_mixture((c,), p, loss=MAE())
    assert result.fit.equivalent_q == pytest.approx(0.37, abs=1e-6)


def test_mixed_measurement_protocols_require_explicit_confirmation(component, profile):
    a = component(weight=0.5)
    b = component(line="B", weight=0.5, protocol="sieve-v1")
    with pytest.raises(DomainValidationError, match="compatibility"):
        analyze_mixture((a, b), profile)
    result = analyze_mixture((a, b), replace(profile, measurement_compatibility_confirmed=True))
    assert any(d.code == "MEASUREMENT_COMPATIBILITY_ASSUMPTION" for d in result.diagnostics)
