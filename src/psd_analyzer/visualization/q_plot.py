"""Lightweight q comparison that retains fit status and missing results."""

from collections.abc import Sequence

import plotly.graph_objects as go

from psd_analyzer.domain.models.analysis_result import ComparisonResult, FitStatus

from ._common import label, layout, number, snapshots
from .exceptions import VisualizationError
from .models import QSeries


def build_q_comparison_figure(
    data: ComparisonResult | Sequence[QSeries], *, title: str = "Equivalent q comparison"
) -> go.Figure:
    """Compare two or more fits; boundary fits are flagged, unavailable q stays missing."""
    if isinstance(data, ComparisonResult):
        baseline, current = snapshots(data)
        series: Sequence[QSeries] = (
            QSeries("Baseline", baseline.fit),
            QSeries("Current", current.fit),
        )
    else:
        series = data
    if len(series) < 2:
        raise VisualizationError("q comparison requires at least two fits; use a card for one q")
    names: list[str] = []
    values: list[float | None] = []
    statuses: list[str] = []
    colors: list[str] = []
    warnings: list[str] = []
    for item in series:
        name = label(item.name)
        status = item.fit.status
        if not isinstance(status, FitStatus):
            raise VisualizationError("Unknown q fit status")
        q = item.fit.equivalent_q
        if q is not None:
            q = number(q, "q")
        names.append(name)
        values.append(q if status in (FitStatus.SUCCESS, FitStatus.AT_BOUND) else None)
        statuses.append(status.value)
        colors.append("#D97706" if status == FitStatus.AT_BOUND else "#1565C0")
        if status != FitStatus.SUCCESS or q is None:
            warnings.append(f"{name}: {status.value}" + (" (q unavailable)" if q is None else ""))
    figure = go.Figure(
        data=[
            go.Bar(
                x=names,
                y=values,
                customdata=statuses,
                marker_color=colors,
                name="Equivalent q",
                hovertemplate="%{x}<br>q: %{y:.5f}<br>Status: %{customdata}<extra></extra>",
            )
        ]
    )
    layout(figure, title, x_title="Analysis", y_title="Equivalent q")
    figure.update_xaxes(type="category", categoryorder="array", categoryarray=names)
    if warnings:
        figure.add_annotation(
            text="<br>".join(warnings),
            xref="paper",
            yref="paper",
            x=0,
            y=-0.28,
            xanchor="left",
            yanchor="top",
            showarrow=False,
            align="left",
        )
        figure.update_layout(margin={"b": 110 + 18 * len(warnings)})
    return figure
