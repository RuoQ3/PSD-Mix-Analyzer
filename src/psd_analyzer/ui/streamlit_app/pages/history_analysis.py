"""History lists use summaries; full snapshots load only for selected records."""

from datetime import UTC, date, datetime, time

import streamlit as st

from psd_analyzer.application.dto.container import ApplicationContainer
from psd_analyzer.application.dto.history import AnalysisType, HistoryFilter
from psd_analyzer.domain.models.analysis_result import ComparisonResult
from psd_analyzer.ui.streamlit_app.components.error_view import USER_ERRORS, show_error
from psd_analyzer.ui.streamlit_app.components.result_view import result_view
from psd_analyzer.ui.streamlit_app.helpers import number_text
from psd_analyzer.visualization import build_q_trend_figure

TYPE_LABELS = {
    AnalysisType.PRODUCTION_MONITORING: "生产监控",
    AnalysisType.MATERIAL_SUBSTITUTION: "原料替代",
    AnalysisType.RECIPE_SIMULATION: "研发模拟",
}


def render(container: ApplicationContainer) -> None:
    """Filter, inspect, compare and explicitly select a production baseline."""
    st.header("历史分析")
    st.caption("历史数据是分析记录，不是正式产品质量判定数据库。所有时间显示为 UTC。")
    with st.expander("历史筛选", expanded=True):
        left, right = st.columns(2)
        recipe_id = left.text_input("Recipe ID（空白为全部）").strip()
        batch_no = right.text_input("原料批号（空白为全部）").strip()
        selected_type = st.selectbox(
            "分析类型",
            (None, *AnalysisType),
            format_func=lambda value: "全部" if value is None else TYPE_LABELS[value],
        )
        date_from: datetime | None = None
        date_to: datetime | None = None
        if st.checkbox("按日期范围筛选（UTC）"):
            left, right = st.columns(2)
            start = left.date_input("开始日期", value=date.today(), key="history_start")
            end = right.date_input("结束日期", value=date.today(), key="history_end")
            if not isinstance(start, date) or not isinstance(end, date):
                st.info("请选择开始和结束日期。")
                return
            if start > end:
                st.error("开始日期不能晚于结束日期。")
                return
            date_from = datetime.combine(start, time.min, tzinfo=UTC)
            date_to = datetime.combine(end, time.max, tzinfo=UTC)
    try:
        summaries = container.list_history.execute(
            HistoryFilter(
                recipe_id=recipe_id or None,
                batch_no=batch_no or None,
                analysis_type=selected_type,
                date_from=date_from,
                date_to=date_to,
            )
        )
    except USER_ERRORS as error:
        show_error(error)
        return
    if not summaries:
        st.info("当前筛选条件下没有已保存的分析。分析完成后点击“保存分析”即可在这里查看。")
        return
    st.caption(f"显示 {len(summaries)} 条记录（最多 1000 条；可缩小筛选范围）。")
    st.dataframe(
        [
            {
                "记录 ID": summary.analysis_id,
                "时间 UTC": summary.created_at.isoformat(),
                "配方": f"{summary.recipe_name} / {summary.recipe_id} / {summary.recipe_version}",
                "类型": TYPE_LABELS[summary.analysis_type],
                "Equivalent q": number_text(summary.equivalent_q),
                "Target q": number_text(summary.target_q),
                "RMSE": number_text(summary.rmse),
                "MAE": number_text(summary.mae),
                "Max deviation": number_text(summary.max_absolute_deviation),
                "基准": "是" if summary.is_baseline else "",
            }
            for summary in summaries
        ],
        hide_index=True,
        width="stretch",
    )
    st.plotly_chart(build_q_trend_figure(summaries), width="stretch", key="history_q_trend")
    labels = {
        item.analysis_id: (
            f"{item.created_at.isoformat()} · {item.recipe_name} {item.recipe_version} · "
            f"{TYPE_LABELS[item.analysis_type]} · {item.analysis_id}"
        )
        for item in summaries
    }
    selected_id = st.selectbox("查看记录详情", tuple(labels), format_func=labels.__getitem__)
    try:
        detail = container.get_detail.execute(selected_id)
        result = detail.current
        comparison = detail.result if isinstance(detail.result, ComparisonResult) else None
        st.subheader("已保存的分析快照")
        recipe = result.recipe
        if recipe is not None:
            st.caption(f"配方 {recipe.recipe_id} / {recipe.version} · {recipe.status.value}")
        st.dataframe(
            [
                {
                    "配方行": component.line_id,
                    "原料 ID": component.batch.material_id,
                    "批号": component.batch.batch_no,
                    "供应商": component.batch.supplier,
                    "PSD": component.measurement.psd_id,
                    "PSD 版本": component.measurement.version,
                    "比例 %": component.mass_fraction * 100,
                }
                for component in result.components
            ],
            hide_index=True,
            width="stretch",
        )
        with st.expander("当次分析配置"):
            profile = result.profile
            st.json(
                {
                    "profile_id": profile.profile_id,
                    "version": profile.version,
                    "d_min_um": profile.d_min_um,
                    "d_max_um": profile.d_max_um,
                    "interpolation": profile.interpolation.value,
                    "tail_policy": profile.tail_policy.value,
                    "model": profile.model_id,
                    "loss": profile.loss_id,
                    "q_bounds": list(profile.q_bounds),
                    "target_q": profile.target_q,
                    "key_sizes_um": list(profile.key_sizes_um),
                    "algorithm_version": result.algorithm_version,
                }
            )
        result_view(result, comparison=comparison, key="history_detail")
        if detail.analysis_type == AnalysisType.PRODUCTION_MONITORING:
            if detail.is_baseline:
                st.info("该记录是此配方版本的当前基准。")
            elif st.button("将该记录设为此配方版本的基准", key=f"baseline_{selected_id}"):
                container.set_baseline.execute(selected_id)
                st.rerun()
        other_ids = tuple(item.analysis_id for item in summaries if item.analysis_id != selected_id)
        if other_ids:
            baseline_id = st.selectbox(
                "选择历史比较基准", other_ids, format_func=labels.__getitem__
            )
            if st.button("比较两条历史分析"):
                historical = container.compare_history.execute(baseline_id, selected_id)
                assert historical.current is not None
                result_view(historical.current, comparison=historical, key="history_compare")
    except USER_ERRORS as error:
        show_error(error)
