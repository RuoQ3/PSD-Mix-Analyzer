"""Bounded one-parameter fitting with diagnostics and replaceable loss."""

from collections.abc import Sequence

import numpy as np
from scipy.optimize import minimize_scalar

from ..exceptions import DomainValidationError
from ..models.analysis_profile import AnalysisProfile
from ..models.analysis_result import FitResult, FitStatus
from ..models.psd import PSD
from ..protocols import LossFunction, QFittableModel
from ..validation import finite, sizes, vector
from .metrics import calculate_metrics

MIN_FIT_POINTS = 3


def fit_q(
    particle_size_um: Sequence[float],
    cumulative_passing: Sequence[float | None],
    *,
    profile: AnalysisProfile,
    model: QFittableModel,
    loss: LossFunction,
) -> FitResult:
    """Fit only inclusive in-range observations; never regrid or repair input PSDs.

    Invalid input raises DomainValidationError. Numerical/model/loss failures are
    represented by FitStatus.FAILED, keeping optimizer internals out of the API.
    """
    grid = sizes(particle_size_um)
    if len(grid) != len(cumulative_passing):
        raise DomainValidationError("Fitting vectors must have equal lengths")
    if model.model_id != profile.model_id or loss.loss_id != profile.loss_id:
        raise DomainValidationError("Injected model/loss does not match the analysis profile")
    observed = vector((v for v in cumulative_passing if v is not None), "passing")
    if any(v < 0 or v > 1 for v in observed) or any(
        a > b for a, b in zip(observed, observed[1:], strict=False)
    ):
        raise DomainValidationError("Fitting requires a valid cumulative PSD")
    selected = tuple(
        (d, p)
        for d, p in zip(grid, cumulative_passing, strict=True)
        if profile.d_min_um <= d <= profile.d_max_um
    )
    if len(selected) < MIN_FIT_POINTS:
        raise DomainValidationError(
            f"At least {MIN_FIT_POINTS} PSD points inside [Dmin, Dmax] are required for q fitting"
        )
    grid = tuple(d for d, _ in selected)
    observed = vector((p for _, p in selected if p is not None), "passing")

    if any(p is None for _, p in selected):
        return FitResult(
            FitStatus.INSUFFICIENT_COVERAGE,
            message="Full in-range fitting coverage required",
            point_count=len(observed),
            d_min_um=profile.d_min_um,
            d_max_um=profile.d_max_um,
        )
    calls = 0

    def objective(q: float) -> float:
        nonlocal calls
        calls += 1
        predicted = model.evaluate_q(
            grid, q=q, d_min_um=profile.d_min_um, d_max_um=profile.d_max_um
        )
        # Validate strategy output independently of the user-supplied loss.
        predicted = PSD(grid, predicted, profile.mix_basis).cumulative_passing
        value = finite(loss(observed, predicted), "loss")
        if value < 0:
            raise DomainValidationError("Loss must be nonnegative")
        return value

    try:
        probes = np.linspace(*profile.q_bounds, profile.scan_points)
        values = [objective(float(q)) for q in probes]
        if max(values) - min(values) <= profile.weak_loss_span:
            return FitResult(
                FitStatus.WEAKLY_IDENTIFIED,
                evaluations=calls,
                message="Loss is effectively flat over the search interval",
                point_count=len(observed),
                d_min_um=profile.d_min_um,
                d_max_um=profile.d_max_um,
            )
        candidates = [(values[0], float(probes[0])), (values[-1], float(probes[-1]))]
        intervals = [
            (float(probes[max(0, i - 1)]), float(probes[min(len(probes) - 1, i + 1)]))
            for i in range(len(probes))
            if (i == 0 or values[i] <= values[i - 1])
            and (i == len(probes) - 1 or values[i] <= values[i + 1])
        ]
        for lo, hi in intervals:
            result = minimize_scalar(
                objective,
                bounds=(lo, hi),
                method="bounded",
                options={"xatol": profile.q_tolerance, "maxiter": 500},
            )
            if not result.success:
                raise DomainValidationError(str(result.message))
            candidate_q = finite(result.x, "optimizer q")
            candidate_loss = finite(result.fun, "optimizer loss")
            if not lo <= candidate_q <= hi or candidate_loss < 0:
                raise DomainValidationError("Optimizer returned an invalid result")
            candidates.append((candidate_loss, candidate_q))
        best_loss, best_q = min(candidates)
        boundary_tolerance = profile.q_tolerance * 10
        at_bound = min(abs(best_q - b) for b in profile.q_bounds) <= boundary_tolerance
        return FitResult(
            FitStatus.AT_BOUND if at_bound else FitStatus.SUCCESS,
            best_q,
            best_loss,
            calls,
            "Search boundary reached" if at_bound else "Converged after interval scan",
            metrics=calculate_metrics(
                observed,
                PSD(
                    grid,
                    model.evaluate_q(
                        grid,
                        q=best_q,
                        d_min_um=profile.d_min_um,
                        d_max_um=profile.d_max_um,
                    ),
                    profile.mix_basis,
                ).cumulative_passing,
            ),
            point_count=len(observed),
            d_min_um=profile.d_min_um,
            d_max_um=profile.d_max_um,
        )
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        return FitResult(
            FitStatus.FAILED,
            evaluations=calls,
            message=str(exc),
            point_count=len(observed),
            d_min_um=profile.d_min_um,
            d_max_um=profile.d_max_um,
        )
