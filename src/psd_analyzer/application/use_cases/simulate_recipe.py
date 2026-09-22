"""Explicit draft-only research analysis, with no production-release operation."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from ...domain.models.analysis_profile import AnalysisProfile
from ...domain.models.analysis_result import AnalysisResult
from ...domain.models.recipe import MixtureComponent, RecipeVersion
from .analyze_recipe import AnalyzeRecipePSD
from .selection import select_components


@dataclass(frozen=True)
class SimulateRecipe:
    """Analyze user-specified draft fractions without modifying any recipe."""

    analyzer: AnalyzeRecipePSD = field(default_factory=AnalyzeRecipePSD)

    def execute(
        self,
        recipe: RecipeVersion,
        components: Sequence[MixtureComponent],
        profile: AnalysisProfile,
        *,
        fit_enabled: bool = True,
    ) -> AnalysisResult:
        ordered = select_components(recipe, components, simulation=True)
        return self.analyzer._on_grid(
            recipe,
            ordered,
            profile,
            self.analyzer.calculation_grid(ordered),
            fit_enabled=fit_enabled,
            simulation=True,
        )
