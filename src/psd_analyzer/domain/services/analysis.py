"""Pure numerical evaluation. No files, transactions, UI, clocks or global state."""

from collections.abc import Sequence

from ..exceptions import DomainValidationError
from ..models.analysis_profile import AnalysisProfile
from ..models.analysis_result import (
    AnalysisResult,
    Diagnostic,
    EvaluatedCurve,
    FitResult,
    FitStatus,
    KeyPassing,
)
from ..models.recipe import MixtureComponent
from ..protocols import LossFunction, PackingModel, PSDInterpolator, QFittableModel
from .basis_conversion import resolve_weights
from .grid import build_grid
from .interpolation import get_interpolator
from .losses import SquaredErrorLoss
from .metrics import calculate_metrics
from .mixing import mix_psd
from .packing_models import ModifiedAndreasen
from .q_fitting import fit_q


def analyze_mixture(
    components: Sequence[MixtureComponent],
    profile: AnalysisProfile,
    *,
    model: PackingModel | None = None,
    loss: LossFunction | None = None,
    interpolator: PSDInterpolator | None = None,
) -> AnalysisResult:
    ordered = tuple(sorted(components, key=lambda c: c.line_id))
    selected_model = model if model is not None else ModifiedAndreasen()
    selected_loss = loss if loss is not None else SquaredErrorLoss()
    selected_interpolator = (
        interpolator if interpolator is not None else get_interpolator(profile.interpolation)
    )
    if (
        selected_model.model_id != profile.model_id
        or selected_loss.loss_id != profile.loss_id
        or selected_interpolator.method_id != profile.interpolation.value
    ):
        raise DomainValidationError("Injected strategies must match the saved profile")
    weights, original_sum, basis_diagnostics = resolve_weights(ordered, profile.mix_basis)
    grid = build_grid(profile)
    mixed = mix_psd(
        ordered,
        grid,
        target_basis=profile.mix_basis,
        interpolator=selected_interpolator,
        tail_policy=profile.tail_policy,
    )
    keys = mix_psd(
        ordered,
        profile.key_sizes_um,
        target_basis=profile.mix_basis,
        interpolator=selected_interpolator,
        tail_policy=profile.tail_policy,
    )
    key_passing = tuple(
        KeyPassing(d, p, None if p is not None else "outside_supported_coverage")
        for d, p in zip(keys.particle_size_um, keys.cumulative_passing, strict=True)
    )
    diagnostics = list(basis_diagnostics)
    protocols = {
        (c.measurement.method, c.measurement.protocol_id) for c in ordered if c.mass_fraction > 0
    }
    if len(protocols) > 1:
        if not profile.measurement_compatibility_confirmed:
            raise DomainValidationError(
                "Mixed measurement protocols require explicit compatibility confirmation"
            )
        diagnostics.append(
            Diagnostic(
                "MEASUREMENT_COMPATIBILITY_ASSUMPTION",
                "Different measurement protocols accepted by the analysis profile",
            )
        )
    fitted = target = None
    fit_metrics = target_metrics = None
    if isinstance(selected_model, QFittableModel):
        fit = fit_q(
            grid,
            mixed.cumulative_passing,
            profile=profile,
            model=selected_model,
            loss=selected_loss,
        )
    else:
        fit = FitResult(
            FitStatus.NOT_APPLICABLE, message="Selected model does not support q fitting"
        )
    if not mixed.complete:
        diagnostics.append(
            Diagnostic("INCOMPLETE_COVERAGE", "Some evaluation nodes are unsupported")
        )
    if fit.status != FitStatus.SUCCESS:
        diagnostics.append(Diagnostic(f"FIT_{fit.status.value.upper()}", fit.message))
    if any(k.cumulative_passing is None for k in key_passing):
        diagnostics.append(Diagnostic("KEY_SIZE_UNAVAILABLE", "Some key sizes lack coverage"))
    observed = tuple(p for p in mixed.cumulative_passing if p is not None)
    if fit.equivalent_q is not None:
        predicted = selected_model.cumulative_passing(
            grid, q=fit.equivalent_q, d_min_um=profile.d_min_um, d_max_um=profile.d_max_um
        )
        fit_metrics = calculate_metrics(observed, predicted)
        fitted = EvaluatedCurve(grid, predicted, profile.mix_basis)
    if profile.target_q is not None or not isinstance(selected_model, QFittableModel):
        predicted = selected_model.cumulative_passing(
            grid, q=profile.target_q, d_min_um=profile.d_min_um, d_max_um=profile.d_max_um
        )
        # Validate plug-in output even if missing observations prevent residual metrics.
        calculate_metrics(predicted, predicted)
        if len(predicted) != len(grid):
            raise DomainValidationError("Target model returned a mismatched curve")
        target = EvaluatedCurve(grid, predicted, profile.mix_basis)
        if mixed.complete:
            target_metrics = calculate_metrics(observed, predicted)
    return AnalysisResult(
        profile,
        ordered,
        mixed,
        fit,
        fitted,
        target,
        fit_metrics,
        target_metrics,
        key_passing,
        tuple(diagnostics),
        weights,
        original_sum,
    )
