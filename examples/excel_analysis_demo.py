"""Generate example input, import it, then invoke the existing numerical services."""

from pathlib import Path
from tempfile import TemporaryDirectory

from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.services.interpolation import LogSizeLinearInterpolator
from psd_analyzer.domain.services.losses import SquaredErrorLoss
from psd_analyzer.domain.services.packing_models import ModifiedAndreasen
from psd_analyzer.domain.services.psd_mixing import PSDMixingService
from psd_analyzer.domain.services.q_fitting import fit_q
from psd_analyzer.infrastructure.excel import generate_excel_template, import_excel_workbook


def main() -> None:
    """Exercise a synthetic workbook without persisting production data."""
    with TemporaryDirectory(prefix="psd-example-") as directory:
        path = Path(directory) / "example.xlsx"
        generate_excel_template(path)
        imported = import_excel_workbook(path)

    recipe = imported.recipes[0]
    # This example deliberately requires one batch and one measurement per material.
    # Production callers must supply an explicit selection for ambiguous histories.
    selected = {}
    for line in recipe.lines:
        batches = [b for b in imported.batches if b.material_id == line.material_id]
        if len(batches) != 1:
            raise RuntimeError("Example requires an explicit unique batch for each material")
        measurements = [m for m in imported.measurements if m.batch_id == batches[0].batch_id]
        if len(measurements) != 1:
            raise RuntimeError("Example requires one selected measurement per batch")
        selected[line.material_id] = measurements[0].psd

    mixed = PSDMixingService().mix(
        tuple(selected[line.material_id] for line in recipe.lines),
        tuple(line.mass_fraction for line in recipe.lines),
        LogSizeLinearInterpolator(),
    )
    profile = AnalysisProfile("example-only", "1", 1, 625)
    fit = fit_q(
        mixed.particle_size_um,
        mixed.cumulative_passing,
        profile=profile,
        model=ModifiedAndreasen(),
        loss=SquaredErrorLoss(),
    )
    print(f"Illustrative recipe: {recipe.name}; imported status: {recipe.status}")
    print(f"Mixed PSD nodes: {len(mixed.particle_size_um)}")
    print(f"Fit status: {fit.status}; equivalent q: {fit.equivalent_q}")
    if fit.metrics is not None:
        print(f"SSE: {fit.metrics.sse:.8g}; RMSE: {fit.metrics.rmse:.8g}")


if __name__ == "__main__":
    main()
