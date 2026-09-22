# Task 3：PSD 插值与混合算法

本次基于既有 Domain Core 增量实现，复用 PSD、PSDInterpolator、DistributionBasis、TailPolicy 与已有领域异常。没有新增同义 RecipeComponent、PSDValidationError，也没有新增 q 拟合、模型、界面、Excel 或数据库功能。

## 累计 PSD 与数据校验

累计通过率 \(P(D)\) 表示粒径不超过给定 \(D\) 的累计质量比例。本接口只接受 `DistributionBasis.MASS`；体积分布、数量分布及未知统计基准均报 `BasisMismatchError`。

内部粒径为 μm、通过率为 0～1。`PSD` 在构造时检查非空、至少两点、粒径有限且大于零、严格递增无重复、通过率有限且在 [0,1] 内单调不下降、两数组等长，并将输入复制成不可变 tuple。重复节点仅允许出现在不同原料之间，不能在同一原料内部静默合并。

比例通过统一 `fractions` 校验：非负、有限，且

\[
\left|\sum_iw_i-1\right|\leq10^{-8}.
\]

0.4+0.3+0.2=0.9 会报 `DomainValidationError`。沿用原项目约定，仅对容差内的浮点总和误差作数值归一化；这不是对错误配方的自动修复。原业务适配层仍记录总和与诊断；新服务只返回 PSD，调用方自行保留输入。

## 为什么需要统一网格

不同原料第 k 行不一定代表同一个粒径，不能直接逐行相加。`ParticleSizeGridBuilder` 将所有已校验原料的测量节点取并集、去重并排序：

\[
G=\operatorname{sort}\left(\bigcup_i\{D_{i,1},\ldots,D_{i,n_i}\}\right).
\]

例如 `(10,100,1000)` 和 `(20,200,2000)` 得到 `(10,20,100,200,1000,2000)`。去重为精确数值去重，不以宽泛容差合并相近但不同的测量节点。

零质量比例的 PSD 也接受数据校验并贡献网格节点，但不贡献累计通过率，不传播其缺失值。单个正比例原料的曲线不因此改变，只可能增加采样节点。

计算复杂度为并集排序约 O(M log M) 与混合 O(NG)，M 为总输入节点数，N 为原料数量，G 为网格大小。不创建额外几千个平滑点。现有 `build_grid(profile)` 专供原分析流程的固定评价网格，继续保留，不能将依赖批次测点的并集直接替代历史 q 评价网格。

## 两种插值策略

在线性坐标上：

\[
P(D)=P_k+\frac{D-D_k}{D_{k+1}-D_k}(P_{k+1}-P_k).
\]

`LinearInterpolator` 使用上述规则。例如 (10 μm,0.2) 与 (100 μm,0.8) 之间的 55 μm 对应 0.5。

在对数粒径坐标上：

\[
P(D)=P_k+\frac{\ln D-\ln D_k}{\ln D_{k+1}-\ln D_k}(P_{k+1}-P_k).
\]

`LogLinearInterpolator` 使用自然对数，`LogSizeLinearInterpolator` 是同一个类的别名，不维护第二份算法。例如 (10 μm,0.2) 与 (1000 μm,0.8) 之间的 100 μm 对应 0.5。只对粒径取对数，不对通过率取对数。非正粒径在取 log 前报错；极端相近粒径在浮点 log 空间重合时也报领域异常。

## 统一边界规则

由现有 `TailPolicy` 扩展并统一在插值模块处理，不在混合算法中重复判断：

| 策略 | 超出已测范围时的行为 |
|---|---|
| `CLAMP` | 新混合服务默认；下端使用第一个实际通过率，上端使用最后一个实际通过率 |
| `ERROR` | 抛已有 `CoverageError` |
| `STRICT` | 保留旧约定：缺失节点为 `None`，不是报错策略 |
| `CONFIRMED` | 保留旧约定：仅显式确认的 0/1 物理尾部可延续，其余为 `None` |

Clamp 公式为：

\[
P(D)=\begin{cases}
P(D_{min}),&D<D_{min},\\
P(D_{max}),&D>D_{max}.
\end{cases}
\]

例如端点为 0.2 与 0.8 时，外部仍为 0.2 与 0.8，不能强制补成 0 与 1。Clamp 是本任务明确采用的数值边界假设，并不证明未知尾部的真实分布。输出不会因此自动标记尾部已经物理确认。

独立插值策略不带参数调用时，仍沿用旧的 `CONFIRMED` 默认值。`PSDMixingService` 会显式传入自己的 `CLAMP` 默认策略，从而同时满足本任务与既有调用兼容性。

新服务承诺返回完整的 `PSD`。若使用 STRICT/CONFIRMED 后仍有缺失节点，会抛 CoverageError；原有分析适配器则继续允许返回带缺失值的 EvaluatedCurve。暂不实现线性外推。

## 混合与输出

\[
P_{mix}(D_j)=\sum_{i=1}^{N}w_iP_i(D_j).
\]

流程为：确认不可变 PSD → 校验比例及 MASS 基准 → 调用网格构建器 → 各原料调用插值策略 → NumPy 矩阵加权 → 检查输出 → 构造新的 PSD。

只有 `_mix_on_grid` 中的一次矩阵乘法实现加权公式。新服务和既有 `mix_psd` 适配器都调用此内核，没有第二份逐行加权代码。Python 仅循环分派各原料的插值，粒径与原料的乘加为向量化操作。

输入曲线合法性由 PSD/EvaluatedCurve 校验。输出先检查有限性、范围和单调性；超出集中定义的 `CUMULATIVE_ROUNDOFF_TOLERANCE=1e-12` 就报错，只允许这个范围内的浮点修正。没有无条件 `np.clip`；连续若干小下降累计超过容差也会报错。

## 稳定接口与最小示例

```python
from psd_analyzer.domain.models.psd import PSD
from psd_analyzer.domain.services.interpolation import LinearInterpolator
from psd_analyzer.domain.services.psd_mixing import PSDMixingService

psd_a = PSD((10, 100, 1000), (0.2, 0.6, 1.0))
psd_b = PSD((10, 100, 1000), (0.0, 0.4, 1.0))

mixed = PSDMixingService().mix(
    psds=(psd_a, psd_b),
    mass_fractions=(0.4, 0.6),
    interpolator=LinearInterpolator(),
)
# mixed.cumulative_passing == approximately (0.08, 0.48, 1.0)
```

| 接口 | 责任 |
|---|---|
| `PSD` | 输入与最终输出的稳定领域对象 |
| `PSDInterpolator` | 沿用既有策略协议，返回 EvaluatedCurve |
| `LinearInterpolator` / `LogSizeLinearInterpolator` | 两种插值，后者复用 LogLinearInterpolator |
| `PSDGridBuilder` | 可注入的网格构建协议 |
| `ParticleSizeGridBuilder` | 默认的测量节点并集实现 |
| `PSDMixingService(grid_builder=..., tail_policy=...)` | 仅处理 PSD、质量分数、网格和插值 |
| `mix_psd(...)` | 旧业务适配接口，签名与原有缺失覆盖规则保留 |

新服务采用两个等长序列 `psds` 与 `mass_fractions`，而没有复制一个与既有 MixtureComponent 语义重叠的新组件类。序列长度不一致会报领域异常。批次、原料和密度信息由上层从旧对象中提取；新服务不读取它们。

Task 4 可以直接取 `mixed.particle_size_um`、`mixed.cumulative_passing`、`mixed.basis` 作为后续模型输入。需要评价网格时显式再次插值，记录插值与边界配置；不要将本任务的并集网格默认为所有历史 q 的比较口径。

## 兼容改动与验收

局部重构原因：原 mix_psd 直接接收批次对象、由调用者提供网格，不能满足独立的“PSD+比例→PSD”入口。现在它是一个薄适配器，原密度换算仍留在旧模块，既有体积分析测试继续运行。新服务只实现 MASS，未复制体积换算功能。

此外，旧实现使用无条件 min/max 限幅，本次改成先验证、后按统一容差修正。共享加权内核改为向量化，因此软件及分析算法版本升级到 0.1.1，避免数值实现变化在追溯时仍沿用旧版本号；q 公式和拟合代码未修改。

测试包含本任务的 14 项验收、零比例、错误策略输出、边界物理标记、依赖注入、底层异常转换及 30×500 节点规模。架构测试实际禁止加载 q、模型、密度适配、SciPy、UI、Excel 与数据库模块后运行独立混合服务。

运行：

```bash
python examples/psd_mixing_demo.py
python -m pytest --cov=psd_analyzer.domain --cov-report=term-missing
python -m ruff check src tests examples
python -m ruff format --check src tests examples
python -m mypy src
```

本地验收结果：185 项测试全部通过（原有 126 项保留，新增 59 项），Domain 行与分支综合覆盖率 98.50%；Ruff、格式检查、mypy（37 个源文件）全部通过；独立混合示例与原有分析示例均可运行。
