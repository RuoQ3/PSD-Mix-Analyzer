"""Grouped comparison of already evaluated key particle sizes."""

from collections.abc import Sequence

import plotly.graph_objects as go

from psd_analyzer.domain.models.analysis_result import ComparisonResult

from ._common import display_vectors, label, layout, snapshots
from .exceptions import VisualizationError
from .models import KeySizeSeries


def build_key_size_comparison_figure(
    data: ComparisonResult | Sequence[KeySizeSeries],
    *,
    title: str = "Passing at key particle sizes",
) -> go.Figure:
    """Display supplied key sizes exactly, without interpolation or missing-value filling."""
    if isinstance(data, ComparisonResult):
        baseline, current = snapshots(data)
        series: Sequence[KeySizeSeries] = (
            KeySizeSeries("Baseline", baseline.key_passing),
            KeySizeSeries("Current", current.key_passing),
        )
    else:
        series = data
    if not series:
        raise VisualizationError("At least one key-size series is required")
    figure = go.Figure()
    categories: tuple[str, ...] | None = None
    expected_grid: tuple[float, ...] | None = None
    for index, item in enumerate(series):
        grid, passing = display_vectors(
            tuple(key.particle_size_um for key in item.values),
            tuple(key.cumulative_passing for key in item.values),
        )
        if expected_grid is not None and grid != expected_grid:
            raise VisualizationError("Key-size comparison requires identical supplied sizes")
        expected_grid = grid
        categories = tuple(f"{size:g} μm" for size in grid)
        figure.add_trace(
            go.Bar(
                x=categories,
                y=passing,
                name=label(item.name),
                marker_color=("#1565C0", "#087F5B", "#D97706")[index % 3],
                hovertemplate="%{x}<br>Passing: %{y:.3f}%<extra>%{fullData.name}</extra>",
            )
        )
    layout(figure, title, x_title="Particle size / μm", y_title="Cumulative passing / %")
    figure.update_layout(barmode="group")
    figure.update_xaxes(type="category", categoryorder="array", categoryarray=categories)
    figure.update_yaxes(range=[0, 100])
    return figure
