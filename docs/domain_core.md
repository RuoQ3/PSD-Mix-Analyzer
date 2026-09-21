# M2：Domain Core 交付说明

本阶段完成目录框架、纯计算核心、配方约束、单元和架构测试、示例与 CI 配置。没有实现 Excel、SQLite、页面或外部设备控制。

## 模块映射

| 文件 | 主要责任 |
|---|---|
| domain/models/psd.py | PSD 与测量版本、统计基准、尾部确认 |
| domain/models/material.py | 原料品种、批次、密度类型 |
| domain/models/recipe.py | 配方版本、配方行、实际混合输入快照 |
| domain/models/analysis_profile.py | 不可变分析参数与数值口径 |
| domain/models/analysis_result.py | 曲线、q 状态、误差、差异与诊断 |
| domain/policies/recipe_policy.py | 正式配方锁定、替代校验、研发副本 |
| domain/services/grid.py | 固定评价网格 |
| domain/services/interpolation.py | 插值与覆盖缺失 |
| domain/services/basis_conversion.py | 统计基准和质量/体积权重 |
| domain/services/mixing.py | 统一节点加权混合 |
| domain/services/packing_models.py | 唯一的 Modified Andreasen 实现 |
| domain/services/q_fitting.py | 有界拟合与状态诊断 |
| domain/services/losses.py、metrics.py | 可替换损失与统一评价指标 |
| domain/services/analysis.py | 无 I/O 的纯数值组合计算 |
| domain/services/comparison.py | 相同口径下的基准差异 |

analysis.py 只组织纯数学调用，后续 Application 仍负责加载、选择业务模式、配方版本/批次校验与保存事务。Domain 不读取配置文件或数据库。

## 验证范围

包括单原料恒等、相同 PSD 任意比例、不同粒径网格手算、正权重混合、质量/体积差异、输入异常、端点和近零 q、已知 q 恢复、拟合失败、可替换策略、配置不兼容、替代差异及模拟隔离。

自动架构检查验证 Domain 不依赖 UI/ORM/Excel；另在禁止导入 Streamlit、Plotly、Pandas、SQLAlchemy、openpyxl 的子进程中加载核心。

版本锁定和检查命令见 README。合成数据用于验证数学与工程约束；真实原料数据、测量协议与现场允许波动范围在后续导入和验收阶段核实。

## 本次验证结果

Python 3.12.14：126 项测试通过；Domain 行与分支综合覆盖率 99.22%；Ruff 检查和格式检查通过；mypy 检查 36 个源文件通过；editable 安装与独立示例运行通过。

示例替代前后保持 60%/40% 质量比例，P10 下降 6.0 个百分点，与手算一致。超出测量范围的 P500 为 None，原配方未变化。

以上为本地验证结果；远程 GitHub Actions 状态请查看仓库 Actions 页面。

## 第一阶段设计的落实与延后

- 已落实所有核心数值口径和可替换接口。
- AnalysisResult 携带输入、配置、实际权重和算法版本，但不生成时间戳或进行保存。
- AnalysisRecord、ReferenceBaseline 的数据库标识、Scenario 的持久化关联与审批登记留给 M3/M4；当前研发副本只实现核心不可变规则，来源引用由后续用例保存。
- 预留包保持空边界，不创建没有行为的 Repository 或 Streamlit 页面。
- 原架构文档保存于 architecture.md，作为 M1 设计快照；其“待确认/未实现”描述是原阶段状态，以本文件和 README 为实际进度。

下一阶段：Excel IO + Repository。先落实模板、单位转换和集中错误报告，再落实不可覆盖的版本与输入快照持久化。
