"""Expected errors are actionable messages rather than Python tracebacks."""

import streamlit as st

from psd_analyzer.application.dto.history import HistoryError
from psd_analyzer.application.dto.workbook import ExcelImportError
from psd_analyzer.application.exceptions import AnalysisError
from psd_analyzer.domain.exceptions import DomainValidationError
from psd_analyzer.ui.streamlit_app.helpers import issue_text
from psd_analyzer.visualization import VisualizationError

USER_ERRORS = (
    ExcelImportError,
    HistoryError,
    AnalysisError,
    DomainValidationError,
    VisualizationError,
)


def show_error(error: Exception) -> None:
    """Render structured import issues individually and other expected errors clearly."""
    if isinstance(error, ExcelImportError):
        st.error(f"导入失败：发现 {len(error.issues)} 个问题。请修改后重新导入。")
        for issue in error.issues:
            st.warning(issue_text(issue))
    else:
        st.error(f"无法完成操作：{error}")
