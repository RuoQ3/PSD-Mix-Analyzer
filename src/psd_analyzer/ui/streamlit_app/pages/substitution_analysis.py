"""Explicit material replacement at unchanged recipe proportions."""

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.history import AnalysisType
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.domain.models.analysis_result import ComparisonResult
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
from psd_analyzer.ui.streamlit_app.helpers import measurement_options, selection_signature


def render(container: ApplicationContainer, workbook: ImportedWorkbook) -> None:
    """Call the existing substitution use case and render its comparison snapshot."""
    st.header("原料替代分析")
    st.warning("这是风险分析，不是正式配方变更。原始与候选原料的配方比例保持不变。")
    recipe = select_recipe(workbook, key="substitution", released=True)
    if recipe is None:
        return
    selections = select_measurements(workbook, recipe, key="substitution")
    line_id = st.selectbox("要替代的配方行", tuple(line.line_id for line in recipe.lines))
    options = measurement_options(workbook)
    if not options:
        st.warning("没有候选原料 PSD。")
        return
    candidate = st.selectbox("候选原料批次 / PSD", tuple(options), format_func=options.__getitem__)
    replacements = {line_id: candidate}
    profile = analysis_controls(container, key="substitution")
    signature = (
        workbook.source_hash,
        recipe,
        selection_signature(selections or {}),
        selection_signature(replacements),
        profile,
    )
    if st.button(
        "执行替代风险分析", disabled=selections is None or profile is None, type="primary"
    ):
        assert selections is not None and profile is not None
        try:
            calculated = container.workflow.substitute(
                workbook, recipe, selections, replacements, profile
            )
            remember_result("substitution", calculated, signature)
        except USER_ERRORS as error:
            show_error(error)
    result = current_result("substitution", signature)
    if isinstance(result, ComparisonResult) and result.current is not None:
        result_view(result.current, comparison=result, key="substitution")
        save_control(container, result, AnalysisType.MATERIAL_SUBSTITUTION, key="substitution")
