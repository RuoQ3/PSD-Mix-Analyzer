"""Inspect figure structures and presentation boundaries, not pixel snapshots."""

from dataclasses import replace

import plotly.graph_objects as go
import pytest

from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.models.analysis_result import (
    AnalysisResult,
    ComparisonResult,
    EvaluatedCurve,
    FitResult,
    FitStatus,
    KeyPassing,
)
from psd_analyzer.domain.models.psd import PSD, DistributionBasis
from psd_analyzer.visualization import (
    KeySizeSeries,
    PSDSeries,
    QSeries,
    VisualizationError,
    build_key_size_comparison_figure,
    build_psd_difference_figure,
    build_psd_figure,
    build_q_comparison_figure,
)


def analysis(*, target=True):
    curve = EvaluatedCurve((1, 10, 100), (0, 0.25, 1), DistributionBasis.MASS)
    return AnalysisResult(
        profile=AnalysisProfile("test", "1", 1, 100, key_sizes_um=(10, 100)),
        components=(),
        mixed_curve=curve,
        fit=FitResult(FitStatus.SUCCESS, equivalent_q=0.25),
        fitted_curve=None,
        target_curve=curve if target else None,
        fit_metrics=None,
        target_metrics=None,
        key_passing=(KeyPassing(10, 0.25), KeyPassing(100, 1)),
        diagnostics=(),
        actual_weights=(),
        input_fraction_sum=1,
    )


def comparison():
    baseline = analysis()
    current = replace(
        baseline,
        fit=FitResult(FitStatus.SUCCESS, equivalent_q=0.3),
        mixed_curve=replace(baseline.mixed_curve, cumulative_passing=(0, 0.28, 1)),
        key_passing=(KeyPassing(10, 0.28), KeyPassing(100, 1)),
    )
    return ComparisonResult(
        (1, 10, 100),
        (0, 0.03, 0),
        0.05,
        (KeyPassing(10, 0.03), KeyPassing(100, 0)),
        0.03,
        baseline=baseline,
        current=current,
    )


def test_analysis_figure_log_axis_percentages_and_distinct_styles():
    result = analysis()
    figure = build_psd_figure(result)
    assert isinstance(figure, go.Figure)
    assert figure.layout.xaxis.type == "log"
    assert figure.layout.yaxis.range == (0, 100)
    assert len(figure.data) == 2
    assert tuple(figure.data[0].y) == (0, 25, 100)
    assert figure.data[0].line.width > figure.data[1].line.width
    assert figure.data[1].line.dash == "dash"
    assert figure.layout.autosize is True
    assert "μm" in figure.data[0].hovertemplate
    assert result.mixed_curve.cumulative_passing == (0, 0.25, 1)


def test_absent_target_is_normal_and_not_synthesized():
    assert len(build_psd_figure(analysis(target=False)).data) == 1
    source = PSD((1, 100), (0.1, 0.9))
    figure = build_psd_figure((PSDSeries("A", source), PSDSeries("Target", None, "target")))
    assert len(figure.data) == 1
    assert source.cumulative_passing == (0.1, 0.9)


def test_comparison_result_can_be_plotted_directly():
    result = comparison()
    figure = build_psd_figure(result)
    assert [trace.name for trace in figure.data] == ["Baseline", "Current"]
    assert tuple(figure.data[1].y) == pytest.approx((0, 28, 100))
    assert figure.data[0].line.dash != figure.data[1].line.dash


def test_missing_coverage_remains_gap():
    curve = EvaluatedCurve((1, 10, 100), (None, 0.5, 1), DistributionBasis.MASS)
    figure = build_psd_figure((PSDSeries("Partial", curve),))
    assert tuple(figure.data[0].y) == (None, 50, 100)
    assert figure.data[0].connectgaps is False


@pytest.mark.parametrize("series", [(), (PSDSeries("Target", None, "target"),)])
def test_empty_psd_series_fails(series):
    with pytest.raises(VisualizationError, match="nonempty"):
        build_psd_figure(series)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("particle_size_um", ()),
        ("particle_size_um", (1,)),
        ("particle_size_um", (0, 100)),
        ("particle_size_um", (100, 1)),
        ("cumulative_passing", (0, float("nan"))),
        ("cumulative_passing", (0, float("inf"))),
        ("cumulative_passing", (0.8, 0.2)),
        ("cumulative_passing", (0, 1.01)),
    ],
)
def test_malformed_input_is_rejected_at_presentation_boundary(field, value):
    # Even data corrupted after construction must not silently become a misleading chart.
    psd = PSD((1, 100), (0, 1))
    object.__setattr__(psd, field, value)
    with pytest.raises(VisualizationError):
        build_psd_figure((PSDSeries("Invalid", psd),))


def test_psd_roles_names_and_bases_are_checked():
    psd = PSD((1, 100), (0, 1))
    with pytest.raises(VisualizationError, match="name"):
        build_psd_figure((PSDSeries("", psd),))
    with pytest.raises(VisualizationError, match="role"):
        build_psd_figure((PSDSeries("A", psd, "invalid"),))
    with pytest.raises(VisualizationError, match="basis"):
        build_psd_figure(
            (
                PSDSeries("Mass", psd),
                PSDSeries("Volume", replace(psd, basis=DistributionBasis.VOLUME)),
            )
        )


def test_difference_uses_precomputed_values_percentage_points_and_zero_reference():
    result = comparison()
    figure = build_psd_difference_figure(result)
    assert tuple(figure.data[0].y) == (0, 3, 0)
    assert "percentage points" in figure.layout.yaxis.title.text
    assert "percentage points" in figure.data[0].hovertemplate
    assert figure.layout.xaxis.type == "log"
    assert figure.layout.shapes[0].y0 == figure.layout.shapes[0].y1 == 0
    assert result.delta_psd == (0, 0.03, 0)
    # No recalculation from the snapshots: use the explicitly supplied result.
    changed = replace(result, delta_psd=(0, -0.02, 0))
    assert tuple(build_psd_difference_figure(changed).data[0].y) == (0, -2, 0)


@pytest.mark.parametrize("delta", [(), (0, 0.5), (0, float("nan"), 0), (0, 1.1, 0)])
def test_difference_rejects_invalid_precomputed_vectors(delta):
    with pytest.raises(VisualizationError):
        build_psd_difference_figure(replace(comparison(), delta_psd=delta))


def test_key_sizes_are_supplied_categories_and_readonly_percent_conversion():
    supplied = (KeyPassing(7, 0.25), KeyPassing(33, 0.75), KeyPassing(700, None))
    figure = build_key_size_comparison_figure(
        (KeySizeSeries("Baseline", supplied), KeySizeSeries("Current", supplied))
    )
    assert figure.layout.barmode == "group"
    assert figure.layout.xaxis.categoryarray == ("7 μm", "33 μm", "700 μm")
    assert tuple(figure.data[0].y) == (25, 75, None)
    assert supplied[0].cumulative_passing == 0.25


def test_key_chart_accepts_comparison_directly():
    figure = build_key_size_comparison_figure(comparison())
    assert len(figure.data) == 2
    assert tuple(figure.data[1].y) == pytest.approx((28, 100))


def test_missing_comparison_snapshots_are_explicit():
    old = ComparisonResult((1, 100), (0, 0), 0, (), 0)
    assert len(build_psd_difference_figure(old).data) == 1
    for builder in (build_psd_figure, build_key_size_comparison_figure, build_q_comparison_figure):
        with pytest.raises(VisualizationError, match="snapshots"):
            builder(old)


def test_key_sizes_require_nonempty_and_same_categories():
    with pytest.raises(VisualizationError):
        build_key_size_comparison_figure(())
    with pytest.raises(VisualizationError):
        build_key_size_comparison_figure((KeySizeSeries("A", ()),))
    with pytest.raises(VisualizationError, match="identical"):
        build_key_size_comparison_figure(
            (
                KeySizeSeries("A", (KeyPassing(1, 0.5),)),
                KeySizeSeries("B", (KeyPassing(10, 0.5),)),
            )
        )


def test_q_chart_exposes_bound_status_and_does_not_turn_failure_into_zero():
    figure = build_q_comparison_figure(
        (
            QSeries("Normal", FitResult(FitStatus.SUCCESS, 0.25)),
            QSeries("Bound", FitResult(FitStatus.AT_BOUND, 1)),
            QSeries("Failed", FitResult(FitStatus.FAILED)),
            QSeries("Weak", FitResult(FitStatus.WEAKLY_IDENTIFIED, 0.4)),
        )
    )
    assert tuple(figure.data[0].y) == (0.25, 1, None, None)
    assert tuple(figure.data[0].customdata) == (
        "success",
        "at_bound",
        "failed",
        "weakly_identified",
    )
    assert figure.data[0].marker.color[1] != figure.data[0].marker.color[0]
    assert "Bound: at_bound" in figure.layout.annotations[0].text
    assert "Failed: failed (q unavailable)" in figure.layout.annotations[0].text


def test_q_chart_accepts_comparison_and_rejects_single_q_and_nan():
    figure = build_q_comparison_figure(comparison())
    assert tuple(figure.data[0].y) == (0.25, 0.3)
    with pytest.raises(VisualizationError, match="at least two"):
        build_q_comparison_figure((QSeries("A", FitResult(FitStatus.SUCCESS, 0.2)),))
    with pytest.raises(VisualizationError, match="finite"):
        build_q_comparison_figure(
            (
                QSeries("A", FitResult(FitStatus.SUCCESS, 0.2)),
                QSeries("B", FitResult(FitStatus.SUCCESS, float("nan"))),
            )
        )
