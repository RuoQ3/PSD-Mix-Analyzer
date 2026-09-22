# Task 6：Application 用例

应用层接收已经合法的领域对象，校验业务选择、编排现有数学服务并返回结构化结果。它不实现数学公式，不读取 Excel，不绘图或持久化。领域层不反向依赖应用层。

## 输入与输出

沿用 `RecipeVersion`、`MixtureComponent`、`AnalysisProfile`。调用方显式选择每条配方行的批次和测量；用例不根据名称猜测批次，不擅自使用“最新测量”。Excel 导入返回的材料、批次、测量和配方可以用来构造这些输入。

```python
from psd_analyzer.application.use_cases import (
    AnalyzeRecipePSD,
    ComparePSDAnalysis,
    CompareMaterialSubstitution,
    SimulateRecipe,
)

result = AnalyzeRecipePSD().execute(recipe, components, profile)
comparison = ComparePSDAnalysis().execute(recipe, baseline_components, current_components, profile)
substitution = CompareMaterialSubstitution().execute(
    recipe, original_components, {"line-A": replacement_component}, profile
)
simulation = SimulateRecipe().execute(draft_recipe, simulation_components, profile)
```

这些入口都接受 `fit_enabled=False`，用于只混合、查询和评价用户目标；此时拟合状态为 `NOT_APPLICABLE`，等效 q 为 None。

复用既有 `AnalysisResult`，未创建新的同义结果类型：

| 字段／属性 | 含义 |
|---|---|
| recipe | 不可变配方快照，包含 recipe_id、name、version |
| is_simulation | 研发模拟明确为 True |
| mixed_curve / mixed_psd | 已计算累计曲线／完整 PSD；旧结果覆盖不全时 mixed_psd 为 None |
| fit / equivalent_q | 实际混合 PSD 的拟合结果／等效 q |
| profile.target_q / target_q | 用户指定的目标 q |
| fitted_curve / fit_metrics | 等效 q 对应模型曲线／拟合范围内指标 |
| target_curve / target_psd / target_metrics | 用户目标曲线／PSD／与混合曲线的指标 |
| key_passing | 由 profile.key_sizes_um 指定的累计通过率 |
| profile | 插值方法、模型标识、粒径边界、q 范围和尾部策略等配置 |
| components / actual_weights / input_fraction_sum | 输入测量快照、实际权重与原始比例和 |

**equivalent_q 与 target_q 独立。** 未提供 target_q 时，target_curve、target_psd、target_metrics 都为 None，不以最佳拟合曲线冒充用户目标。拟合指标只评价 `[Dmin,Dmax]` 内节点；目标指标评价整个混合计算网格，范围外目标按模型规则为 0/1，二者口径有明确区别。

## 固定配方与模拟

`AnalyzeRecipePSD` 要求 Released 配方，沿用 `validate_selection` 校验配方行、材料归属和原始质量比例。缺少正比例组分的 PSD 抛 `MissingMaterialPSD`，重复选择或比例修改仍抛可识别的 `RecipeLockedError`。

`SimulateRecipe` 仅接受 Draft，返回 `is_simulation=True`；用户可自行指定 Draft 比例，但其选定组分必须与该 Draft 一致。用例不修改来源配方。若从正式配方创建研发副本，可先调用已有 `create_simulation_recipe`，该函数要求新的场景身份。Excel 导入默认产生 Draft，应使用模拟入口；此阶段没有生产配方发布功能。

## 批次比较与替代

`ComparePSDAnalysis` 的两组选料必须使用同一个 Released 配方和相同比例，每条配方行的材料身份也必须相同。供应商、批次、测量版本可以变化；测量协议仍须满足已有比较约束。

`CompareMaterialSubstitution` 只替换映射中指定的行，允许替代材料身份不同，其余组分保持原样。替代组分必须具有同一行 ID 和同一质量分数，不会重分配其他材料比例。

比较先用双方所有 PSD 建立一个共同网格，再分别混合和拟合，避免在两个不同网格上估计 q 后直接比较。默认是双方实测节点并集；因此一份批次在不同的配对分析中可能采用不同节点权重。跨历史结果比较时应显式注入相同的固定网格策略，并保留一致配置，不将不同网格的 q 混为一条历史指标。

复用 `ComparisonResult`，增加 baseline、current 分析快照以及 metrics；既有 delta_psd、delta_q、key_delta 继续表示 **current − baseline**。RMSE、MAE、MaxDev 等均来自唯一的领域指标函数。只有双方均为成功的区间内拟合才给出 delta_q；边界解或失败保留诊断，不伪造差值。

## 配置与依赖注入

配置沿用纯数据 `AnalysisProfile`，不存服务实例。默认插值策略是 `LogLinearInterpolator`，注入策略的 method_id / model_id / loss_id 必须与 profile 一致。

```python
from dataclasses import replace
from psd_analyzer.domain.models.analysis_profile import InterpolationMethod, TailPolicy
from psd_analyzer.domain.services.interpolation import LinearInterpolator

linear_profile = replace(profile, interpolation=InterpolationMethod.LINEAR, tail_policy=TailPolicy.CLAMP)
analyzer = AnalyzeRecipePSD(interpolator=LinearInterpolator())
comparison_case = ComparePSDAnalysis(analyzer=analyzer)
result = analyzer.execute(recipe, components, linear_profile)
```

AnalyzeRecipePSD 构造器可注入 grid_builder、interpolator、model、loss、mixing_factory、q_fitter、metrics_service、key_size_evaluator。小型 factory 将所选网格和尾部策略绑定到已有 Task 3 混合服务；配对分析复用同一 analyzer。应用测试使用 fake 服务验证调用顺序，无需重复测试数学实现。

本阶段应用用例明确只支持 MASS，不进行密度换算。profile 原默认尾部策略仍为 CONFIRMED；不同原料范围不足时，Task 3 会抛 CoverageError。若分析目的允许端点常数延续，应显式选择 CLAMP，不静默修改配置。原有 `analyze_mixture` 固定对数评价网格及体积分析能力保留，未被这些新入口替换。

## 异常与依赖边界

应用只增加少量 `AnalysisError` 子类：`MissingMaterialPSD`、`InvalidAnalysisConfiguration`；DomainValidationError、RecipeLockedError、CoverageError 等保留其具体类型。拟合数值失败保留为 FitResult 状态和诊断，混合结果仍可返回。没有 `except Exception` 式统一吞错。

代码位于既有 `application/use_cases` 和 `application/ports`。Plotly 属于独立可选依赖；Application 不导入 Plotly、Streamlit、Excel、数据库、NumPy 或 SciPy 的计算接口。

完整示例：`python examples/application_visualization_demo.py`。加 `--output-dir data/demo_figures` 可导出独立交互 HTML；绘图由调用方执行，不在 use case 内执行。

## Task 8 / Task 9 的调用边界

`WorkbookAnalysis` 将已导入工作簿、配方、逐行 PSD 选择和配置传入上述既有用例。
`ImportWorkbook` / `GenerateWorkbookTemplate` 依赖 `WorkbookGateway` Protocol，
页面无需导入 Excel infrastructure。默认 UI profile 显式采用 clamp，不改动 Task 6 的默认约定。

`SaveAnalysis`、`ListAnalysisHistory`、`GetAnalysisDetail`、`GetBaselineAnalysis`、
`SetBaselineAnalysis`、`CompareHistoricalAnalyses` 只依赖 Application 的
`AnalysisRepository` Protocol。数据库实现由 composition root 注入。保存是独立操作，
数学用例不会自动写入数据库；历史比较调用现有 `compare_results`，不静默改变网格或重拟合。

`ApplicationContainer` 是这些用例的显式不可变组合，只有组装层知道 SQLite 和 Excel 的实现。
公共导入 DTO 使用唯一实现，旧 infrastructure 导入路径保持兼容。
