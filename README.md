# PSD Mix Analyzer

多原料粒度分布分析与颗粒级配监控系统，用于耐火材料混料线的批次波动分析、原料替代评价与研发模拟。

**生产阶段固定配方，模型用于监控和分析；研发阶段才允许模拟调整比例。**

## 当前进度

已完成项目目录框架、**M2：Domain Core**、**Task 3：PSD 插值与混合**、**Task 4：Modified Andreasen + q 拟合**、**Task 5：Excel 数据输入层**、**Task 6：Application 用例**及 **Task 7：Plotly 可视化**。数学核心可以脱离 GUI、Excel 和数据库独立运行。数据库与 Streamlit 仍只预留边界。

- 不可变的原料、批次、PSD 测量、配方版本、分析配置和结果。
- 线性与对数粒径线性插值，严格的尾部覆盖处理。
- 质量混合、密度换算及带明确假设的体积基准分析。
- Modified Andreasen / Funk-Dinger 模型，要求 q > 0，保留 q→0⁺ 的稳定数值处理。
- 用户目标 q 与拟合等效 q 分开保存；损失函数与模型可替换。
- MSE、RMSE、MAE、SSE、最大绝对偏差、可配置关键粒径和基准差异。
- 正式配方锁定、固定比例替代校验、独立研发配方副本。
- 原始输入快照、实际权重、配置和算法版本随计算结果返回，供下一阶段持久化。

q 值仅反映整体颗粒级配趋势，不代表产品性能，也不能单独作为现场修改配方的依据。

## Task 3：独立插值与质量混合

新增 `PSDMixingService.mix(psds, mass_fractions, interpolator) -> PSD`：默认采用原始节点并集和 clamp 边界，仅接收 PSD 与质量比例。无需创建原料、批次或分析配置；不调用 q 拟合。

旧分析入口保留其固定评价网格和原边界规则。详见 [Task 3 模块说明](docs/psd_interpolation_mixing.md)。

## Task 4 与 Task 5

沿用既有 `ModifiedAndreasen`、`fit_q`、`FitResult`、`PackingModel` 和 `LossFunction`。拟合仅使用模型范围内至少 3 个节点，默认 q 搜索范围为 `[0.05, 1.0]`；结果携带独立 SSE/MSE/RMSE/MAE/MaxDev、有效点数、模型边界和收敛状态。`evaluate_at_sizes` 直接复用 Task 3 插值策略。

Excel 采用既有架构的 `Materials`、`Measurements`、`PSD`、`Recipe` 数据表，保留批次与测量标识；模板另含 `说明` 页。导入先收集结构化错误，再构造已有领域对象；不会运行混合、拟合或选择批次。配方导入为 Draft，不具备生产发布功能。

详见 [Task 4 数学服务](docs/task4.md) 与 [Excel 格式及接口](docs/excel_input.md)。

## Task 6 与 Task 7

应用层提供 `AnalyzeRecipePSD`、`ComparePSDAnalysis`、`CompareMaterialSubstitution`、`SimulateRecipe`，复用 `AnalysisProfile` 与领域计算服务。生产分析要求 Released 配方；Excel 导入的 Draft 可通过模拟用例分析，并明确标记 `is_simulation=True`。批次比较和替代分析保持配方比例不变，双方在同一网格上计算。

`AnalysisResult` 保留独立的 equivalent q、target q 及对应指标，并附带配方身份；`ComparisonResult` 带双方快照及差异指标。绘图层直接消费结果，生成 PSD、百分点差值、关键粒径及 q 对比 Figure。Application 不依赖 Plotly；图层不执行混合、拟合或导入。

详见 [Application 用例](docs/application.md) 和 [Plotly 可视化](docs/visualization.md)。

## 安装与运行

需要 Python 3.12+。建议先创建虚拟环境；Windows 激活路径为 `.venv\Scripts\activate`，Linux/macOS 为 `source .venv/bin/activate`。

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS；Windows 使用下方命令
python -m pip install -e ".[dev,excel,visualization]" -c requirements.lock
python examples/psd_mixing_demo.py
# 原有完整分析示例仍可运行
python examples/domain_demo.py
# Excel 导入 → 固定配方混合 → q 拟合
python examples/excel_analysis_demo.py
# 应用层 → 绘图；可选导出独立 HTML
python examples/application_visualization_demo.py --output-dir data/demo_figures
```

Windows PowerShell 可直接指定虚拟环境解释器，避免误用系统中的 Python 3.10：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,excel,visualization]" -c requirements.lock
.\.venv\Scripts\python.exe examples/application_visualization_demo.py --output-dir data/demo_figures
```

`pyproject.toml` 定义依赖；`requirements.lock` 是本次 Python 3.12 验证环境的完整开发依赖约束。跨 Python 大版本升级时重新验证并更新锁定版本。Plotly 通过可选依赖 `.[visualization]` 安装；仅运行应用层无需安装 Plotly。Excel 是可选依赖，通过 `.[excel]` 安装；使用 openpyxl 保留原始单元格格式和位置，不额外依赖 pandas。仅运行核心时可安装 `python -m pip install -e . -c requirements.lock`。

示例使用人工构造数据，展示固定配方的基准、原料替代及质量/体积权重差异，不包含真实生产配方。默认输出到终端；绘图示例可显式导出 HTML，不操作数据库或设备。

## 校验

```bash
python -m pytest --cov=psd_analyzer.domain --cov-report=term-missing
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src
```

覆盖率门槛为 90%，包含分支覆盖。CI 在 Python 3.12 下执行相同检查。数值恢复测试使用合成数据，混合和插值另有独立手算案例；不将测试通过解释为生产数据已经验证。

Task 4 / Task 5 本地验收：Python 3.12，264 项测试通过，Domain 行与分支综合覆盖率 98.25%；Ruff、mypy（44 个源文件）和三个示例通过。Excel 示例恢复 q=0.2499999977（预期 0.25）。

Task 6 / Task 7 本地验收：312 项测试通过，Domain 行与分支综合覆盖率 98.30%；Ruff、mypy（58 个源文件）和四个示例通过。测试包括 Application → Figure、批次比较 → 多图以及 Excel Draft → 研发模拟 → Figure。

## 核心入口

| 入口 | 作用 |
|---|---|
| `PSDMixingService().mix(psds, mass_fractions, interpolator)` | 并集网格、默认 clamp、纯质量混合，返回 PSD |
| `analyze_mixture(components, profile)` | 纯数值完整分析，不读写文件 |
| `mix_psd(...)` | 在指定网格上插值、按一致统计基准混合 |
| `fit_q(...)` | 筛选模型范围内节点，返回 q、状态和指标 |
| `evaluate_at_sizes(psd, sizes, interpolator)` | 可配置粒径查询，复用插值策略 |
| `calculate_metrics(observed, predicted)` | 唯一的误差指标计算来源 |
| `import_excel_workbook(path)` | 读取和校验，返回不可变领域对象集合 |
| `generate_excel_template(path)` | 生成带明确示例标记的标准模板 |
| `compare_results(current, baseline)` | 比较同一口径结果，输出差值 |
| `validate_selection(recipe, components)` | 检查正式配方、组分身份与比例 |
| `validate_selection(..., substitution=True)` | 保持比例，允许明确替代原料 |
| `create_simulation_recipe(...)` | 创建独立 Draft 模拟配方，不改变来源 |

`analyze_mixture` 是数学服务，不代表生产操作授权。Application 生产用例已先执行 `validate_selection`，再调用计算；本阶段不存在生产配方发布入口。

## 目录职责

| 目录 | 职责/状态 |
|---|---|
| `src/psd_analyzer/domain` | 已实现：数据不变量、业务约束与数学计算 |
| `src/psd_analyzer/application` | 已实现四类用例和计算依赖注入；Repository 仍预留 |
| `src/psd_analyzer/infrastructure` | 已实现 Excel；数据库、配置仍预留 |
| `src/psd_analyzer/visualization` | 已实现独立 Plotly Figure 构建器与绘图数据 |
| `src/psd_analyzer/ui` | 预留：Streamlit 页面 |
| `tests/unit`、`tests/architecture` | 数学、数据、配方与依赖边界测试 |
| `tests/integration` | Excel → 数学；Application → Figure；比较结果 → 三类图 |
| `examples` | 可运行的独立核心示例 |
| `docs` | 架构、数学口径、M2 交付说明 |

## 数值与数据约定

- 内部单位：粒径 μm、通过率 0～1、密度 kg/m³，配方为干基质量分数。
- 原料 PSD 内部不自动排序、合并重复节点或修复非单调数据。跨原料节点并集由独立网格构建器去重排序。
- Task 3 新服务默认 clamp，越界保持实际端点通过率。旧分析默认 CONFIRMED，仅延续明确确认的 0/1 尾部，其余返回 `None`；两者由同一边界策略控制。
- 质量和体积统计基准不能混用；单原料质量/体积分布等同需要粒级密度一致假设。
- 整体体积分数转换必须有与颗粒体积定义匹配的密度，不接受堆积密度。
- 使用不同测试协议的数据需在分析配置中显式确认可比性，且结果保留诊断。
- q 默认搜索范围 [0.05,1] 是数值配置，不是质量标准；命中边界、覆盖不足、目标函数过平坦与失败均有独立状态。
- 拟合网格与关键粒径分开；更换分析配置不得直接与历史 q 混合比较。
- SSE 为分数平方和；RMSE 等显示为百分点时乘 100，SSE 改成 pp² 时乘 10000。

详见 [数学与接口约定](docs/mathematical_conventions.md)、[第一阶段架构](docs/architecture.md) 和 [M2 交付说明](docs/domain_core.md)。

## 兼容性调整

- Task 4 要求 `q > 0`，因此原有 `q = 0`、负 q 和 Modified Andreasen 的非正搜索下界现在报错；近零正 q 仍稳定计算。使用旧 `[0,1]` 配置时需显式更新配置版本及下界。
- `MaterialBatch.supplier` 允许空字符串表示尚未填写，批次身份和 `batch_no` 仍必须明确。不会填造供应商名称；空 notes 沿用现有领域模型的空字符串约定。
- Task 3 的质量混合、PSD、Recipe 以及插值协议保持原接口。结果模型按 Task 6 补充可选配方身份、模拟标记及比较快照，保留既有字段。算法版本更新为 `domain-core-0.3.0`，旧分析结果应按同一配置重算后比较。

## 后续开发

未来 UI 可直接调用 Application 用例，再将结果交给 Figure 构建器；本阶段不实现 Streamlit 页面、数据库、SPC、自动优化或生产配方自动修改。
