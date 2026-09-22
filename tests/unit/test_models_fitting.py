from dataclasses import replace
from math import sqrt
from types import SimpleNamespace

import numpy as np
import pytest

from psd_analyzer.domain.exceptions import DomainValidationError
from psd_analyzer.domain.models.analysis_result import FitStatus
from psd_analyzer.domain.services.grid import build_grid
from psd_analyzer.domain.services.losses import SquaredErrorLoss
from psd_analyzer.domain.services.metrics import calculate_metrics
from psd_analyzer.domain.services.packing_models import ModifiedAndreasen
from psd_analyzer.domain.services.q_fitting import fit_q


@pytest.mark.parametrize("q", [1e-12, 0.25, 0.3, 1, 100])
def test_model_endpoints_monotonicity_and_finiteness(q):
    grid = (0.1, 1, 2, 10, 50, 100, 1000)
    actual = ModifiedAndreasen().evaluate_q(grid, q=q, d_min_um=1, d_max_um=100)
    assert actual[0] == actual[1] == 0
    assert actual[-1] == actual[-2] == 1
    assert np.all(np.isfinite(actual))
    assert np.all(np.diff(actual) >= 0)


def test_model_against_independent_values():
    model = ModifiedAndreasen()
    assert model.evaluate_q((1, 10, 100), q=1, d_min_um=1, d_max_um=100) == pytest.approx(
        (0, 9 / 99, 1)
    )
    assert model.evaluate_q((1, 10, 100), q=1e-12, d_min_um=1, d_max_um=100) == pytest.approx(
        (0, 0.5, 1)
    )
    assert model.evaluate_q((1, 10, 100), q=0.5, d_min_um=1, d_max_um=100)[1] == pytest.approx(
        (sqrt(10) - 1) / 9
    )
    with pytest.raises(DomainValidationError):
        model.cumulative_passing((1, 2), q=None, d_min_um=1, d_max_um=2)
    with pytest.raises(DomainValidationError):
        model.evaluate_q((1, 2), q=0.3, d_min_um=2, d_max_um=1)
    with pytest.raises(DomainValidationError):
        model.evaluate_q((1, 2), q=1e308, d_min_um=1, d_max_um=1e308)


@pytest.mark.parametrize("q", [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.8, 0.97])
def test_recover_known_q(profile, q):
    model = ModifiedAndreasen()
    grid = build_grid(profile)
    observed = model.evaluate_q(grid, q=q, d_min_um=profile.d_min_um, d_max_um=profile.d_max_um)
    result = fit_q(grid, observed, profile=profile, model=model, loss=SquaredErrorLoss())
    assert result.status == FitStatus.SUCCESS
    assert result.equivalent_q == pytest.approx(q, abs=1e-6)
    assert result.objective_value < 1e-12


@pytest.mark.parametrize("q", [0.05, 1])
def test_boundary_fit_preserves_warning(profile, q):
    model = ModifiedAndreasen()
    grid = build_grid(profile)
    observed = model.evaluate_q(grid, q=q, d_min_um=1, d_max_um=100)
    fit = fit_q(grid, observed, profile=profile, model=model, loss=SquaredErrorLoss())
    assert fit.status == FitStatus.AT_BOUND
    assert fit.equivalent_q == q


def test_missing_coverage_is_not_zero(profile):
    result = fit_q(
        (1, 10, 100),
        (None, 0.5, 1),
        profile=profile,
        model=ModifiedAndreasen(),
        loss=SquaredErrorLoss(),
    )
    assert result.status == FitStatus.INSUFFICIENT_COVERAGE
    assert result.equivalent_q is None


def test_flat_and_invalid_loss(profile):
    class FlatLoss:
        loss_id = "flat"

        def __call__(self, observed, predicted):
            return 1.0

    result = fit_q(
        (1, 10, 100),
        (0, 0.5, 1),
        profile=replace(profile, loss_id="flat"),
        model=ModifiedAndreasen(),
        loss=FlatLoss(),
    )
    assert result.status == FitStatus.WEAKLY_IDENTIFIED

    class InvalidLoss(FlatLoss):
        def __call__(self, observed, predicted):
            return -1

    result = fit_q(
        (1, 10, 100),
        (0, 0.5, 1),
        profile=replace(profile, loss_id="flat"),
        model=ModifiedAndreasen(),
        loss=InvalidLoss(),
    )
    assert result.status == FitStatus.FAILED


def test_optimizer_failure_is_explicit(profile, monkeypatch):
    monkeypatch.setattr(
        "psd_analyzer.domain.services.q_fitting.minimize_scalar",
        lambda *a, **k: SimpleNamespace(success=False, message="failed"),
    )
    fit = fit_q(
        (1, 10, 100),
        (0, 0.5, 1),
        profile=profile,
        model=ModifiedAndreasen(),
        loss=SquaredErrorLoss(),
    )
    assert fit.status == FitStatus.FAILED and fit.equivalent_q is None


@pytest.mark.parametrize(
    "grid,passing",
    [
        ((1, 10, 100), (0, 1)),
        ((1, 10, 100), (0, 1.1, 1)),
        ((1, 10, 100), (0, 0.9, 0.5)),
        ((0.5, 10, 100), (0, 0.5, 1)),
    ],
)
def test_invalid_fitting_data(profile, grid, passing):
    with pytest.raises(DomainValidationError):
        fit_q(grid, passing, profile=profile, model=ModifiedAndreasen(), loss=SquaredErrorLoss())


def test_wrong_strategy_identity(profile):
    with pytest.raises(DomainValidationError):
        fit_q(
            (1, 10, 100),
            (0, 0.5, 1),
            profile=replace(profile, loss_id="other"),
            model=ModifiedAndreasen(),
            loss=SquaredErrorLoss(),
        )


def test_hand_calculated_metrics():
    m = calculate_metrics((0, 0.5, 1), (0, 0.4, 0.8))
    assert m.sse == pytest.approx(0.05)
    assert m.mse == pytest.approx(0.05 / 3)
    assert m.rmse == pytest.approx(sqrt(0.05 / 3))
    assert m.mae == pytest.approx(0.1)
    assert m.max_absolute_deviation == pytest.approx(0.2)
    assert m.n == 3


@pytest.mark.parametrize(
    "obs,pred", [((), ()), ((0, 1), (0,)), ((0, 1), (0, 2)), ((0, 1), (0, float("nan")))]
)
def test_metrics_reject_invalid(obs, pred):
    with pytest.raises(DomainValidationError):
        calculate_metrics(obs, pred)


def test_partial_invalid_psd_is_rejected_before_coverage_status(profile):
    with pytest.raises(DomainValidationError):
        fit_q(
            (1, 10, 100),
            (None, 1.1, 1),
            profile=profile,
            model=ModifiedAndreasen(),
            loss=SquaredErrorLoss(),
        )


def test_invalid_model_curve_cannot_be_hidden_by_custom_loss(profile):
    class InvalidModel:
        model_id = "invalid"

        def evaluate_q(self, grid, **kwargs):
            return tuple(2.0 for _ in grid)

    result = fit_q(
        (1, 10, 100),
        (0, 0.5, 1),
        profile=replace(profile, model_id="invalid"),
        model=InvalidModel(),
        loss=SquaredErrorLoss(),
    )
    assert result.status == FitStatus.FAILED
    assert result.equivalent_q is None
