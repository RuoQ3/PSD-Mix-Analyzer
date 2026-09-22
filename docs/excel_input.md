# Task 5：Excel 数据输入

Excel 模块位于 `infrastructure/excel`，只读取、校验、转换数据，返回已有不可变领域对象。它不选择批次，不计算混合 PSD、q 或指标，不读写数据库。数学核心无需安装 Excel 依赖。

## 安装与入口

```bash
python -m pip install -e ".[dev,excel]" -c requirements.lock
python examples/excel_analysis_demo.py
```

```python
from psd_analyzer.infrastructure.excel import (
    ExcelImportError,
    generate_excel_template,
    import_excel_workbook,
)

generate_excel_template("PSD_Mix_Analyzer_Template.xlsx")
try:
    imported = import_excel_workbook("PSD_Mix_Analyzer_Template.xlsx")
except ExcelImportError as exc:
    for issue in exc.issues:
        print(issue.file, issue.sheet, issue.row, issue.column,
              issue.value, issue.code, issue.message)
```

模板默认包含明确标注为 EXAMPLE ONLY 的虚构数据，不能当作实际配方。`include_example=False` 生成空模板；填入合法数据后才能导入，空模板本身会报告缺少数据。生成操作会写入指定路径。

## 模板与既有架构的关系

沿用 `architecture.md` 的批次、测量、配方分离设计，因此使用以下四个必需数据页，并额外生成可选的 `说明` 页。配方页名称为 **Recipe（单数）**。不同批次或复测不能只用原料名称关联。

| Sheet | 必需列 | 可选列 |
|---|---|---|
| Materials | material_code, material_name, batch_key, batch_no | supplier, grade, notes, density, density_kind |
| Measurements | measurement_key, batch_key, basis, method, protocol | version |
| PSD | measurement_key, particle_size_um, cumulative_passing_pct | — |
| Recipe | recipe_code, recipe_version, line_key, material_code, mass_fraction_pct | recipe_name, status, approval_reference |

第一行填写列名；列名和 Sheet 名区分大小写。标识和版本用文本填写，例如 `A001`、`v1`、文本 `1`，避免 Excel 丢失前导零。未知附加列不参与当前领域映射。当前领域对象没有 `tested_at` 字段，本版不导入测试日期。

- 同一 `material_code` 可以对应多行不同批次，但 material_name、grade、notes 必须一致；`batch_key` 全工作簿唯一。
- `measurement_key` 全工作簿唯一，通过 `batch_key` 指向批次。未填写 measurement version 时使用文本 `1`。
- `basis` 显式填写 `mass`、`volume`、`number` 或 `unknown`。输入层保留声明；Task 3 独立质量混合只接受 `mass`。
- PSD 使用长表，以 `measurement_key` 分组；每组按输入行顺序严格递增，至少两点，不自动排序。
- 配方以 `(recipe_code, recipe_version)` 分组，`line_key` 在该版本内唯一。缺省 recipe_name 使用 recipe_code。
- 密度单位 kg/m³，可空；填写时必须同时声明 `density_kind`：`particle`、`true` 或 `bulk`。导入不进行密度修正或体积分数计算。

## 百分数与安全转换

内部粒径单位 μm，通过率及配方质量比例为 `[0,1]`。百分数列支持三种明确表示：

| Excel 输入 | 读取依据 | Domain 数值 |
|---|---|---|
| 普通数值 `25` | 列名 `_pct`，数值除以 100 | 0.25 |
| 文本 `25%` | 明确的百分号 | 0.25 |
| Excel 百分比格式显示 `25%`，存储 0.25 | 单元格数值及百分比格式 | 0.25 |
| 普通数值 `0.25`，无百分比格式 | 表示 0.25%，不按数值大小猜单位 | 0.0025 |

允许去除文本首尾空白、跳过完全空白行。可选文本在 DTO 中可为 None，映射到既有 Material / MaterialBatch 时使用空字符串；未填写密度保留 None。supplier 可空，批次标识和 batch_no 仍必需。

不会删除重复粒径、修补未知粒度、平滑非单调数据、截断负值或归一化错误配方。配方总和使用 Domain 的 `FRACTION_TOLERANCE=1e-8`（分数单位），95% 等明显错误会失败。导入保留容差内原比例；后续混合仍使用已有领域比例校验。

公式单元格要求先转换成显式数值，不信任可能陈旧的公式缓存，也不执行 Excel 公式。

## 职责与错误报告

| 模块 | 职责 |
|---|---|
| reader.py | openpyxl 读取原值和格式、文件 SHA-256、Sheet 与列校验 |
| parser.py | 文本／数值解析、单位识别、逐行 DTO |
| records.py | Excel 原始逐行记录；兼容再导出 Application 的 ImportedWorkbook、ImportIssue、ExcelImportError |
| mapper.py | 关联、顺序、单调性及总比例校验；再调用领域构造器 |
| importer.py | 编排 reader → schema → parser → mapper |
| template.py | 创建标准输入模板与虚构示例 |

公共导入结果与结构化错误的唯一实现位于 `application/dto/workbook.py`，旧 `infrastructure.excel.records` 导入路径兼容保留；原始单元格 DTO 仍只属于 Infrastructure。`WorkbookGateway` 让 UI 经 Application 上传 bytes 或下载模板，不直接调用 Excel 库。

`ExcelImporter` 可注入 reader 和 schema validator。未来 CSV/API 输入适配器可构造相同领域对象，无需改数学服务；Excel DTO 不进入 Domain。

失败通过 `ExcelImportError.issues` 一次返回可收集的多个问题。每个 `ImportIssue` 包含文件、sheet、Excel 原始行号（从 1 开始）、列名、原始值、code、message、severity。无法读取文件、损坏 workbook 或缺少关键结构时提前失败。数据错误不返回部分成功结果，也不修改源文件。

校验覆盖空值、数值类型、NaN/inf、粒径正值、百分比范围、重复／未递增粒径、累计通过率下降、点数不足、未知关联、重复身份和配方比例总和。Infrastructure 校验通过后仍构造 `PSD`、`MaterialBatch`、`RecipeVersion` 等对象，领域不变量继续生效。

## 输出与后续分析

`ImportedWorkbook` 包含 `materials`、`batches`、`measurements`、`recipes` 元组及 `source_hash`。每个 PSDMeasurement 保留原文件哈希，便于后续追溯；当前不保存原文件副本或实现导入历史。

配方默认 Draft。Task 8 增加可选 `status`（draft / released / archived）和 `approval_reference`；Released / Archived 必须填写外部审批引用，同一配方版本各行必须一致。导入只保留已声明状态，不提供生产审批、发布或覆盖正式配方的入口。调用方根据配方行显式选择批次和测量，再把对应 PSD 和质量比例交给 `PSDMixingService`；对返回 PSD 调用 `fit_q`。完整示例见 `examples/excel_analysis_demo.py`。

集成测试使用粒径 `1,16,81,256,625` 与通过率 `0,25,50,75,100%` 的小文件。四次方根为 `1,2,3,4,5`，可手算验证 q=0.25，测试调用正式导入、混合、拟合和指标接口，不复制算法。
