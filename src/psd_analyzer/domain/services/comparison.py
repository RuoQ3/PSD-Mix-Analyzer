"""Compare only results with identical numerical conventions."""

from ..exceptions import IncompatibleComparisonError
from ..models.analysis_result import (
    AnalysisResult,
    ComparisonResult,
    Diagnostic,
    FitStatus,
    KeyPassing,
)
from .metrics import calculate_metrics


def compare_results(current: AnalysisResult, baseline: AnalysisResult) -> ComparisonResult:
    if (
        current.profile != baseline.profile
        or current.algorithm_version != baseline.algorithm_version
    ):
        raise IncompatibleComparisonError(
            "Profile or algorithm changed; recompute on one convention"
        )

    def signature(result: AnalysisResult) -> tuple[tuple[str, float, str, str], ...]:
        return tuple(
            (c.line_id, c.mass_fraction, c.measurement.method, c.measurement.protocol_id)
            for c in result.components
        )

    if signature(current) != signature(baseline):
        raise IncompatibleComparisonError("Recipe fractions or measurement protocols differ")
    if (
        current.mixed_curve.particle_size_um != baseline.mixed_curve.particle_size_um
        or current.mixed_curve.basis != baseline.mixed_curve.basis
    ):
        raise IncompatibleComparisonError("Mixed curve grids or bases differ")
    if not current.mixed_curve.complete or not baseline.mixed_curve.complete:
        raise IncompatibleComparisonError("Full coverage is required for standard comparison")
    delta = tuple(
        a - b
        for a, b in zip(
            current.mixed_curve.cumulative_passing,
            baseline.mixed_curve.cumulative_passing,
            strict=True,
        )
        if a is not None and b is not None
    )
    diagnostics: list[Diagnostic] = []
    dq = None
    if (
        current.fit.status == baseline.fit.status == FitStatus.SUCCESS
        and current.fit.equivalent_q is not None
        and baseline.fit.equivalent_q is not None
    ):
        dq = current.fit.equivalent_q - baseline.fit.equivalent_q
    else:
        diagnostics.append(
            Diagnostic("DELTA_Q_UNAVAILABLE", "Two successful interior fits required")
        )
    if tuple(k.particle_size_um for k in current.key_passing) != tuple(
        k.particle_size_um for k in baseline.key_passing
    ):
        raise IncompatibleComparisonError("Key-size grids differ")
    keys = tuple(
        KeyPassing(
            a.particle_size_um,
            a.cumulative_passing - b.cumulative_passing
            if a.cumulative_passing is not None and b.cumulative_passing is not None
            else None,
            "outside_supported_coverage"
            if a.cumulative_passing is None or b.cumulative_passing is None
            else None,
        )
        for a, b in zip(current.key_passing, baseline.key_passing, strict=True)
    )
    metrics = calculate_metrics(
        tuple(p for p in current.mixed_curve.cumulative_passing if p is not None),
        tuple(p for p in baseline.mixed_curve.cumulative_passing if p is not None),
    )
    return ComparisonResult(
        current.mixed_curve.particle_size_um,
        delta,
        dq,
        keys,
        metrics.max_absolute_deviation,
        tuple(diagnostics),
        baseline=baseline,
        current=current,
        metrics=metrics,
    )
