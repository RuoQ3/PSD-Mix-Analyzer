"""Fixed-recipe production monitoring; fractions are never editable here."""

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.history import AnalysisType
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.domain.models.analysis_result import AnalysisResult, ComparisonResult
from psd_analyzer.ui.streamlit_app.components.analysis_controls import (
    analysis_controls,
    select_measurements,
    select_recipe,
)
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.components.result_view import (
    current_result,
    remember_result,
    result_view,
    save_control,
)
from psd_analyzer.ui.streamlit_app.helpers import selection_signature


def render(container: ApplicationContainer, workbook: ImportedWorkbook) -> None:
    """Analyze selected batches with an externally released recipe's fixed proportions."""
    st.header("生产监控")
    st.info("正式配方比例固定。更换批次用于观察级配变化，不会修改生产配方。")
    recipe = select_recipe(workbook, key="production", released=True)
    if recipe is None:
        return
    selections = select_measurements(workbook, recipe, key="production")
    profile = analysis_controls(container, key="production")
    signature = (workbook.source_hash, recipe, selection_signature(selections or {}), profile)
    if st.button(
        "执行生产监控分析", disabled=selections is None or profile is None, type="primary"
    ):
        assert selections is not None and profile is not None
        try:
            with st.spinner("正在分析…"):
                calculated = container.workflow.production(workbook, recipe, selections, profile)
            remember_result("production", calculated, signature)
        except USER_ERRORS as error:
            show_error(error)
    result = current_result("production", signature)
    if not isinstance(result, AnalysisResult):
        return
    comparison: ComparisonResult | None = None
    try:
        baseline = container.get_baseline.execute(recipe.recipe_id, recipe.version)
        if baseline is not None:
            comparison = container.workflow.compare_baseline(baseline.current, result)
            st.caption(f"显式指定的历史基准：{baseline.analysis_id}")
        else:
            st.caption("尚未设置基准。可保存分析后，在历史页显式设置。")
    except USER_ERRORS as error:
        st.warning(f"基准暂不可比较；当前分析仍可查看和保存。{error}")
    result_view(result, comparison=comparison, key="production")
    save_control(container, result, AnalysisType.PRODUCTION_MONITORING, key="production")
