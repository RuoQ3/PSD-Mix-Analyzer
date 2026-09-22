# 集成测试

`test_excel_analysis.py` 在临时目录写入一个小型 workbook，经正式 Excel 导入接口生成领域对象，再调用 Task 3 质量混合与 Task 4 模型、拟合和指标服务。

人工可验证数据：粒径 `1,16,81,256,625 μm` 的四次方根为 `1,2,3,4,5`，Modified Andreasen 在 q=0.25、Dmin=1、Dmax=625 时累计通过率为 `0,0.25,0.5,0.75,1`。两个相同分布按 25% / 75% 混合后不变。没有在导入器或测试中复制拟合算法。

运行：`python -m pytest tests/integration`。需安装 `.[dev,excel,visualization]`。

`test_application_visualization.py` 验证固定配方分析结果直接生成 PSD Figure，批次比较结果直接生成 PSD／差值／关键粒径／q 图，以及 Excel Draft 经研发模拟后生成图。测试还确认 equivalent q 与 target q 分开、模拟标记明确、输入领域对象不被修改。
