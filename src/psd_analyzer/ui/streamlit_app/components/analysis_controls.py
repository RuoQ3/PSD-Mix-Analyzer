"""Recipe, measurement and numerical-configuration input widgets."""

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.models.recipe import RecipeStatus, RecipeVersion
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.helpers import measurement_options, recipe_rows


def select_recipe(workbook: ImportedWorkbook, *, key: str, released: bool) -> RecipeVersion | None:
    """Production never promotes imported draft recipes to released status."""
    choices = tuple(
        r for r in workbook.recipes if not released or r.status == RecipeStatus.RELEASED
    )
    if not choices:
        st.warning(
            "没有可用的已发布配方。生产与替代分析需要 status=released 且有外部 "
            "approval_reference；草稿可进入研发模拟。"
            if released
            else "工作簿没有配方。"
        )
        return None
    selected = st.selectbox(
        "选择配方",
        range(len(choices)),
        key=f"{key}_recipe",
        format_func=lambda i: (
            f"{choices[i].name} · {choices[i].version} ({choices[i].status.value})"
        ),
    )
    recipe = choices[selected]
    st.dataframe(recipe_rows(recipe, workbook), hide_index=True, width="stretch")
    st.caption(f"配方 {recipe.recipe_id} · {recipe.version}；正式比例只读。")
    return recipe


def select_measurements(
    workbook: ImportedWorkbook, recipe: RecipeVersion, *, key: str
) -> dict[str, str] | None:
    """Select a batch/measurement for each fixed recipe line."""
    selections: dict[str, str] = {}
    missing = False
    for line in recipe.lines:
        options = measurement_options(workbook, line.material_id)
        if not options:
            st.warning(f"配方行 {line.line_id} / {line.material_id} 没有可选 PSD。")
            missing = True
            continue
        selections[line.line_id] = st.selectbox(
            f"原料批次 · {line.line_id}",
            tuple(options),
            format_func=options.__getitem__,
            key=f"{key}_{recipe.recipe_id}_{recipe.version}_{line.line_id}_measurement",
        )
    return None if missing else selections


def analysis_controls(container: ApplicationContainer, *, key: str) -> AnalysisProfile | None:
    """Delegate parameter validation and profile construction to Application."""
    left, right = st.columns(2)
    d_min = left.number_input("D_min (μm)", min_value=0.000001, value=1.0, key=f"{key}_dmin")
    d_max = right.number_input("D_max (μm)", min_value=0.000001, value=1000.0, key=f"{key}_dmax")
    target_enabled = st.checkbox("设置目标 q（参考曲线）", key=f"{key}_target_enabled")
    target_q = (
        st.number_input("Target q", min_value=0.000001, value=0.25, key=f"{key}_target_q")
        if target_enabled
        else None
    )
    with st.expander("高级设置"):
        method = st.selectbox("插值方法", ("log-linear", "linear"), key=f"{key}_interpolation")
        left, right = st.columns(2)
        q_min = left.number_input("q 下界", min_value=0.000001, value=0.05, key=f"{key}_q_min")
        q_max = right.number_input("q 上界", min_value=0.000001, value=1.0, key=f"{key}_q_max")
        sizes = st.text_input(
            "关键粒径 μm（逗号分隔）", "10,45,75,100,500,1000", key=f"{key}_sizes"
        )
    try:
        return container.workflow.profile(
            d_min_um=d_min,
            d_max_um=d_max,
            interpolation=method,
            q_min=q_min,
            q_max=q_max,
            target_q=target_q,
            key_sizes=sizes,
        )
    except USER_ERRORS as error:
        show_error(error)
        return None
