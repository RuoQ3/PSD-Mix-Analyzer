# Task 4：目标级配、等效 q 与误差评价

本模块复用既有 `PSD`、`AnalysisProfile`、`PackingModel`、`LossFunction`、`FitResult`，不依赖 Excel、UI 或数据库。q 是级配描述及研发分析指标，不代表真实堆积密度，不用于自动修改生产配方。

## Modified Andreasen / Funk–Dinger

累计 PSD 的 $P(D)$ 表示粒径不大于 $D$ 的累计通过分数。粒径单位为 μm，通过率为 $[0,1]$。

$$
P(D;q)=\frac{D^q-D_{\min}^q}{D_{\max}^q-D_{\min}^q}
$$

`ModifiedAndreasen` 沿用既有无状态策略接口：配置参数通过 `evaluate_q` 或 `cumulative_passing` 显式传入。要求有限的 $q>0$、$D_{\min}>0$、$D_{\max}>D_{\min}$，查询粒径必须为严格递增正数。$D\le D_{\min}$ 返回精确 0，$D\ge D_{\max}$ 返回精确 1；这与实测 PSD 的端点延续含义不同。

内部使用自然对数及 `expm1` 稳定计算，避免直接求大数幂。极小正 q 使用连续对数极限。Task 4 按当前业务要求收紧了旧实现允许 q≤0 的行为；原来的零值/负值配置应显式迁移，不能静默修正。

## 等效 q 拟合

```python
from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.services.losses import SquaredErrorLoss
from psd_analyzer.domain.services.packing_models import ModifiedAndreasen
from psd_analyzer.domain.services.q_fitting import fit_q

profile = AnalysisProfile("research", "1", 1, 1000, q_bounds=(0.05, 1.0))
result = fit_q(
    mixed_psd.particle_size_um,
    mixed_psd.cumulative_passing,
    profile=profile,
    model=ModifiedAndreasen(),
    loss=SquaredErrorLoss(),
)
```

只选择 $D_{\min}\le D_j\le D_{\max}$ 的原始输入节点；不添加显示节点，也不把区间外的 0/1 尾部加入损失。至少需要 `MIN_FIT_POINTS=3` 个区间内节点。默认目标为：

$$
q^*=\arg\min_{q\in[q_{\min},q_{\max}]} \sum_j(P_{actual}(D_j)-P(D_j;q))^2
$$

默认范围集中定义为 `[0.05, 1.00]`，可通过 profile 显式改变。先沿用既有候选区间扫描，再调用 SciPy 有界 `minimize_scalar`，同时比较两个端点。扫描不是任意自定义多峰损失的全局最优保证。模型与 loss 的 ID 必须与 profile 一致。

`FitResult` 保留既有字段 `status`、`equivalent_q`、`objective_value`、`evaluations`、`message`，新增：

- `metrics`：独立计算的 `ErrorMetrics`，与自定义优化 loss 分开。
- `point_count`、`d_min_um`、`d_max_um`：实际评价节点数和模型范围。
- `q`、`sse`、`rmse`、`mae`、`max_absolute_deviation`：便捷只读属性。
- `converged`：`success` 和 `at_bound` 时为真；边界解仍保留警告状态，不能视为无约束最佳 q。

输入错误和区间内节点过少抛 `DomainValidationError`。区间内存在缺失通过率返回 `insufficient_coverage`；区间外缺失不影响拟合。目标函数 NaN/inf、非法预测、优化器报错或不收敛返回 `failed`；平坦损失返回 `weakly_identified`。失败和弱可辨识结果的 q/metrics 为 `None`，不伪造 q=0。

## 误差指标

统一由 `calculate_metrics(actual, predicted)` 实现。令 $e_j=y_j-\hat y_j$：

$$
SSE=\sum_j e_j^2,\quad MSE=SSE/n,\quad RMSE=\sqrt{MSE}
$$

$$
MAE=\frac1n\sum_j|e_j|,\qquad MaxDev=\max_j|e_j|
$$

`ErrorMetrics` 包含 `sse`、`mse`、`rmse`、`mae`、`max_absolute_deviation`、`n`。SSE loss 直接复用该模块。通过率误差单位为 fraction；显示为百分点时由上层乘以 100，SSE/MSE 为 fraction²。指标函数要求非空、等长、有限且在 `[0,1]` 内的数组。

## 关键粒径查询

```python
from psd_analyzer.domain.services.interpolation import LogLinearInterpolator
from psd_analyzer.domain.services.queries import evaluate_at_sizes

curve = evaluate_at_sizes(mixed_psd, (10, 45, 75, 100), LogLinearInterpolator())
```

粒径列表由调用方指定，必须严格递增、无重复且为正数；返回既有 `EvaluatedCurve`。查询服务委托 Task 3 的 `PSDInterpolator`，没有第二套插值公式。默认 `TailPolicy.CLAMP` 延续实测端点，也支持显式传入现有 `STRICT` / `CONFIRMED` / `ERROR` 策略。

## 与既有分析流程的关系

`analyze_mixture` 仍沿用 profile 的固定评价网格以保证历史比较一致，内部复用相同 fitter 和 metrics；直接对 Task 3 的混合 `PSD` 调用 `fit_q` 则使用该 PSD 的并集节点。两者节点权重不同，不能把其结果不加说明地直接比较。Task 4 不增加新的 application 编排框架。
