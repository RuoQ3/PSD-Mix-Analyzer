"""Read-model-only time trends, without database queries or control-limit inference."""

from collections import defaultdict
from collections.abc import Sequence

import plotly.graph_objects as go

from ..application.dto.history import AnalysisSummary
from ..domain.models.analysis_result import FitStatus
from ._common import layout


def build_q_trend_figure(
    summaries: Sequence[AnalysisSummary], *, title: str = "Equivalent q history (UTC)"
) -> go.Figure:
    """Keep recipe/version/type series separate, preserve missing fits and boundary status."""
    groups: dict[tuple[str, str, str, str], list[AnalysisSummary]] = defaultdict(list)
    for item in summaries:
        groups[
            (item.recipe_id, item.recipe_version, item.analysis_type.value, item.convention_key)
        ].append(item)
    figure = go.Figure()
    for (recipe, version, kind, convention), items in sorted(groups.items()):
        ordered = sorted(items, key=lambda item: item.created_at)
        name = f"{recipe} / {version} / {kind}"
        if convention:
            name += f" / {convention[:8]}"
        figure.add_trace(
            go.Scatter(
                x=[item.created_at for item in ordered],
                y=[
                    item.equivalent_q
                    if item.fit_status in (FitStatus.SUCCESS, FitStatus.AT_BOUND)
                    else None
                    for item in ordered
                ],
                name=name,
                mode="lines+markers",
                connectgaps=False,
                customdata=[item.fit_status.value for item in ordered],
                marker={
                    "color": [
                        "#D97706" if item.fit_status == FitStatus.AT_BOUND else "#1565C0"
                        for item in ordered
                    ]
                },
                hovertemplate="%{x}<br>Equivalent q: %{y:.5f}<br>%{customdata}<extra></extra>",
            )
        )
        if any(item.target_q is not None for item in ordered):
            figure.add_trace(
                go.Scatter(
                    x=[item.created_at for item in ordered],
                    y=[item.target_q for item in ordered],
                    name=f"{name} — target reference",
                    mode="lines+markers",
                    connectgaps=False,
                    line={"dash": "dot"},
                )
            )
    layout(figure, title, x_title="Timestamp (UTC)", y_title="q (grading reference)")
    figure.update_xaxes(type="date")
    if not summaries:
        figure.add_annotation(
            text="No historical analyses", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5
        )
    return figure
