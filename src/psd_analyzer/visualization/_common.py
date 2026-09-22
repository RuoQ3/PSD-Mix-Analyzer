"""Presentation validation and consistent layout, without numerical services."""

from collections.abc import Sequence
from math import isfinite

import plotly.graph_objects as go

from psd_analyzer.domain.models.analysis_result import AnalysisResult, ComparisonResult

from .exceptions import VisualizationError


def label(value: str) -> str:
    """Require a readable series label."""
    if not isinstance(value, str) or not value.strip():
        raise VisualizationError("Series name must not be empty")
    return value


def number(value: float, name: str) -> float:
    """Reject nonnumeric and nonfinite values before they reach Plotly."""
    if isinstance(value, (bool, str, bytes)):
        raise VisualizationError(f"{name} must be a finite number")
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise VisualizationError(f"{name} must be a finite number") from exc
    if not isfinite(converted):
        raise VisualizationError(f"{name} must be finite")
    return converted


def display_vectors(
    sizes: Sequence[float],
    values: Sequence[float | None],
    *,
    difference: bool = False,
) -> tuple[tuple[float, ...], tuple[float | None, ...]]:
    """Validate coordinates and copy fractions into percent or percentage points."""
    if not sizes or len(sizes) != len(values):
        raise VisualizationError("Nonempty particle sizes and passing must have equal lengths")
    grid = tuple(number(value, "particle size") for value in sizes)
    if any(value <= 0 for value in grid) or any(
        left >= right for left, right in zip(grid, grid[1:], strict=False)
    ):
        raise VisualizationError("Particle sizes must be positive and strictly increasing")
    validated = tuple(None if v is None else number(v, "passing") for v in values)
    lower = -1 if difference else 0
    if any(value < lower or value > 1 for value in validated if value is not None):
        raise VisualizationError(f"Passing must be within [{lower}, 1]")
    present = tuple(value for value in validated if value is not None)
    if not difference and any(a > b for a, b in zip(present, present[1:], strict=False)):
        raise VisualizationError("Cumulative passing must be nondecreasing")
    return grid, tuple(None if value is None else 100 * value for value in validated)


def snapshots(result: ComparisonResult) -> tuple[AnalysisResult, AnalysisResult]:
    """Require the already computed snapshots needed by comparison charts."""
    if result.baseline is None or result.current is None:
        raise VisualizationError("Comparison requires baseline and current analysis snapshots")
    return result.baseline, result.current


def layout(figure: go.Figure, title: str, *, x_title: str, y_title: str) -> None:
    """Apply a restrained responsive engineering layout."""
    figure.update_layout(
        title=title,
        template="plotly_white",
        autosize=True,
        margin={"l": 75, "r": 30, "t": 75, "b": 80},
        legend={"orientation": "h", "y": 1.04, "x": 0},
        hovermode="closest",
        xaxis_title=x_title,
        yaxis_title=y_title,
    )
    figure.update_xaxes(showgrid=True)
    figure.update_yaxes(showgrid=True, zeroline=False)
