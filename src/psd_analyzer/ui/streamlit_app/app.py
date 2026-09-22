"""Run with: streamlit run src/psd_analyzer/ui/streamlit_app/app.py."""

from collections.abc import Callable

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.components.file_input import workbook_input
from psd_analyzer.ui.streamlit_app.composition import build_container
from psd_analyzer.ui.streamlit_app.pages import (
    history_analysis,
    production_monitor,
    recipe_simulation,
    substitution_analysis,
)


def home(container: ApplicationContainer) -> None:
    """Project scope and a short workflow, with no invented quality-control limits."""
    st.title("PSD Mix Analyzer")
    st.write("多原料粒度分布分析与颗粒级配监控系统")
    st.info("q 值用于级配分析和波动监控，不代表产品性能，不应单独作为现场修改配方依据。")
    st.markdown(
        "**生产监控**：固定正式配方，选择当前批次，查看混合 PSD 与等效 q。\n\n"
        "**原料替代**：保持比例不变，对比原始和候选原料的级配差异。\n\n"
        "**研发模拟**：人工调整比例，所有结果明确标记为非正式生产配方。\n\n"
        "**历史分析**：查看显式保存的记录、设置基准并观察 q 的时间趋势。"
    )
    st.caption("推荐流程：导入 Excel → 选择页面与配方 → 执行分析 → 查看结果 → 显式保存。")
    workbook_input(container)


def data_page(
    container: ApplicationContainer,
    renderer: Callable[[ApplicationContainer, ImportedWorkbook], None],
) -> None:
    """Shared import panel delegates to Application before a thin page controller."""
    workbook = workbook_input(container)
    if workbook is not None:
        renderer(container, workbook)


def main() -> None:
    """Composition is isolated; navigation contains only presentation callables."""
    st.set_page_config(page_title="PSD Mix Analyzer", page_icon="📊", layout="wide")
    try:
        container = build_container()
        navigation = st.navigation(
            [
                st.Page(lambda: home(container), title="首页", default=True, url_path="home"),
                st.Page(
                    lambda: data_page(container, production_monitor.render),
                    title="生产监控",
                    url_path="production",
                ),
                st.Page(
                    lambda: data_page(container, substitution_analysis.render),
                    title="原料替代",
                    url_path="substitution",
                ),
                st.Page(
                    lambda: data_page(container, recipe_simulation.render),
                    title="研发模拟",
                    url_path="simulation",
                ),
                st.Page(
                    lambda: history_analysis.render(container), title="历史分析", url_path="history"
                ),
            ]
        )
        st.sidebar.caption("质量分数混合 · μm · Domain 通过率 0～1")
        st.sidebar.caption("范围外 PSD 使用恒定端点延伸；目标 q 不是控制限。")
        navigation.run()
    except USER_ERRORS as error:
        show_error(error)


if __name__ == "__main__":
    main()
