"""Present the precomputed current-minus-baseline difference."""

import plotly.graph_objects as go

from psd_analyzer.domain.models.analysis_result import ComparisonResult

from ._common import display_vectors, layout


def build_psd_difference_figure(
    result: ComparisonResult, *, title: str = "PSD difference: current − baseline"
) -> go.Figure:
    """Convert existing fractional differences to percentage points, without subtraction."""
    x, y = display_vectors(result.particle_size_um, result.delta_psd, difference=True)
    figure = go.Figure(
        data=[
            go.Scatter(
                x=x,
                y=y,
                name="Current − baseline",
                mode="lines",
                line={"color": "#087F5B", "width": 2.5},
                connectgaps=False,
                hovertemplate=(
                    "Particle size: %{x:.6g} μm<br>Δ passing: %{y:+.3f} percentage points"
                    "<extra>%{fullData.name}</extra>"
                ),
            )
        ]
    )
    layout(
        figure,
        title,
        x_title="Particle size / μm",
        y_title="Δ cumulative passing / percentage points",
    )
    figure.update_xaxes(type="log")
    figure.add_hline(y=0, line_dash="dash", line_color="#6B7280", line_width=1)
    return figure
