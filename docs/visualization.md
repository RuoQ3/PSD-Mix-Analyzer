# Task 7：Plotly 可视化

可视化层只读取现有 `AnalysisResult`、`ComparisonResult`、`PSD` 或 `EvaluatedCurve`，返回 `plotly.graph_objects.Figure`。它不调用混合、插值、拟合、误差计算、Excel 或数据库；可以被未来 Streamlit 页面、Notebook 和 HTML 导出复用。

## 对外接口

```python
from psd_analyzer.visualization import (
    build_psd_figure,
    build_psd_difference_figure,
    build_key_size_comparison_figure,
    build_q_comparison_figure,
)

psd_figure = build_psd_figure(analysis_result)
comparison_figure = build_psd_figure(comparison_result)
difference_figure = build_psd_difference_figure(comparison_result)
key_figure = build_key_size_comparison_figure(comparison_result)
q_figure = build_q_comparison_figure(comparison_result)
```

`AnalysisResult` 默认显示混合曲线和可选目标曲线；没有 target 时只显示混合曲线，不以 fitted curve 替代 target。`ComparisonResult` 默认显示 baseline/current 的混合曲线。比较主图、关键粒径图与 q 图需要结果携带 `baseline`、`current` 快照；旧结果缺失快照时报 `VisualizationError`，差值图仍可直接读取已有 `delta_psd`。

如需自行决定显示原料、混合物或其他曲线，传入轻量的绘图 DTO：

```python
from psd_analyzer.visualization import PSDSeries, build_psd_figure

figure = build_psd_figure((
    PSDSeries("原料 A", material_psd, "material"),
    PSDSeries("混合 PSD", analysis_result.mixed_curve, "mixed"),
    PSDSeries("目标 PSD", analysis_result.target_curve, "target"),
))
```

`role` 支持 `material`、`mixed`、`target`、`baseline`、`current`，仅控制视觉样式。空的可选曲线被跳过。不同统计基准的 PSD 不允许直接叠加。`KeySizeSeries(name, values)` 可以传入已经计算的 `KeyPassing`；`QSeries(name, fit)` 可以传入现有 `FitResult`，用于多个批次。它们都不创建新的数学结果类型。

## 坐标与单位

- PSD 主图：X 为 μm，使用对数坐标；Y 为累计通过率 0～100%。域内的 0～1 只在新建显示数组中乘 100，原对象保持不变。
- 差值图：直接读取预先计算的 `current − baseline`；Y 的单位为**百分点**。例如域内差值 0.03 显示为 +3 个百分点。图中有零参考线，不重新相减，也不重新插值。
- 关键粒径图：分组柱状图，类别完全来自结果中的粒径列表，不写死 45、100 等节点。各组必须使用相同粒径列表；显示层不会补齐或对齐不一致的输入。
- q 图：用于至少两个分析结果。单个 q 更适合 UI 数值卡片。`AT_BOUND` 用不同颜色及明确状态显示，失败、覆盖不足、弱识别或不适用的 q 不画成有效数值，也不补零；状态保留在图下注释和 hover 中。

`None` 覆盖缺口保留为缺口，折线设置 `connectgaps=False`。可选目标不存在属于正常情况；无任何曲线、空节点、不等长、NaN、inf、非正粒径或错误累计值则明确抛出 `VisualizationError`。

## 样式与使用边界

采用白底、网格、清晰轴标题、横向图例、hover、统一边距和 `autosize=True`。混合曲线更粗，目标与基准使用虚线，current 使用独立颜色。Plotly 样式只存在于 visualization，不进入 domain。

图对象不会自行显示或写文件。调用方可使用 `figure.write_html(...)` 导出；实际宽度由未来 UI 容器控制。此阶段没有 Streamlit、SPC 控制限或历史数据库。q 的展示不代表根据 q 自动修改生产配方。

结构测试覆盖 Figure 类型、log X、trace 数量、百分数/百分点转换、关键粒径类别、可选目标、缺口、状态与输入不可变性，不依赖像素截图。
