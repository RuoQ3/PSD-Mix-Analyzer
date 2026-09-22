"""Read-only cumulative PSD figures with logarithmic particle-size axes."""

from collections.abc import Sequence

import plotly.graph_objects as go

from psd_analyzer.domain.models.analysis_result import AnalysisResult, ComparisonResult

from ._common import display_vectors, label, layout, snapshots
from .exceptions import VisualizationError
from .models import PSDSeries


def _result_series(result: AnalysisResult | ComparisonResult) -> tuple[PSDSeries, ...]:
    if isinstance(result, ComparisonResult):
        baseline, current = snapshots(result)
        return (
            PSDSeries("Baseline", baseline.mixed_curve, "baseline"),
            PSDSeries("Current", current.mixed_curve, "current"),
        )
    return (
        PSDSeries("Mixed PSD", result.mixed_curve, "mixed"),
        PSDSeries("Target PSD", result.target_curve, "target"),
    )


def _trace(series: PSDSeries, index: int) -> go.Scatter:
    if series.psd is None:
        raise VisualizationError("Cannot build a trace from an absent PSD")
    x, y = display_vectors(series.psd.particle_size_um, series.psd.cumulative_passing)
    styles = {
        "material": (("#6B7280", "#8B6A47", "#5C8D89")[index % 3], "solid", 1.5),
        "mixed": ("#1565C0", "solid", 3.5),
        "target": ("#D97706", "dash", 2.5),
        "baseline": ("#1565C0", "dash", 2.5),
        "current": ("#087F5B", "solid", 3.5),
    }
    if series.role not in styles:
        raise VisualizationError(f"Unknown PSD series role: {series.role}")
    color, dash, width = styles[series.role]
    return go.Scatter(
        x=x,
        y=y,
        name=label(series.name),
        mode="lines",
        line={"color": color, "dash": dash, "width": width},
        connectgaps=False,
        hovertemplate=(
            "Particle size: %{x:.6g} μm<br>Passing: %{y:.3f}%<extra>%{fullData.name}</extra>"
        ),
    )


def build_psd_figure(
    data: Sequence[PSDSeries] | AnalysisResult | ComparisonResult,
    *,
    title: str = "Cumulative particle size distribution",
) -> go.Figure:
    """Present supplied curves or result snapshots; optional target curves are skipped."""
    series = _result_series(data) if isinstance(data, (AnalysisResult, ComparisonResult)) else data
    visible = tuple(item for item in series if item.psd is not None)
    if not visible:
        raise VisualizationError("At least one nonempty PSD series is required")
    if len({item.psd.basis for item in visible if item.psd is not None}) != 1:
        raise VisualizationError("PSD series must share the same distribution basis")
    figure = go.Figure(data=[_trace(item, index) for index, item in enumerate(visible)])
    layout(figure, title, x_title="Particle size / μm", y_title="Cumulative passing / %")
    figure.update_xaxes(type="log")
    figure.update_yaxes(range=[0, 100])
    return figure
