"""Pure presentation conversions; numerical analysis stays in Application/Domain."""

from collections.abc import Mapping

from psd_analyzer.application.dto.workbook import ImportedWorkbook, ImportIssue
from psd_analyzer.domain.models.analysis_result import AnalysisResult, ComparisonResult
from psd_analyzer.domain.models.recipe import RecipeVersion


def issue_text(issue: ImportIssue) -> str:
    """Preserve actionable workbook, sheet and cell context in an import error."""
    location = f"{issue.file} · {issue.sheet}"
    if issue.row is not None:
        location += f" 第 {issue.row} 行"
    if issue.column:
        location += f" · {issue.column} = {issue.value!r}"
    return f"{location}：{issue.message} [{issue.code}]"


def number_text(value: float | None, *, percent: bool = False) -> str:
    """Missing measurements are displayed as unavailable, never as zero."""
    if value is None:
        return "—"
    return f"{value * 100:.3f}%" if percent else f"{value:.5g}"


def metric_values(result: AnalysisResult) -> dict[str, str]:
    """Label metrics by their actual reference; q has no quality-control meaning."""
    metrics = result.target_metrics if result.target_metrics is not None else result.fit_metrics
    reference = "目标" if result.target_metrics is not None else "拟合曲线"
    values = {"Equivalent q": number_text(result.equivalent_q)}
    if result.target_q is not None:
        values["Target q（参考）"] = number_text(result.target_q)
    values.update(
        {
            f"RMSE · {reference}": number_text(None if metrics is None else metrics.rmse),
            f"MAE · {reference}": number_text(None if metrics is None else metrics.mae),
            f"Max deviation · {reference}": number_text(
                None if metrics is None else metrics.max_absolute_deviation
            ),
        }
    )
    return values


def key_size_rows(
    result: AnalysisResult, comparison: ComparisonResult | None = None
) -> list[dict[str, float | str | None]]:
    """Render supplied key-size results and supplied differences without recomputation."""
    baseline = (
        {point.particle_size_um: point for point in comparison.baseline.key_passing}
        if comparison is not None and comparison.baseline is not None
        else {}
    )
    delta = (
        {point.particle_size_um: point for point in comparison.key_delta}
        if comparison is not None
        else {}
    )
    rows: list[dict[str, float | str | None]] = []
    for point in result.key_passing:
        row: dict[str, float | str | None] = {
            "粒径 μm": point.particle_size_um,
            "当前通过率": number_text(point.cumulative_passing, percent=True),
            "说明": point.reason or "",
        }
        if comparison is not None:
            before = baseline.get(point.particle_size_um)
            change = delta.get(point.particle_size_um)
            row["基准通过率"] = number_text(
                None if before is None else before.cumulative_passing, percent=True
            )
            row["差值 pp"] = number_text(
                None
                if change is None or change.cumulative_passing is None
                else change.cumulative_passing * 100
            )
        rows.append(row)
    return rows


def recipe_rows(recipe: RecipeVersion, workbook: ImportedWorkbook) -> list[dict[str, str | float]]:
    """Read-only recipe table used by production and substitution pages."""
    names = {material.material_id: material.name for material in workbook.materials}
    return [
        {
            "行 ID": line.line_id,
            "原料": names.get(line.material_id, line.material_id),
            "原料 ID": line.material_id,
            "正式比例 %": line.mass_fraction * 100,
        }
        for line in recipe.lines
    ]


def measurement_options(
    workbook: ImportedWorkbook, material_id: str | None = None
) -> dict[str, str]:
    """Keep measurement version and batch identity visible in selection labels."""
    batches = {batch.batch_id: batch for batch in workbook.batches}
    names = {material.material_id: material.name for material in workbook.materials}
    return {
        measurement.psd_id: (
            f"{names.get(batches[measurement.batch_id].material_id, '')} · "
            f"{batches[measurement.batch_id].batch_no} · {measurement.psd_id} "
            f"(v{measurement.version}, {measurement.protocol_id})"
        )
        for measurement in workbook.measurements
        if material_id is None or batches[measurement.batch_id].material_id == material_id
    }


def selection_signature(selections: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Stable input token lets the UI hide stale results after an input change."""
    return tuple(sorted(selections.items()))
