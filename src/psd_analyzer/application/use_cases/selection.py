"""Resolve recipe selections without changing fractions or selecting batches implicitly."""

from collections.abc import Sequence

from ...domain.exceptions import RecipeLockedError
from ...domain.models.recipe import MixtureComponent, RecipeStatus, RecipeVersion
from ...domain.policies.recipe_policy import validate_selection
from ..exceptions import MissingMaterialPSD


def select_components(
    recipe: RecipeVersion,
    components: Sequence[MixtureComponent],
    *,
    simulation: bool = False,
    substitution: bool = False,
) -> tuple[MixtureComponent, ...]:
    """Order by recipe lines, retaining explicit batch and measurement provenance."""
    selected = {c.line_id: c for c in components}
    if len(selected) != len(components):
        raise RecipeLockedError("Duplicate selected line IDs")
    missing = [
        line.line_id
        for line in recipe.lines
        if line.mass_fraction > 0 and line.line_id not in selected
    ]
    if missing:
        raise MissingMaterialPSD(f"Missing material PSD for recipe lines: {', '.join(missing)}")
    if simulation:
        if recipe.status != RecipeStatus.DRAFT:
            raise RecipeLockedError("Simulation requires an explicitly separate draft recipe")
        lines = {line.line_id: line for line in recipe.lines}
        for component in components:
            line = lines.get(component.line_id)
            if line is None or component.mass_fraction != line.mass_fraction:
                raise RecipeLockedError("Selections must match draft recipe lines and fractions")
            if component.batch.material_id not in line.allowed_material_ids:
                raise RecipeLockedError("Selected material does not belong to the draft recipe")
    else:
        validate_selection(recipe, components, substitution=substitution)
    return tuple(selected[line.line_id] for line in recipe.lines if line.line_id in selected)
