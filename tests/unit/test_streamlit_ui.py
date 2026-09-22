"""Presentation helpers and Streamlit interactions without pixel assertions."""

from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from psd_analyzer.application.dto.workbook import ImportIssue
from psd_analyzer.domain.models.recipe import RecipeStatus
from psd_analyzer.ui.streamlit_app.composition import build_container
from psd_analyzer.ui.streamlit_app.helpers import (
    issue_text,
    key_size_rows,
    measurement_options,
    metric_values,
    recipe_rows,
)


@pytest.fixture
def ui_data(tmp_path):
    container = build_container(tmp_path / "ui.db")
    workbook = container.import_workbook.execute(
        container.generate_template.execute(), "sample.xlsx"
    )
    released = replace(
        workbook.recipes[0],
        status=RecipeStatus.RELEASED,
        approval_reference="test-external-approval",
    )
    workbook = replace(workbook, recipes=(released,))
    choices = {"EX-LINE-A": "EX-PSD-A", "EX-LINE-B": "EX-PSD-B"}
    profile = container.workflow.profile(1, 625, key_sizes="16,81,256")
    result = container.workflow.production(workbook, released, choices, profile)
    return container, workbook, result


def page_test(tmp_path, workbook, page):
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from psd_analyzer.ui.streamlit_app.composition import build_container\n"
        f"from psd_analyzer.ui.streamlit_app.pages.{page} import render\n"
        f"container = build_container({str(tmp_path / 'ui.db')!r})\n"
        "render(container, st.session_state['book'])\n"
    )
    app.session_state["book"] = workbook
    return app.run(timeout=30)


def test_issue_text_preserves_file_sheet_row_column_and_value():
    issue = ImportIssue(
        "input.xlsx", "PSD", 18, "cumulative_passing_pct", 118, "range", "合法范围 0～100"
    )
    text = issue_text(issue)
    for part in ("input.xlsx", "PSD", "18", "cumulative_passing_pct", "118", "0～100", "range"):
        assert part in text


def test_metrics_without_target_and_key_table_without_baseline(ui_data):
    _, workbook, result = ui_data
    values = metric_values(result)
    assert values["Equivalent q"] == "0.25"
    assert all("Target q" not in label for label in values)
    assert any("拟合曲线" in label for label in values)
    rows = key_size_rows(result)
    assert [row["粒径 μm"] for row in rows] == [16, 81, 256]
    assert all("基准通过率" not in row for row in rows)
    assert recipe_rows(workbook.recipes[0], workbook)[0]["正式比例 %"] == 25
    assert tuple(measurement_options(workbook, "EX-A")) == ("EX-PSD-A",)


def test_production_page_has_no_editable_recipe_fractions(tmp_path, ui_data):
    _, workbook, _ = ui_data
    app = page_test(tmp_path, workbook, "production_monitor")
    assert not app.exception
    assert len(app.get("data_editor")) == 0
    assert all("比例" not in widget.label for widget in app.number_input)
    assert "正式比例只读" in " ".join(item.value for item in app.caption)
    assert workbook.recipes[0].lines[0].mass_fraction == 0.25


def test_production_disallows_draft_without_inventing_approval(tmp_path, ui_data):
    _, workbook, _ = ui_data
    draft = replace(workbook.recipes[0], status=RecipeStatus.DRAFT, approval_reference="")
    app = page_test(tmp_path, replace(workbook, recipes=(draft,)), "production_monitor")
    assert not app.exception
    assert any("没有可用的已发布配方" in item.value for item in app.warning)
    assert not app.button


def test_invalid_simulation_fraction_disables_run(tmp_path, ui_data):
    _, workbook, _ = ui_data
    app = page_test(tmp_path, workbook, "recipe_simulation")
    assert not app.exception
    assert not next(button for button in app.button if button.label == "执行研发模拟").disabled
    recipe = workbook.recipes[0]
    key = f"simulation_editor_{workbook.source_hash}_{recipe.recipe_id}_{recipe.version}"
    app.session_state[key] = {
        "edited_rows": {0: {"模拟比例 %": 20.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run(timeout=30)
    assert not app.exception
    assert next(button for button in app.button if button.label == "执行研发模拟").disabled
    assert any("100%" in item.value for item in app.error)
    assert workbook.recipes[0].lines[0].mass_fraction == 0.25


def test_result_without_optional_target_or_baseline_renders(ui_data):
    _, _, result = ui_data
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from psd_analyzer.ui.streamlit_app.components.result_view import result_view\n"
        "result_view(st.session_state['result'], key='test')\n"
    )
    app.session_state["result"] = result
    app.run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 4
    assert len(app.get("plotly_chart")) == 1


def test_comparison_main_plot_keeps_optional_target(ui_data, monkeypatch):
    container, workbook, result = ui_data
    profile = replace(result.profile, target_q=0.3)
    choices = {"EX-LINE-A": "EX-PSD-A", "EX-LINE-B": "EX-PSD-B"}
    target_result = container.workflow.production(workbook, workbook.recipes[0], choices, profile)
    comparison = container.workflow.compare_baseline(target_result, target_result)
    from psd_analyzer.ui.streamlit_app.components import result_view as module

    figures = []
    original = module.build_psd_figure

    def capture(data):
        figure = original(data)
        figures.append(figure)
        return figure

    monkeypatch.setattr(module, "build_psd_figure", capture)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from psd_analyzer.ui.streamlit_app.components.result_view import result_view\n"
        "result_view(st.session_state['result'], "
        "comparison=st.session_state['comparison'], key='test')\n"
    )
    app.session_state["result"] = target_result
    app.session_state["comparison"] = comparison
    app.run(timeout=30)
    assert not app.exception
    assert len(figures[0].data) == 3
    assert {trace.name for trace in figures[0].data} == {"Baseline PSD", "Mixed PSD", "Target PSD"}


def test_home_entry_point_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("PSD_ANALYZER_DB", str(tmp_path / "app.db"))
    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/psd_analyzer/ui/streamlit_app/app.py"))
    app.run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "PSD Mix Analyzer"
    assert any("不代表产品性能" in info.value for info in app.info)


def test_save_is_explicit_and_reuses_result_uuid(tmp_path, ui_data):
    container, _, result = ui_data
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from psd_analyzer.application.dto.history import AnalysisType\n"
        "from psd_analyzer.ui.streamlit_app.composition import build_container\n"
        "from psd_analyzer.ui.streamlit_app.components.result_view "
        "import remember_result, save_control\n"
        f"container = build_container({str(tmp_path / 'ui.db')!r})\n"
        "if 'test_analysis_id' not in st.session_state:\n"
        "    remember_result('test', st.session_state['result'], 'input')\n"
        "save_control(container, st.session_state['result'], "
        "AnalysisType.PRODUCTION_MONITORING, key='test')\n"
    )
    app.session_state["result"] = result
    app.run(timeout=30)
    identifier = app.session_state["test_analysis_id"]
    assert container.list_history.execute() == ()
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert len(container.list_history.execute()) == 1
    app.run(timeout=30)
    assert app.button[0].disabled
    assert app.session_state["test_analysis_id"] == identifier
    assert len(container.list_history.execute()) == 1


@pytest.mark.parametrize(
    ("page", "button_label", "expected_type"),
    [
        ("production_monitor", "执行生产监控分析", "production_monitoring"),
        ("substitution_analysis", "执行替代风险分析", "material_substitution"),
        ("recipe_simulation", "执行研发模拟", "recipe_simulation"),
    ],
)
def test_analysis_pages_execute_and_save_explicitly(
    tmp_path, ui_data, page, button_label, expected_type
):
    container, workbook, _ = ui_data
    app = page_test(tmp_path, workbook, page)
    next(button for button in app.button if button.label == button_label).click().run(timeout=30)
    assert not app.exception
    assert len(app.get("plotly_chart")) >= 1
    assert container.list_history.execute() == ()
    next(button for button in app.button if button.label == "保存分析").click().run(timeout=30)
    assert not app.exception
    summaries = container.list_history.execute()
    assert len(summaries) == 1
    assert summaries[0].analysis_type.value == expected_type
    if page == "production_monitor":
        app.number_input[0].set_value(2.0).run(timeout=30)
        assert not app.exception
        assert any("输入已变化" in message.value for message in app.info)
        assert len(app.get("plotly_chart")) == 0
        assert not any(button.label == "保存分析" for button in app.button)


def test_history_page_lists_detail_and_sets_baseline(tmp_path, ui_data):
    from uuid import uuid4

    from psd_analyzer.application.dto.history import AnalysisType

    container, _, result = ui_data
    saved = container.save_analysis.execute(
        result, AnalysisType.PRODUCTION_MONITORING, analysis_id=str(uuid4())
    )
    app = AppTest.from_string(
        "from psd_analyzer.ui.streamlit_app.composition import build_container\n"
        "from psd_analyzer.ui.streamlit_app.pages.history_analysis import render\n"
        f"render(build_container({str(tmp_path / 'ui.db')!r}))\n"
    ).run(timeout=30)
    assert not app.exception
    assert len(app.get("plotly_chart")) >= 2
    next(button for button in app.button if "设为" in button.label).click().run(timeout=30)
    assert not app.exception
    assert (
        container.get_baseline.execute(result.recipe.recipe_id, result.recipe.version).analysis_id
        == saved.analysis_id
    )
