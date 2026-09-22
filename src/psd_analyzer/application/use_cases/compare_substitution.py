"""Explicit material replacements preserve every recipe fraction."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ...domain.exceptions import RecipeLockedError
from ...domain.models.analysis_profile import AnalysisProfile
from ...domain.models.analysis_result import ComparisonResult
from ...domain.models.recipe import MixtureComponent, RecipeVersion
from .compare_batches import ComparePSDAnalysis
from .selection import select_components


@dataclass(frozen=True)
class CompareMaterialSubstitution:
    """Replace only named lines, never rebalance other components."""

    comparison: ComparePSDAnalysis = field(default_factory=ComparePSDAnalysis)

    def execute(
        self,
        recipe: RecipeVersion,
        original_components: Sequence[MixtureComponent],
        replacements: Mapping[str, MixtureComponent],
        profile: AnalysisProfile,
        *,
        fit_enabled: bool = True,
    ) -> ComparisonResult:
        original = select_components(recipe, original_components)
        selected = {c.line_id: c for c in original}
        for line_id, component in replacements.items():
            if line_id not in selected or component.line_id != line_id:
                raise RecipeLockedError("Replacement must name an existing selected recipe line")
            selected[line_id] = component
        replaced = select_components(recipe, tuple(selected.values()), substitution=True)
        return self.comparison._compare(
            recipe, original, replaced, profile, fit_enabled=fit_enabled
        )
