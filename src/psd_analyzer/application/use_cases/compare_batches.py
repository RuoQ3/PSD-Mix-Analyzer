"""Fixed-proportion batch comparison on one shared calculation grid."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ...domain.exceptions import RecipeLockedError
from ...domain.models.analysis_profile import AnalysisProfile
from ...domain.models.analysis_result import AnalysisResult, ComparisonResult
from ...domain.models.recipe import MixtureComponent, RecipeVersion
from ...domain.services.comparison import compare_results
from .analyze_recipe import AnalyzeRecipePSD
from .selection import select_components


@dataclass(frozen=True)
class ComparePSDAnalysis:
    """Compare two batch selections while retaining recipe and material identity."""

    analyzer: AnalyzeRecipePSD = field(default_factory=AnalyzeRecipePSD)
    comparator: Callable[[AnalysisResult, AnalysisResult], ComparisonResult] = compare_results

    def execute(
        self,
        recipe: RecipeVersion,
        baseline_components: Sequence[MixtureComponent],
        current_components: Sequence[MixtureComponent],
        profile: AnalysisProfile,
        *,
        fit_enabled: bool = True,
    ) -> ComparisonResult:
        baseline = select_components(recipe, baseline_components)
        current = select_components(recipe, current_components)
        old_materials = {c.line_id: c.batch.material_id for c in baseline}
        new_materials = {c.line_id: c.batch.material_id for c in current}
        if old_materials != new_materials:
            raise RecipeLockedError("Batch comparison cannot change materials; use substitution")
        return self._compare(recipe, baseline, current, profile, fit_enabled=fit_enabled)

    def _compare(
        self,
        recipe: RecipeVersion,
        baseline: tuple[MixtureComponent, ...],
        current: tuple[MixtureComponent, ...],
        profile: AnalysisProfile,
        *,
        fit_enabled: bool,
    ) -> ComparisonResult:
        grid = self.analyzer.calculation_grid((*baseline, *current))
        base = self.analyzer._on_grid(recipe, baseline, profile, grid, fit_enabled=fit_enabled)
        now = self.analyzer._on_grid(recipe, current, profile, grid, fit_enabled=fit_enabled)
        return self.comparator(now, base)
