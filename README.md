# PSD Mix Analyzer

**PSD Mix Analyzer 是用于多原料颗粒级配分析、波动监控和研发辅助的工程工具。**

**q 值不是产品质量的独立判定指标；系统不会自动修改正式生产配方。**

项目将各原料的累计粒度分布（PSD）映射到统一粒径网格，按固定配方的质量分数计算混合 PSD，再提供等效 q 拟合、目标曲线对比、关键粒径查询及历史分析。适用于原料批次波动观察、国产替代料评价和人工研发模拟。

当前已实现 Domain Core、插值与混合、Modified Andreasen 模型、Excel 输入、Application 用例、Plotly 图表、Streamlit 界面和 SQLite 历史记录。数学核心可脱离界面、Excel 和数据库独立运行。

## 解决什么问题

- **不同测量节点的原料如何混合分析**：先插值到统一网格，再按配方比例加权，得到理论混合 PSD。
- **固定配方下，原料批次变化带来多大级配差异**：对比混合曲线、等效 q、关键粒径通过率与误差指标。
- **候选原料能否保持相近的级配**：明确指定替代原料，保持配方比例不变，查看替代前后的差异。
- **研发时怎样比较人工设定的比例**：在独立模拟页面调整比例，保留正式配方，结果标记为研发模拟。
- **如何追溯一次分析**：显式保存配方版本、原料批次、源 PSD、分析配置与结果，之后可恢复查看和比较。

## 不解决什么问题

本工具不预测强度、热震、耐蚀性等产品性能，也不直接计算实际堆积密度、孔隙率或作产品合格判定。理论混合 PSD 也不能替代混合后实物的粒度检测。

当前不提供配方自动优化、自动推荐或修改正式生产配方、审批发布流程、设备控制、MES / ERP 对接及完整 SPC 控制系统。没有建立 UCL / LCL、Cp / Cpk 等正式控制标准。研发页面的比例调整是用户主动进行的独立模拟；原料替代结果用于辅助评估，仍需结合实际工艺试验。

## 安装

项目要求 Python 3.12+；当前 CI 使用 Python 3.12，首次安装建议采用同版本。需要 Git 获取仓库；已有本地仓库时，在仓库根目录执行 `git pull` 更新，然后跳过克隆步骤。

```bash
git clone https://github.com/RuoQ3/PSD-Mix-Analyzer.git
cd PSD-Mix-Analyzer
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[ui]" -c requirements.lock
```

如果已经激活项目虚拟环境，直接执行安装命令即可。不方便激活时，可在后续所有命令中将 `python` 替换为 `.\.venv\Scripts\python.exe`，无需修改 PowerShell 执行策略。

### Linux / macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui]" -c requirements.lock
```

`.[ui]` 包含运行界面、Excel 导入、Plotly 绘图和 SQLite 所需依赖。开发与测试使用 `.[dev,ui]`；仅运行数学核心可安装 `python -m pip install -e . -c requirements.lock`。Excel、绘图、持久化也分别提供 `excel`、`visualization`、`persistence` 可选依赖。

`pyproject.toml` 声明依赖范围，`requirements.lock` 固定 Python 3.12 Linux 验证环境的依赖版本。使用其他 Python 版本或平台时仍需验证兼容性。遇到 Python 版本不符合要求的提示，先运行 `python --version`，确认当前终端使用的是项目虚拟环境。

## 运行界面

在仓库根目录、已激活的虚拟环境中运行：

```bash
python -m streamlit run src/psd_analyzer/ui/streamlit_app/app.py
```

打开终端显示的 **Local URL**。运行期间保留终端，结束时按 `Ctrl+C`。界面包含首页、生产监控、原料替代、研发模拟和历史分析；不需要自行编写 Python 脚本才能使用这些页面。

### 首次体验：使用示例模板

1. 首页点击“准备 Excel 模板”，再点击“下载 Excel 模板”。
2. 上传下载的 `.xlsx`，点击“导入工作簿”。示例均标注为 `EXAMPLE ONLY`，只用于演示。
3. 进入“研发模拟”，选择示例配方和各行原料批次，保持示例比例不变。
4. 将 `D_min` 设为 **1 μm**、`D_max` 设为 **625 μm**；高级设置中的关键粒径可填写 `16,81,256`。其余设置保持默认，暂不设置目标 q。
5. 点击“执行研发模拟”，应得到约 **0.25** 的 `equivalent_q`，并看到 PSD 曲线和关键粒径结果。
6. 如需保留结果，点击“保存分析”，然后到“历史分析”查看。

示例配方默认是 Draft，因此应从研发模拟开始。示例恢复 q=0.25 使用上述 1～625 μm 范围；界面初始 `D_max` 为 1000 μm，使用不同范围会得到不同拟合结果。

## Excel 格式

使用一个 `.xlsx` 工作簿，包含以下 **四个必需数据页**。模板另有 `说明` 页；配方页是单数 **`Recipe`**，不是 `Recipes`。

| Sheet | 必需列 | 可选列 |
|---|---|---|
| `Materials` | `material_code`, `material_name`, `batch_key`, `batch_no` | `supplier`, `grade`, `notes`, `density`, `density_kind` |
| `Measurements` | `measurement_key`, `batch_key`, `basis`, `method`, `protocol` | `version` |
| `PSD` | `measurement_key`, `particle_size_um`, `cumulative_passing_pct` | — |
| `Recipe` | `recipe_code`, `recipe_version`, `line_key`, `material_code`, `mass_fraction_pct` | `recipe_name`, `status`, `approval_reference` |

关联方式：`Materials` 定义原料及批次；`Measurements.batch_key` 指向批次；`PSD.measurement_key` 指向测量；`Recipe.material_code` 指向原料，执行分析时再选择具体批次与测量。这样可以区分同一原料的多个批次和复测结果。

PSD 使用长表，一行对应一个测量的一个粒径节点：

| measurement_key | particle_size_um | cumulative_passing_pct |
|---|---:|---:|
| EX-PSD-A | 1 | 0 |
| EX-PSD-A | 16 | 25 |
| EX-PSD-A | 81 | 50 |
| EX-PSD-A | 256 | 75 |
| EX-PSD-A | 625 | 100 |

填写规则：

- Sheet 名与列名区分大小写；标识和版本用文本填写，例如 `A001`、`v1`，避免丢失前导零。
- 当前界面按质量分数分析，所选测量的 `basis` 应为 `mass`；测量方法和协议必须明确。输入层保留其他基准，但不会自动将其当作质量 PSD。
- 粒径单位为 **μm**。每个测量至少两个节点，在输入行顺序中严格递增、全部大于 0，不得重复；累计通过率不得下降。
- 百分比列可填普通数值 `25`、文本 `25%` 或 Excel 百分比格式的 `25%`，均转换为 Domain 的 `0.25`。普通数值 `0.25` 没有百分比格式时表示 **0.25%**，不是 25%。
- 同一配方版本的比例应非负且总计 100%，使用统一浮点容差。系统不会自动排序、删重复粒径、补未知 PSD 或将 95% 等错误配方归一化；也不执行 Excel 公式。错误会保留文件、Sheet、行号、列名、原始值及原因。
- 密度可不填；填写时单位为 kg/m³，并同时填写 `density_kind`。当前界面不会用密度偷偷修正质量比例。

配方 `status` 缺省为 `draft`。生产监控和原料替代要求外部已批准的配方：同一配方版本各行填写一致的 `status=released` 及真实 `approval_reference`。导入只记录外部状态与引用，不执行审批或发布。

详细规则和程序接口见 [Excel 输入说明](docs/excel_input.md)。

## 如何执行分析

### 选择分析模式

| 页面 | 适用场景 | 配方比例 |
|---|---|---|
| 生产监控 | 已批准配方下选择当前原料批次，观察级配波动 | 正式比例只读 |
| 原料替代 | 显式选择要替代的配方行及候选原料测量，比较替代前后差异 | 保持不变；不代表正式配方变更 |
| 研发模拟 | 对 Draft 或正式配方创建独立模拟，人工设定比例 | 仅模拟比例可编辑；非负且合计 100% 才能执行 |

导入成功后，选择配方，并逐行选择原料批次和测量版本；原料替代页面还需指定替代行和候选测量。设置以下参数后，点击对应页面的执行按钮：

| 参数 | 含义与默认设置 |
|---|---|
| `D_min` / `D_max` | Modified Andreasen 模型与拟合范围，单位 μm；界面默认 1 / 1000，需按分析约定设置 |
| `target_q` | 可选的目标参考曲线参数；未勾选时不生成目标曲线 |
| 插值方法 | 高级设置中选择 `log-linear`（默认）或 `linear` |
| q 上下界 | 拟合搜索区间，默认 `[0.05, 1.0]`；不是质量合格区间 |
| 关键粒径 | 高级设置中输入逗号分隔的正数，严格递增，例如 `10,45,75,100` |

当前计算取原料实测粒径节点的并集。`linear` 在粒径坐标上插值；`log-linear` 在自然对数粒径坐标上插值。界面采用 clamp 边界：小于最小测量粒径时保持该端点通过率，大于最大测量粒径时保持最大端点通过率。它不会自动把未测尾部补成 0% 或 100%。

结果包括混合 PSD、拟合等效 q、可选目标曲线、误差指标和关键粒径通过率。生产页面如有兼容的历史基准，还展示基准曲线与差值；替代页面展示双方曲线、ΔPSD、Δq 和关键粒径对比。

指标卡在设置目标 q 时显示相对目标曲线的误差，否则显示拟合误差，以卡片标签为准。RMSE、MAE、MaxDev 使用累计通过率分数单位，乘以 100 才是百分点；关键粒径通过率显示为百分数，差值显示为百分点（pp）。拟合误差仅评价拟合范围内节点，目标曲线误差按当前混合计算网格评价。

改变输入后需要重新执行分析。计算本身不会写数据库；点击“保存分析”才保存，重复点击同一结果不会产生重复记录。完整操作见 [界面说明](docs/streamlit.md)。

## q 的含义：equivalent_q 与 target_q

累计 PSD 的 $P(D)$ 表示粒径不超过 $D$ 的累计通过比例。质量混合采用：

$$
P_{mix}(D_j)=\sum_i w_i P_i(D_j),\qquad w_i\geq 0,\quad \sum_i w_i=1
$$

Modified Andreasen / Funk-Dinger 模型用分布模数 q 描述参考级配曲线的形状：

$$
P(D)=\frac{D^q-D_{min}^q}{D_{max}^q-D_{min}^q},\qquad q>0,\quad 0<D_{min}<D_{max}
$$

模型在 $D\leq D_{min}$ 时返回 0，在 $D\geq D_{max}$ 时返回 1。在相同粒径上下限下，较小的 q 对应较高的中间粒径累计通过率，即更多细颗粒；这不意味着产品性能一定更好。

| 概念 | 来源 | 用途 |
|---|---|---|
| `equivalent_q`（等效 q） | 从实际混合 PSD 拟合得到，使模型曲线尽量接近该 PSD | 描述本次级配，辅助同口径批次比较 |
| `target_q`（目标 q） | 用户显式设置，可为空 | 生成目标参考曲线，评价与目标的差异；不决定拟合结果 |
| 控制限 | 当前尚未建立 | 不能用目标 q 或拟合搜索边界替代正式控制限 |

例如 `equivalent_q=0.28`、`target_q=0.25` 表示实际级配的拟合描述与所设目标有差异，**不表示不合格，也不会触发自动改配方**。设置或改变 `target_q` 不会自动把 `equivalent_q` 调整到目标值。

拟合默认最小化平方误差和（SSE），仅使用 $D_{min}\leq D_j\leq D_{max}$ 内的节点，至少需要 3 个有效点。命中搜索边界、覆盖不足或拟合不稳定时应查看拟合状态和诊断，不能只看 q 数字。q 也不能表达所有局部粒径差异，需结合完整 PSD、关键粒径通过率和误差指标判断。

批次比较需使用一致的配方版本、测量协议、粒径范围、网格、插值方式、拟合设置和算法版本。改变这些条件可能改变等效 q；历史比较不兼容时系统会提示原因，不静默重算。详见 [数学服务](docs/task4.md) 和 [数值约定](docs/mathematical_conventions.md)。

## 如何查看历史与设置基准

1. 分析完成后点击“保存分析”。生产监控、原料替代和研发模拟分别保存类型，模拟记录不会伪装成正式生产记录。
2. 进入“历史分析”，按 Recipe ID、原料批号、分析类型或 UTC 日期范围筛选；默认显示最新的最多 1000 条，可缩小范围。
3. 在“查看记录详情”选择记录，查看当次配方版本、批次、拟合配置、PSD、关键粒径及指标。历史查看不需要重新上传 Excel。
4. 如需设置基准，选择一条生产监控记录，点击“将该记录设为此配方版本的基准”。同一配方 ID + 版本最多一个基准，切换需显式操作；模拟和替代分析不能成为默认生产基准。
5. 有多条记录时，可选择“历史比较基准”，点击“比较两条历史分析”。页面同时提供等效 q 时间趋势，不同计算口径分组显示，不绘制 SPC 控制限。

默认 SQLite 文件是**启动目录下**的 `data/psd_analyzer.db`。从仓库根目录启动可保持路径一致；首次启动集中初始化表结构。保存的是原始数据与结果快照，查看时重新生成图表，不保存 Plotly Figure。

需要自定义位置时，在启动前设置 `PSD_ANALYZER_DB`，例如 Windows PowerShell：

```powershell
$env:PSD_ANALYZER_DB = "E:\PSDData\psd_analyzer.db"
python -m streamlit run src/psd_analyzer/ui/streamlit_app/app.py
```

Linux / macOS 可用 `export PSD_ANALYZER_DB="$PWD/data/psd_analyzer.db"`。记录和时间过滤统一使用 UTC；切换数据库路径会看到另一份数据库的记录。历史数据是分析记录，不是正式产品质量判定数据库。详见 [SQLite 持久化](docs/persistence.md)。

## 如何运行测试

在仓库根目录、项目虚拟环境中安装开发依赖后执行：

```bash
python -m pip install -e ".[dev,ui]" -c requirements.lock
python -m pytest
python -m pytest --cov=psd_analyzer.domain --cov-report=term-missing
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src
```

测试包含数学手算与 q 恢复、Excel 校验、Application 编排、依赖边界、Streamlit 交互、SQLite 事务以及 Excel → Application → 保存 → 恢复 → 绘图集成。数据库测试使用临时数据库。Domain 行与分支综合覆盖率门槛为 90%。

Task 8 / Task 9 交付验收：375 项测试通过，Domain 覆盖率 98.30%；Ruff、mypy（86 个源文件）、四个示例及 Streamlit 无界面启动检查通过。这是该次交付记录；后续变更以 [GitHub Actions](https://github.com/RuoQ3/PSD-Mix-Analyzer/actions) 的结果为准。合成数据测试不等同于实际生产验证。

不启动界面也可运行以下示例：

```bash
python examples/psd_mixing_demo.py
python examples/domain_demo.py
python examples/excel_analysis_demo.py
python examples/application_visualization_demo.py --output-dir data/demo_figures
```

示例全部使用虚构数据；最后一个命令导出可单独打开的 HTML 图表。示例不修改生产配方或控制设备。

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

## 项目架构

| 目录 | 职责/状态 |
|---|---|
| `src/psd_analyzer/domain` | 已实现：数据不变量、业务约束与数学计算 |
| `src/psd_analyzer/application` | 已实现四类用例和计算依赖注入；Repository 协议及历史查询用例 |
| `src/psd_analyzer/infrastructure` | 已实现 Excel 和 SQLAlchemy / SQLite 快照持久化 |
| `src/psd_analyzer/visualization` | 已实现独立 Plotly Figure 构建器与绘图数据 |
| `src/psd_analyzer/ui` | 已实现：生产、替代、模拟、历史四类页面 |
| `tests/unit`、`tests/architecture` | 数学、数据、配方与依赖边界测试 |
| `tests/integration` | Excel → 数学；Application → Figure；比较结果 → 三类图 |
| `examples` | 可运行的独立核心示例 |
| `docs` | 架构、数学口径、M2 交付说明 |

依赖方向：Streamlit 页面调用 Application 用例并将结果交给 Visualization；Application 调用 Domain，通过 Repository / Workbook 协议访问基础设施。SQLite 和 Excel 实现由 `ui/streamlit_app/composition.py` 统一组装。

Domain 不依赖 Streamlit、Plotly、Excel 或 SQLAlchemy。绘图层只消费结果，不计算混合、拟合或查询数据库；页面不直接执行数学公式或 SQL。新增输入方式或更换持久化实现无需重写数学核心。

应用与图层的详细接口见 [Application 用例](docs/application.md)、[Plotly 可视化](docs/visualization.md)；独立插值与质量混合见 [Task 3 模块说明](docs/psd_interpolation_mixing.md)。

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

当前已提供完整界面与历史记录；后续可扩展正式控制标准。本阶段不实现 SPC、自动优化或生产配方自动修改。
