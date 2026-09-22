"""Render immutable results and explicitly save through Application use cases."""

from typing import cast
from uuid import uuid4

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.history import AnalysisType
from psd_analyzer.domain.models.analysis_result import AnalysisResult, ComparisonResult, FitStatus
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.helpers import key_size_rows, metric_values, number_text
from psd_analyzer.visualization import (
    PSDSeries,
    build_key_size_comparison_figure,
    build_psd_difference_figure,
    build_psd_figure,
    build_q_comparison_figure,
)


def remember_result(key: str, result: AnalysisResult | ComparisonResult, signature: object) -> None:
    """One result gets one UUID retained across reruns and save retries."""
    st.session_state[f"{key}_result"] = result
    st.session_state[f"{key}_signature"] = signature
    st.session_state[f"{key}_analysis_id"] = str(uuid4())
    st.session_state[f"{key}_saved"] = False


def current_result(key: str, signature: object) -> AnalysisResult | ComparisonResult | None:
    """Never present an old analysis as the result of changed controls."""
    if st.session_state.get(f"{key}_signature") != signature:
        if f"{key}_result" in st.session_state:
            st.info("输入已变化，请重新执行分析以更新结果。")
        return None
    return cast(AnalysisResult | ComparisonResult | None, st.session_state.get(f"{key}_result"))


def result_view(
    result: AnalysisResult, *, comparison: ComparisonResult | None = None, key: str
) -> None:
    """Use the existing Plotly builders; passing percentages are display conversion only."""
    if result.is_simulation:
        st.warning("研发模拟结果 · 非正式生产配方")
    values = metric_values(result)
    if comparison is not None:
        values["Δq · 当前 − 基准"] = number_text(comparison.delta_q)
    for column, (label, value) in zip(st.columns(len(values)), values.items(), strict=True):
        column.metric(label, value)
    st.caption("误差指标单位为累计通过率分数（0～1）；这些数值描述偏离，不作产品质量判定。")
    if result.fit.status != FitStatus.SUCCESS:
        st.warning(f"q 拟合状态：{result.fit.status.value}。{result.fit.message}")
    for diagnostic in result.diagnostics:
        st.warning(f"{diagnostic.code}：{diagnostic.message}")
    series = (
        PSDSeries(
            "Baseline PSD",
            None
            if comparison is None or comparison.baseline is None
            else comparison.baseline.mixed_curve,
            "baseline",
        ),
        PSDSeries("Mixed PSD", result.mixed_curve, "mixed"),
        PSDSeries("Target PSD", result.target_curve, "target"),
    )
    st.plotly_chart(build_psd_figure(series), width="stretch", key=f"{key}_psd")
    st.dataframe(key_size_rows(result, comparison), hide_index=True, width="stretch")
    if comparison is not None:
        for diagnostic in comparison.diagnostics:
            st.warning(f"{diagnostic.code}：{diagnostic.message}")
        st.plotly_chart(build_psd_difference_figure(comparison), width="stretch", key=f"{key}_diff")
        left, right = st.columns(2)
        left.plotly_chart(
            build_q_comparison_figure(comparison), width="stretch", key=f"{key}_qcompare"
        )
        right.plotly_chart(
            build_key_size_comparison_figure(comparison), width="stretch", key=f"{key}_keycompare"
        )
        if comparison.metrics is not None:
            st.caption(
                f"当前与基准：RMSE={comparison.metrics.rmse:.5g}；"
                f"MAE={comparison.metrics.mae:.5g}；"
                f"MaxDev={comparison.metrics.max_absolute_deviation:.5g}"
            )


def save_control(
    container: ApplicationContainer,
    result: AnalysisResult | ComparisonResult,
    analysis_type: AnalysisType,
    *,
    key: str,
) -> None:
    """No analysis is persisted without the user's explicit save action."""
    saved = bool(st.session_state.get(f"{key}_saved", False))
    if st.button("保存分析" if not saved else "已保存", disabled=saved, key=f"{key}_save"):
        try:
            record = container.save_analysis.execute(
                result, analysis_type, analysis_id=st.session_state[f"{key}_analysis_id"]
            )
            st.session_state[f"{key}_saved"] = True
            st.success(f"分析已保存：{record.analysis_id}")
        except USER_ERRORS as error:
            show_error(error)
    if saved:
        st.caption(f"记录 ID：{st.session_state[f'{key}_analysis_id']}")
