"""Task 4 acceptance cases, including filter, optimizer and strategy boundaries."""

from dataclasses import replace
from math import inf, nan
from types import SimpleNamespace

import numpy as np
import pytest

from psd_analyzer.domain.exceptions import CoverageError, DomainValidationError
from psd_analyzer.domain.models.analysis_profile import AnalysisProfile, TailPolicy
from psd_analyzer.domain.models.analysis_result import EvaluatedCurve, FitStatus
from psd_analyzer.domain.models.psd import PSD, DistributionBasis
from psd_analyzer.domain.services.interpolation import LinearInterpolator, LogLinearInterpolator
from psd_analyzer.domain.services.losses import SquaredErrorLoss
from psd_analyzer.domain.services.metrics import calculate_metrics
from psd_analyzer.domain.services.packing_models import ModifiedAndreasen
from psd_analyzer.domain.services.q_fitting import fit_q
from psd_analyzer.domain.services.queries import evaluate_at_sizes


def test_target_matches_hand_formula_and_exact_endpoints():
    grid = (0.1, 1, 10, 100, 1000, 2000)
    values = ModifiedAndreasen().evaluate_q(grid, q=0.25, d_min_um=1, d_max_um=1000)
    assert values[0] == values[1] == 0
    assert values[-1] == values[-2] == 1
    assert values[2] == pytest.approx((10**0.25 - 1) / (1000**0.25 - 1))
    assert np.all(np.diff(values) >= 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"q": 0},
        {"q": -0.25},
        {"q": nan},
        {"q": inf},
        {"d_min_um": 0},
        {"d_min_um": -1},
        {"d_min_um": inf},
        {"d_max_um": 1},
        {"d_max_um": 0.5},
        {"d_max_um": nan},
        {"particle_size_um": (0, 1, 1000)},
        {"particle_size_um": (1, nan, 1000)},
    ],
)
def test_target_invalid_parameters(kwargs):
    params = dict(particle_size_um=(1, 10, 1000), q=0.25, d_min_um=1, d_max_um=1000)
    params.update(kwargs)
    with pytest.raises(DomainValidationError):
        ModifiedAndreasen().evaluate_q(**params)


@pytest.mark.parametrize("kwargs", [{"q_bounds": (0, 1)}, {"q_bounds": (-1, 1)}, {"target_q": 0}])
def test_profile_positive_modulus_contract(profile, kwargs):
    with pytest.raises(DomainValidationError, match="positive q"):
        replace(profile, **kwargs)
    # A different model owns its own parameter constraints.
    assert replace(profile, model_id="custom", **kwargs).model_id == "custom"


def test_adjacent_large_model_boundaries_remain_finite():
    lo = 1e100
    middle = np.nextafter(lo, inf)
    hi = np.nextafter(middle, inf)
    values = ModifiedAndreasen().evaluate_q((lo, middle, hi), q=0.25, d_min_um=lo, d_max_um=hi)
    assert values == pytest.approx((0, 0.5, 1))


def test_deterministic_perturbation_recovers_reasonable_q():
    profile = AnalysisProfile("fit", "1", 1, 1000)
    grid = np.geomspace(1, 1000, 31)
    target = np.array(ModifiedAndreasen().evaluate_q(grid, q=0.25, d_min_um=1, d_max_um=1000))
    observed = target + 0.002 * np.sin(np.linspace(0, 2 * np.pi, len(grid)))
    observed[0], observed[-1] = 0, 1
    psd = PSD(grid, observed)
    result = fit_q(
        psd.particle_size_um,
        psd.cumulative_passing,
        profile=profile,
        model=ModifiedAndreasen(),
        loss=SquaredErrorLoss(),
    )
    assert result.converged and result.q == pytest.approx(0.25, abs=0.01)
    assert result.point_count == len(grid)
    assert (result.d_min_um, result.d_max_um) == (1, 1000)
    assert result.rmse > 0
    assert result.sse == result.metrics.sse
    assert result.mae == result.metrics.mae
    assert result.max_absolute_deviation == result.metrics.max_absolute_deviation


def test_fitting_filters_outside_nodes_without_loss_influence(profile):
    model = ModifiedAndreasen()
    grid = (0.5, 1, 10, 100, 200)
    observed = model.evaluate_q(grid, q=0.25, d_min_um=1, d_max_um=100)
    full = fit_q(grid, observed, profile=profile, model=model, loss=SquaredErrorLoss())
    interior = fit_q(
        grid[1:-1], observed[1:-1], profile=profile, model=model, loss=SquaredErrorLoss()
    )
    assert full == interior
    assert full.point_count == 3
    # Missing observations outside the fitting range cannot spoil valid coverage.
    missing = fit_q(
        grid, (None, *observed[1:-1], None), profile=profile, model=model, loss=SquaredErrorLoss()
    )
    assert missing == interior


@pytest.mark.parametrize("grid", [(1, 100), (0.1, 0.5, 1, 100, 1000), (0.1, 0.2, 0.5)])
def test_insufficient_in_range_points_raise_clear_domain_error(profile, grid):
    with pytest.raises(DomainValidationError, match="At least 3 PSD points inside"):
        fit_q(
            grid,
            np.linspace(0, 1, len(grid)),
            profile=profile,
            model=ModifiedAndreasen(),
            loss=SquaredErrorLoss(),
        )


def test_custom_loss_result_still_contains_actual_sse_metrics(profile):
    class ScaledLoss:
        loss_id = "scaled"

        def __call__(self, observed, predicted):
            return 2 * calculate_metrics(observed, predicted).sse

    profile = replace(profile, loss_id="scaled")
    result = fit_q(
        (1, 10, 100),
        (0.05, 0.3, 0.9),
        profile=profile,
        model=ModifiedAndreasen(),
        loss=ScaledLoss(),
    )
    assert result.converged
    assert result.objective_value == pytest.approx(2 * result.sse)
    assert result.sse > 0


@pytest.mark.parametrize("value", [nan, inf])
def test_nonfinite_objective_is_explicit_failure(profile, value):
    class InvalidLoss:
        loss_id = "sse"

        def __call__(self, observed, predicted):
            return value

    result = fit_q(
        (1, 10, 100), (0, 0.3, 1), profile=profile, model=ModifiedAndreasen(), loss=InvalidLoss()
    )
    assert result.status == FitStatus.FAILED
    assert not result.converged and result.q is None and result.sse is None
    assert result.rmse is None and result.mae is None and result.max_absolute_deviation is None
    assert result.point_count == 3


def test_optimizer_value_error_is_not_leaked(profile, monkeypatch):
    def invalid_optimizer(*args, **kwargs):
        raise ValueError("optimizer rejected input")

    monkeypatch.setattr("psd_analyzer.domain.services.q_fitting.minimize_scalar", invalid_optimizer)
    result = fit_q(
        (1, 10, 100),
        (0, 0.3, 1),
        profile=profile,
        model=ModifiedAndreasen(),
        loss=SquaredErrorLoss(),
    )
    assert result.status == FitStatus.FAILED
    assert "optimizer rejected input" in result.message


def test_optimizer_invalid_result_is_failure(profile, monkeypatch):
    monkeypatch.setattr(
        "psd_analyzer.domain.services.q_fitting.minimize_scalar",
        lambda *a, **k: SimpleNamespace(success=True, x=99, fun=0),
    )
    result = fit_q(
        (1, 10, 100),
        (0, 0.3, 1),
        profile=profile,
        model=ModifiedAndreasen(),
        loss=SquaredErrorLoss(),
    )
    assert result.status == FitStatus.FAILED


@pytest.mark.parametrize(
    "interpolator,expected", [(LinearInterpolator(), 9 / 99), (LogLinearInterpolator(), 0.5)]
)
def test_key_query_uses_task3_strategy_and_clamp(interpolator, expected):
    psd = PSD((1, 100), (0, 1))
    result = evaluate_at_sizes(psd, (0.5, 10, 200), interpolator)
    assert result.cumulative_passing == pytest.approx((0, expected, 1))
    strict = evaluate_at_sizes(psd, (0.5, 10, 200), interpolator, tail_policy=TailPolicy.STRICT)
    assert strict.cumulative_passing[0] is strict.cumulative_passing[-1] is None
    assert strict.cumulative_passing[1] == pytest.approx(expected)
    with pytest.raises(CoverageError):
        evaluate_at_sizes(psd, (0.5,), interpolator, tail_policy=TailPolicy.ERROR)


def test_query_delegates_exact_requested_grid_to_injected_strategy():
    calls = []

    class Spy:
        method_id = "spy"

        def interpolate(self, psd, grid, policy):
            calls.append((psd, grid, policy))
            return EvaluatedCurve(grid, (0.2, 0.7), psd.basis)

    psd = PSD((1, 100), (0, 1))
    result = evaluate_at_sizes(psd, (7, 35), Spy())
    assert calls == [(psd, (7, 35), TailPolicy.CLAMP)]
    assert result.cumulative_passing == (0.2, 0.7)


@pytest.mark.parametrize("grid", [(), (10, 1), (1, 1), (0, 1), (nan,)])
def test_invalid_query_sizes(grid):
    with pytest.raises(DomainValidationError):
        evaluate_at_sizes(PSD((1, 100), (0, 1)), grid, LinearInterpolator())


def test_query_rejects_invalid_model_and_policy():
    with pytest.raises(DomainValidationError):
        evaluate_at_sizes("bad", (1,), LinearInterpolator())
    with pytest.raises(DomainValidationError):
        evaluate_at_sizes(PSD((1, 100), (0, 1)), (1,), LinearInterpolator(), tail_policy="bad")


def test_query_rejects_incompatible_plugin_output():
    class WrongBasis:
        method_id = "wrong"

        def interpolate(self, psd, grid, policy):
            return EvaluatedCurve(grid, (0.5,), DistributionBasis.VOLUME)

    with pytest.raises(DomainValidationError, match="incompatible"):
        evaluate_at_sizes(PSD((1, 100), (0, 1)), (10,), WrongBasis())


def test_query_translates_plugin_numpy_error():
    class BrokenInterpolator:
        method_id = "broken"

        def interpolate(self, psd, grid, policy):
            raise ValueError("simulated array shape error")

    with pytest.raises(DomainValidationError, match="Key-size interpolation failed"):
        evaluate_at_sizes(PSD((1, 100), (0, 1)), (10,), BrokenInterpolator())


def test_configured_search_bounds_can_include_smaller_positive_q(profile):
    profile = replace(profile, q_bounds=(0.01, 0.1))
    model = ModifiedAndreasen()
    grid = (1, 10, 100)
    observed = model.evaluate_q(grid, q=0.03, d_min_um=1, d_max_um=100)
    result = fit_q(grid, observed, profile=profile, model=model, loss=SquaredErrorLoss())
    assert result.converged
    assert result.q == pytest.approx(0.03, abs=1e-6)
