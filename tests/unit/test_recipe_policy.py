from dataclasses import FrozenInstanceError, replace

import pytest

from psd_analyzer.domain.exceptions import RecipeLockedError
from psd_analyzer.domain.models.recipe import RecipeLine, RecipeStatus, RecipeVersion
from psd_analyzer.domain.policies.recipe_policy import (
    create_simulation_recipe,
    revise_draft,
    validate_selection,
)


@pytest.fixture
def recipe():
    return RecipeVersion(
        "r",
        "Recipe",
        "1",
        (RecipeLine("A", "m1", 1),),
        RecipeStatus.RELEASED,
        "external-approval-001",
    )


def test_production_lock_and_substitution(recipe, component):
    validate_selection(recipe, (component(),))
    alternate = component(material="domestic")
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, (alternate,))
    validate_selection(recipe, (alternate,), substitution=True)
    assert recipe.lines[0].material_id == "m1" and recipe.lines[0].mass_fraction == 1
    with pytest.raises(FrozenInstanceError):
        recipe.lines[0].mass_fraction = 0.5
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, (component(weight=0.5),))
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, ())
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, (component(line="B"),))
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, (component(), component()))
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, (component(weight=0),))


def test_released_and_archived_cannot_be_revised(recipe, component):
    with pytest.raises(RecipeLockedError):
        revise_draft(recipe, (RecipeLine("A", "m1", 1),))
    archived = replace(recipe, status=RecipeStatus.ARCHIVED)
    with pytest.raises(RecipeLockedError):
        revise_draft(archived, recipe.lines)
    with pytest.raises(RecipeLockedError):
        validate_selection(archived, (component(),))


def test_simulation_copies_without_mutating_source(recipe):
    lines = (RecipeLine("A", "m1", 0.4), RecipeLine("B", "m2", 0.6))
    simulation = create_simulation_recipe(recipe, scenario_id="simulation-001", lines=lines)
    assert simulation.status == RecipeStatus.DRAFT
    assert simulation.recipe_id != recipe.recipe_id
    assert "非正式生产配方" in simulation.name
    assert recipe.lines == (RecipeLine("A", "m1", 1),)
    revised = revise_draft(simulation, (RecipeLine("A", "m1", 1),))
    assert revised.lines[0].mass_fraction == 1
    assert simulation.lines[0].mass_fraction == 0.4


def test_zero_line_and_allowed_alternative(component):
    recipe = RecipeVersion(
        "r",
        "R",
        "1",
        (RecipeLine("A", "m1", 1, ("m1", "m2")), RecipeLine("B", "m3", 0)),
        RecipeStatus.RELEASED,
        "ok",
    )
    validate_selection(recipe, (component(material="m2"),))
    with pytest.raises(RecipeLockedError):
        validate_selection(recipe, (component(), component(line="unknown", weight=0)))


def test_simulation_cannot_reuse_source_identity(recipe):
    with pytest.raises(RecipeLockedError):
        create_simulation_recipe(recipe, scenario_id=recipe.recipe_id, lines=recipe.lines)
