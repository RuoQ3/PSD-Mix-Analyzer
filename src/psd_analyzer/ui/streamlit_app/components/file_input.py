"""File upload delegates every read and validation step to Application."""

from typing import cast

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.workbook import ImportedWorkbook
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error


def workbook_input(container: ApplicationContainer) -> ImportedWorkbook | None:
    """Import on an explicit button, preserving the last valid workbook in session."""
    with st.expander("Excel 数据与模板", expanded="workbook" not in st.session_state):
        st.caption("模板含 Materials、Measurements、PSD、Recipe；示例配方默认为研发草稿。")
        if st.button("准备 Excel 模板", key="prepare_template"):
            try:
                st.session_state["template_bytes"] = container.generate_template.execute()
            except USER_ERRORS as error:
                show_error(error)
        if "template_bytes" in st.session_state:
            st.download_button(
                "下载 Excel 模板",
                st.session_state["template_bytes"],
                file_name="psd_mix_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        uploaded = st.file_uploader("上传 Excel (.xlsx)", type=["xlsx"], key="workbook_upload")
        if st.button("导入工作簿", disabled=uploaded is None):
            assert uploaded is not None
            try:
                imported = container.import_workbook.execute(uploaded.getvalue(), uploaded.name)
                st.session_state["workbook"] = imported
                st.session_state["workbook_name"] = uploaded.name
                st.success("工作簿校验通过。")
            except USER_ERRORS as error:
                show_error(error)
        if "workbook" in st.session_state:
            st.caption(f"当前数据：{st.session_state.get('workbook_name', '已导入工作簿')}")
    workbook = cast(ImportedWorkbook | None, st.session_state.get("workbook"))
    if workbook is None:
        st.info("请先导入工作簿；也可在历史分析页查看已保存记录。")
    return workbook
