"""Research-only editable fractions; no optimizer and no official recipe mutation."""

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.history import AnalysisType
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.domain.models.analysis_result import AnalysisResult
from psd_analyzer.ui.streamlit_app.components.analysis_controls import (
    analysis_controls,
    select_measurements,
    select_recipe,
)
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.components.recipe_editor import recipe_editor
from psd_analyzer.ui.streamlit_app.components.result_view import (
    current_result,
    remember_result,
    result_view,
    save_control,
)
from psd_analyzer.ui.streamlit_app.helpers import selection_signature


def render(container: ApplicationContainer, workbook: ImportedWorkbook) -> None:
    """Block invalid proportions before calling the simulation use case."""
    st.header("研发模拟")
    st.warning("非正式生产配方 · 仅限人工调整比例；不会改变已发布配方。")
    recipe = select_recipe(workbook, key="simulation", released=False)
    if recipe is None:
        return
    selections = select_measurements(workbook, recipe, key="simulation")
    fractions, valid = recipe_editor(container, workbook, recipe)
    profile = analysis_controls(container, key="simulation")
    signature = (
        workbook.source_hash,
        recipe,
        selection_signature(selections or {}),
        tuple(sorted(fractions.items())),
        profile,
    )
    if st.button(
        "执行研发模拟", disabled=not valid or selections is None or profile is None, type="primary"
    ):
        assert selections is not None and profile is not None
        try:
            calculated = container.workflow.simulation(
                workbook, recipe, selections, fractions, profile
            )
            remember_result("simulation", calculated, signature)
        except USER_ERRORS as error:
            show_error(error)
    result = current_result("simulation", signature)
    if isinstance(result, AnalysisResult):
        result_view(result, key="simulation")
        save_control(container, result, AnalysisType.RECIPE_SIMULATION, key="simulation")
