"""Analyze fictional batches and optionally export standalone, interactive HTML figures."""

import argparse
from dataclasses import replace
from pathlib import Path

from psd_analyzer.application.use_cases import AnalyzeRecipePSD, ComparePSDAnalysis
from psd_analyzer.domain.models.analysis_profile import AnalysisProfile, TailPolicy
from psd_analyzer.domain.models.material import MaterialBatch
from psd_analyzer.domain.models.psd import PSD, PSDMeasurement
from psd_analyzer.domain.models.recipe import (
    MixtureComponent,
    RecipeLine,
    RecipeStatus,
    RecipeVersion,
)
from psd_analyzer.visualization import (
    build_key_size_comparison_figure,
    build_psd_difference_figure,
    build_psd_figure,
    build_q_comparison_figure,
)


def main() -> None:
    """Keep numerical analysis in use cases and pass their results directly to builders."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Optionally write standalone HTML figures")
    args = parser.parse_args()
    baseline_psd = PSD((1, 16, 81, 256, 625), (0, 0.25, 0.5, 0.75, 1))
    baseline_batch = MaterialBatch("example-batch-1", "example-A", "Example supplier", "example-1")
    measurement = PSDMeasurement(
        "example-PSD-1", baseline_batch.batch_id, "1", baseline_psd, "example", "example-v1"
    )
    baseline = (MixtureComponent("line-A", baseline_batch, measurement, 1),)
    current_batch = replace(baseline_batch, batch_id="example-batch-2", batch_no="example-2")
    current_measurement = replace(
        measurement,
        psd_id="example-PSD-2",
        batch_id=current_batch.batch_id,
        psd=PSD(baseline_psd.particle_size_um, (0, 0.125, 1 / 3, 0.625, 1)),
    )
    current = (MixtureComponent("line-A", current_batch, current_measurement, 1),)
    recipe = RecipeVersion(
        "example-recipe",
        "Fictional fixed recipe",
        "1",
        (RecipeLine("line-A", "example-A", 1),),
        RecipeStatus.RELEASED,
        "example-only-not-production",
    )
    profile = AnalysisProfile(
        "example-analysis",
        "1",
        1,
        625,
        target_q=0.3,
        key_sizes_um=(16, 81, 256),
        tail_policy=TailPolicy.CLAMP,
    )
    analysis = AnalyzeRecipePSD().execute(recipe, current, profile)
    comparison = ComparePSDAnalysis().execute(recipe, baseline, current, profile)
    figures = {
        "analysis": build_psd_figure(analysis),
        "batches": build_psd_figure(comparison),
        "difference": build_psd_difference_figure(comparison),
        "key_sizes": build_key_size_comparison_figure(comparison),
        "q_comparison": build_q_comparison_figure(comparison),
    }
    print("Fictional data only; no production recipe is modified.")
    print(f"Equivalent q: {analysis.equivalent_q}; target q: {analysis.target_q}")
    print(f"Batch delta q: {comparison.delta_q}; metrics: {comparison.metrics}")
    for name, figure in figures.items():
        # Serialize the full Figure to exercise the frontend-facing structure in CI.
        figure.to_json()
        print(f"{name}: {len(figure.data)} traces")
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, figure in figures.items():
            figure.write_html(args.output_dir / f"{name}.html", include_plotlyjs=True)
        print(f"Standalone HTML figures written to {args.output_dir}")


if __name__ == "__main__":
    main()
