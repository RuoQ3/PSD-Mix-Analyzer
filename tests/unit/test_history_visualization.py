"""Trend builders consume read models and never join incompatible numerical conventions."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psd_analyzer.application.dto.history import AnalysisSummary, AnalysisType
from psd_analyzer.domain.models.analysis_result import FitStatus
from psd_analyzer.visualization import build_q_trend_figure


def summary():
    return AnalysisSummary(
        str(uuid4()),
        datetime(2026, 9, 22, tzinfo=UTC),
        AnalysisType.PRODUCTION_MONITORING,
        "R",
        "Recipe",
        "1",
        0.25,
        None,
        0.01,
        0.005,
        0.02,
        False,
        FitStatus.SUCCESS,
        "configuration-a",
    )


def test_empty_trend_has_no_invented_measurements():
    figure = build_q_trend_figure(())
    assert not figure.data
    assert figure.layout.annotations


def test_trend_sorts_times_and_keeps_missing_values():
    first = summary()
    later = replace(
        first,
        analysis_id=str(uuid4()),
        created_at=first.created_at + timedelta(days=1),
        equivalent_q=None,
        fit_status=FitStatus.FAILED,
    )
    figure = build_q_trend_figure((later, first))
    assert tuple(figure.data[0].x) == (first.created_at, later.created_at)
    assert tuple(figure.data[0].y) == (0.25, None)
    assert figure.data[0].connectgaps is False
    assert figure.layout.xaxis.type == "date"


def test_boundary_fit_keeps_status_and_target_is_reference():
    item = replace(summary(), fit_status=FitStatus.AT_BOUND, equivalent_q=0.05, target_q=0.3)
    figure = build_q_trend_figure((item,))
    assert tuple(figure.data[0].customdata) == ("at_bound",)
    assert "reference" in figure.data[1].name
    assert not figure.layout.shapes


def test_changed_profiles_do_not_share_a_connected_series():
    first = summary()
    changed = replace(first, analysis_id=str(uuid4()), convention_key="configuration-b")
    figure = build_q_trend_figure((first, changed))
    assert len(figure.data) == 2
    assert all(len(trace.y) == 1 for trace in figure.data)
