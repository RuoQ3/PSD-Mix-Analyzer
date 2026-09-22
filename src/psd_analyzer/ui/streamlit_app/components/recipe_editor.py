"""Only the research page exposes editable fractions."""

from typing import cast

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.domain.models.recipe import RecipeVersion
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.helpers import recipe_rows


def recipe_editor(
    container: ApplicationContainer, workbook: ImportedWorkbook, recipe: RecipeVersion
) -> tuple[dict[str, float], bool]:
    """Application checks fractions; invalid totals keep the run button disabled."""
    rows = [dict(row, **{"模拟比例 %": row["正式比例 %"]}) for row in recipe_rows(recipe, workbook)]
    edited = cast(
        list[dict[str, str | float]],
        st.data_editor(
            rows,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            disabled=["行 ID", "原料", "原料 ID", "正式比例 %"],
            column_config={"模拟比例 %": st.column_config.NumberColumn(required=True, step=0.1)},
            key=f"simulation_editor_{workbook.source_hash}_{recipe.recipe_id}_{recipe.version}",
        ),
    )
    try:
        fractions = {str(row["行 ID"]): float(row["模拟比例 %"]) for row in edited}
        container.workflow.validate_simulation_fractions(tuple(fractions.values()))
    except USER_ERRORS as error:
        show_error(error)
        return {}, False
    except (ValueError, TypeError):
        st.error("模拟比例必须填写有效数值。")
        return {}, False
    st.caption("模拟比例校验通过；未对输入进行自动归一化。")
    return fractions, True
