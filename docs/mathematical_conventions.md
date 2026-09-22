# 数学与接口约定

本文件描述既有完整分析流程。Task 3 新增的独立质量混合入口默认使用节点并集与 clamp，详情见 [Task 3 模块说明](psd_interpolation_mixing.md)；不会替换下面的固定 q 评价网格。

## 输入和统计基准

PSD 是非降累计分布。粒径必须为有限正数且严格递增，通过率为 [0,1]；缺少统计基准的测量允许表示，但不能参与计算。输入序列转为 tuple，外部修改列表或数组不会改动对象。

配方质量分数非负且总和与 1 的差不大于 1e-8。只在该浮点容差内归一化，保留原始比例总和和诊断；明显缺项不会自动归一化。正比例固体组分都必须有测量。

质量累计混合为 `sum(w_i * P_i(D))`。体积混合权重为 `(w_i / rho_i) / sum(w_j / rho_j)`。转换权重与加权求和分别实现。

单原料 mass 与 volume 的累计曲线等同仅在该原料内部密度与粒径无关的假设下成立；通过 `uniform_density_confirmed=True` 明确记录。整体体积混合还需要每个正比例组分的密度。`particle` 或 `true` 密度是否与具体多孔原料的体积定义相符，需要工程人员确认，程序不会用 `bulk` 松装/堆积密度替代。

不同测试协议在 `AnalysisProfile.measurement_compatibility_confirmed=True` 时才允许组合；这一确认不能消除测试方法的系统差异。新旧批次比较依然要求每个配方位置的 method 与 protocol_id 不变。

## 网格与尾部

分析采用固定的对数网格，默认 201 点。节点和模型边界属于 profile，关键粒径独立计算，不进入 q 的损失函数。默认关键点 10、45、75、100、500、1000 μm，可配置。

Linear 对 D 分段线性插值；LogLinear 对 ln(D) 分段线性插值，均不对累计通过率取对数。

strict 不超出测量范围；confirmed 仅允许明确确认且实测端点为精确 0 或 1 的尾部延续。不根据模型边界强行修改实测端点。原始数据的仪器舍入、近似 100% 或测量检出限需要上游明确处理，核心不会猜测。

`EvaluatedCurve` 保留固定网格和 `None` 掩码。只要一个正比例组分在某节点缺失，混合该节点即缺失。完整拟合覆盖不足时保留已有混合结果，但返回 `insufficient_coverage`，不拟合 q，也不计算假装完整的误差。

## 模型与拟合

Modified Andreasen / Funk-Dinger 使用同一实现：

`P(D) = (D**q - Dmin**q) / (Dmax**q - Dmin**q)`。

模型区间外为 0/1。q→0 时为 `ln(D/Dmin)/ln(Dmax/Dmin)`。实现通过对数和非正指数的 expm1 形式避免相近幂相减与幂溢出；Dmin 必须大于 0。

默认损失为固定网格 SSE。q 范围默认 [0,1]，先扫描 101 点识别候选极小值区间，再进行有界标量最小化，并比较边界候选。可替换损失；扫描并不构成任意多峰损失的全局最优证明。

q_tolerance 默认 1e-8，边界诊断使用其 10 倍。扫描损失跨度 ≤1e-12 时默认标记 weakly_identified。均为可配置数值诊断，不是产品质量阈值。

`target_q` 和 `equivalent_q` 独立。目标与最佳拟合的 RMSE、MAE、SSE、最大绝对偏差分别保存。拟合模型的能力通过 QFittableModel 声明，无 q 的自定义目标仍可生成目标曲线和误差，其拟合状态为 not_applicable。

状态：success、at_bound、weakly_identified、insufficient_coverage、failed、not_applicable。失败或辨识不足不以 q=0 替代。默认不生成统计置信区间，插值节点不是独立试验重复。

## 可比性

compare_results 要求 profile 完全一致（包含 ID/版本、目标 q、统计基准、边界、网格、方法、损失、范围和容差）、算法版本一致、配方行及原始质量比例一致、各行测试协议一致。排序后的配方行对比不受调用者输入顺序影响。

这是严格的工程约定。即使两份不同版本配置恰好数值相同，也须显式重算到同一配置，不静默混用。部分覆盖记录不能进入标准比较。

差值为 current - baseline，累计通过率差值内部为分数，显示时转为百分点。只有两个 success 拟合才提供常规 Δq；边界拟合仍可比较完整曲线，但 Δq 返回 None 并附原因。

质量基准 q 与体积基准 q 分开解释；两者均不预测真实堆积密度、强度或热震性能。

## 扩展契约

自定义插值实现 PSDInterpolator；模型实现 PackingModel，需要拟合时同时实现 evaluate_q；损失实现 LossFunction。实现的 method_id/model_id/loss_id 必须与配置一致。改变算法实现时应改变算法或配置版本，ID 不是自动生成的内容指纹。

输出累计曲线必须有限、长度匹配、单调且在 [0,1]。不允许替换策略产生非法曲线后继续保存可信指标。核心输入错误抛 DomainValidationError 子类，数值拟合过程失败通过 FitResult 表达。

生产模式在 Application 实现前，调用方须显式调用 validate_selection。数学核心本身支持研发比例，这是设计能力，不是自动修改正式配方。
