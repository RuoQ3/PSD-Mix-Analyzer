"""Run after `python -m pip install -e .`; all data below are synthetic."""

import json

from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.models.material import DensityKind, MaterialBatch
from psd_analyzer.domain.models.psd import PSD, PSDMeasurement
from psd_analyzer.domain.models.recipe import (
    MixtureComponent,
    RecipeLine,
    RecipeStatus,
    RecipeVersion,
)
from psd_analyzer.domain.policies.recipe_policy import validate_selection
from psd_analyzer.domain.services.analysis import analyze_mixture
from psd_analyzer.domain.services.basis_conversion import mass_to_volume_fractions
from psd_analyzer.domain.services.comparison import compare_results


def make_component(
    line: str, material: str, fraction: float, passing: tuple[float, ...]
) -> MixtureComponent:
    batch = MaterialBatch(
        f"batch-{material}", material, "demo-supplier", "demo-001", 2500, DensityKind.PARTICLE
    )
    psd = PSD((1.0, 10.0, 100.0), passing)
    measurement = PSDMeasurement(f"psd-{material}", batch.batch_id, "1", psd, "laser", "demo-v1")
    return MixtureComponent(line, batch, measurement, fraction)


def main() -> None:
    recipe = RecipeVersion(
        "demo",
        "演示固定配方",
        "1",
        (RecipeLine("A", "original", 0.6), RecipeLine("B", "coarse", 0.4)),
        RecipeStatus.RELEASED,
        "synthetic-demo-only",
    )
    fine = make_component("A", "original", 0.6, (0.0, 0.65, 1.0))
    coarse = make_component("B", "coarse", 0.4, (0.0, 0.2, 1.0))
    replacement = make_component("A", "candidate", 0.6, (0.0, 0.55, 1.0))
    profile = AnalysisProfile(
        "demo-profile", "1", 1, 100, target_q=0.3, key_sizes_um=(10.0, 45.0, 100.0, 500.0)
    )
    validate_selection(recipe, (fine, coarse))
    validate_selection(recipe, (replacement, coarse), substitution=True)
    baseline = analyze_mixture((fine, coarse), profile)
    candidate = analyze_mixture((replacement, coarse), profile)
    difference = compare_results(candidate, baseline)
    # Same proportions, lower P(10) in candidate: .6 * (.55 - .65) = -.06.
    summary = {
        "data": "synthetic; not a production recommendation",
        "baseline_q": baseline.fit.equivalent_q,
        "candidate_q": candidate.fit.equivalent_q,
        "delta_q": difference.delta_q,
        "delta_P10_percentage_points": difference.key_delta[0].cumulative_passing * 100,
        "P500": candidate.key_passing[-1].cumulative_passing,
        "P500_reason": candidate.key_passing[-1].reason,
        "equal_mass_volume_fractions_at_density_2000_4000": mass_to_volume_fractions(
            (0.5, 0.5), (2000, 4000)
        ),
        "recipe_unchanged": recipe.lines[0].mass_fraction == 0.6,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
