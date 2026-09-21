"""Production and substitution invariants also apply without a UI."""

from collections.abc import Sequence
from dataclasses import replace

from ..exceptions import RecipeLockedError
from ..models.recipe import MixtureComponent, RecipeLine, RecipeStatus, RecipeVersion


def validate_selection(
    recipe: RecipeVersion, components: Sequence[MixtureComponent], *, substitution: bool = False
) -> None:
    if recipe.status != RecipeStatus.RELEASED:
        raise RecipeLockedError("Production and substitution require a released recipe")
    lines = {line.line_id: line for line in recipe.lines if line.mass_fraction > 0}
    selected = {c.line_id: c for c in components if c.mass_fraction > 0}
    if len({c.line_id for c in components}) != len(components):
        raise RecipeLockedError("Duplicate selected line IDs")
    if set(selected) != set(lines) or any(
        c.line_id not in {r.line_id for r in recipe.lines} for c in components
    ):
        raise RecipeLockedError("Selections must match the recipe lines")
    by_id = {line.line_id: line for line in recipe.lines}
    for component in components:
        line = by_id[component.line_id]
        if component.mass_fraction != line.mass_fraction:
            raise RecipeLockedError("Production proportions cannot be edited")
        if not substitution and component.batch.material_id not in line.allowed_material_ids:
            raise RecipeLockedError("Material is not allowed; use a substitution scenario")


def revise_draft(recipe: RecipeVersion, lines: Sequence[RecipeLine]) -> RecipeVersion:
    if recipe.status != RecipeStatus.DRAFT:
        raise RecipeLockedError("Released or archived versions are immutable")
    return replace(recipe, lines=tuple(lines))


def create_simulation_recipe(
    recipe: RecipeVersion, *, scenario_id: str, lines: Sequence[RecipeLine]
) -> RecipeVersion:
    if scenario_id == recipe.recipe_id:
        raise RecipeLockedError(
            "A simulation must have an identity distinct from its source recipe"
        )
    return RecipeVersion(
        scenario_id,
        f"{recipe.name} — 研发模拟，非正式生产配方",
        "1",
        tuple(lines),
        RecipeStatus.DRAFT,
    )
