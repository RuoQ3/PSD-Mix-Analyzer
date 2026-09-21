# PSD Mix Analyzer

多原料粒度分布分析与颗粒级配监控系统，用于耐火材料混料线的批次波动分析、原料替代评价与研发模拟。

**生产阶段固定配方，模型用于监控和分析；研发阶段才允许模拟调整比例。**

## 当前进度

已完成项目目录框架与 **M2：Domain Core**。核心可以脱离 GUI、Excel 和数据库独立运行。Excel 导入、数据库、业务用例、Plotly 与 Streamlit 尚未实现；对应包仅预留边界，没有假页面或空业务实现。

- 不可变的原料、批次、PSD 测量、配方版本、分析配置和结果。
- 线性与对数粒径线性插值，严格的尾部覆盖处理。
- 质量混合、密度换算及带明确假设的体积基准分析。
- Modified Andreasen / Funk-Dinger 模型，包含 q→0 稳定极限。
- 用户目标 q 与拟合等效 q 分开保存；损失函数与模型可替换。
- RMSE、MAE、SSE、最大绝对偏差、可配置关键粒径和基准差异。
- 正式配方锁定、固定比例替代校验、独立研发配方副本。
- 原始输入快照、实际权重、配置和算法版本随计算结果返回，供下一阶段持久化。

q 值仅反映整体颗粒级配趋势，不代表产品性能，也不能单独作为现场修改配方的依据。

## 安装与运行

需要 Python 3.12+。建议先创建虚拟环境；Windows 激活路径为 `.venv\Scripts\activate`，Linux/macOS 为 `source .venv/bin/activate`。

```bash
python -m venv .venv
python -m pip install -e ".[dev]" -c requirements.lock
python examples/domain_demo.py
```

`pyproject.toml` 定义依赖；`requirements.lock` 是本次 Python 3.12 验证环境的完整开发依赖约束。跨 Python 大版本升级时重新验证并更新锁定版本。仅运行核心时可安装 `python -m pip install -e . -c requirements.lock`。

示例使用人工构造数据，展示固定配方的基准、原料替代及质量/体积权重差异，不包含真实生产配方。输出到终端，不操作数据库或设备。

## 校验

```bash
python -m pytest --cov=psd_analyzer.domain --cov-report=term-missing
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src
```

覆盖率门槛为 90%，包含分支覆盖。CI 在 Python 3.12 下执行相同检查。数值恢复测试使用合成数据，混合和插值另有独立手算案例；不将测试通过解释为生产数据已经验证。

## 核心入口

| 入口 | 作用 |
|---|---|
| `analyze_mixture(components, profile)` | 纯数值完整分析，不读写文件 |
| `mix_psd(...)` | 在指定网格上插值、按一致统计基准混合 |
| `fit_q(...)` | 固定模型边界下拟合单参数 q |
| `compare_results(current, baseline)` | 比较同一口径结果，输出差值 |
| `validate_selection(recipe, components)` | 检查正式配方、组分身份与比例 |
| `validate_selection(..., substitution=True)` | 保持比例，允许明确替代原料 |
| `create_simulation_recipe(...)` | 创建独立 Draft 模拟配方，不改变来源 |

`analyze_mixture` 是数学服务，不代表生产操作授权。后续生产用例必须先执行 `validate_selection`，再调用计算；本阶段不存在生产配方发布入口。

## 目录职责

| 目录 | 职责/状态 |
|---|---|
| `src/psd_analyzer/domain` | 已实现：数据不变量、业务约束与数学计算 |
| `src/psd_analyzer/application` | 预留：用例、传输对象、Repository 接口 |
| `src/psd_analyzer/infrastructure` | 预留：Excel、数据库、配置 |
| `src/psd_analyzer/visualization` | 预留：独立图表 |
| `src/psd_analyzer/ui` | 预留：Streamlit 页面 |
| `tests/unit`、`tests/architecture` | 数学、数据、配方与依赖边界测试 |
| `tests/integration`、`tests/fixtures` | 预留后续文件与数据库集成案例 |
| `examples` | 可运行的独立核心示例 |
| `docs` | 架构、数学口径、M2 交付说明 |

## 数值与数据约定

- 内部单位：粒径 μm、通过率 0～1、密度 kg/m³，配方为干基质量分数。
- 不自动排序、合并重复粒径、修复非单调数据或补全未知尾部；这些输入直接报错或返回覆盖缺失。
- 只有显式确认的 0/1 端点可延续已知尾部；未知节点返回 `None`。
- 质量和体积统计基准不能混用；单原料质量/体积分布等同需要粒级密度一致假设。
- 整体体积分数转换必须有与颗粒体积定义匹配的密度，不接受堆积密度。
- 使用不同测试协议的数据需在分析配置中显式确认可比性，且结果保留诊断。
- q 默认搜索范围 [0,1] 是数值配置，不是质量标准；命中边界、覆盖不足、目标函数过平坦与失败均有独立状态。
- 拟合网格与关键粒径分开；更换分析配置不得直接与历史 q 混合比较。
- SSE 为分数平方和；RMSE 等显示为百分点时乘 100，SSE 改成 pp² 时乘 10000。

详见 [数学与接口约定](docs/mathematical_conventions.md)、[第一阶段架构](docs/architecture.md) 和 [M2 交付说明](docs/domain_core.md)。

## 后续开发

下一阶段为 **M3：Excel IO + Repository**，然后按用例、图表、界面顺序推进。不会提前增加 AI、自动配方优化、设备控制或性能预测。
