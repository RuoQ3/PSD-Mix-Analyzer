"""Versioned recipes and immutable mixture input snapshots."""

from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import DomainValidationError
from ..validation import finite, fractions, identifier
from .material import MaterialBatch
from .psd import PSDMeasurement


class RecipeStatus(StrEnum):
    DRAFT = "draft"
    RELEASED = "released"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class RecipeLine:
    line_id: str
    material_id: str
    mass_fraction: float
    allowed_material_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identifier(self.line_id, "line_id")
        identifier(self.material_id, "material_id")
        value = finite(self.mass_fraction, "mass_fraction")
        if value < 0 or value > 1:
            raise DomainValidationError("mass_fraction must be within [0, 1]")
        allowed = tuple(self.allowed_material_ids) or (self.material_id,)
        for item in allowed:
            identifier(item, "allowed_material_id")
        object.__setattr__(self, "mass_fraction", value)
        object.__setattr__(self, "allowed_material_ids", allowed)


@dataclass(frozen=True)
class RecipeVersion:
    recipe_id: str
    name: str
    version: str
    lines: tuple[RecipeLine, ...]
    status: RecipeStatus = RecipeStatus.DRAFT
    approval_reference: str = ""

    def __post_init__(self) -> None:
        for name in ("recipe_id", "name", "version"):
            identifier(getattr(self, name), name)
        lines = tuple(self.lines)
        if not isinstance(self.status, RecipeStatus):
            raise DomainValidationError("status must be a RecipeStatus")
        if not all(isinstance(line, RecipeLine) for line in lines):
            raise DomainValidationError("lines must contain RecipeLine objects")
        if len({line.line_id for line in lines}) != len(lines):
            raise DomainValidationError("Recipe line IDs must be unique")
        fractions(line.mass_fraction for line in lines)
        if self.status != RecipeStatus.DRAFT:
            identifier(self.approval_reference, "approval_reference")
        object.__setattr__(self, "lines", lines)


@dataclass(frozen=True)
class MixtureComponent:
    line_id: str
    batch: MaterialBatch
    measurement: PSDMeasurement
    mass_fraction: float
    uniform_density_confirmed: bool = False

    def __post_init__(self) -> None:
        identifier(self.line_id, "line_id")
        if not isinstance(self.batch, MaterialBatch) or not isinstance(
            self.measurement, PSDMeasurement
        ):
            raise DomainValidationError("Component requires a batch and validated PSD measurement")
        if self.measurement.batch_id != self.batch.batch_id:
            raise DomainValidationError("PSD measurement does not belong to the selected batch")
        value = finite(self.mass_fraction, "mass_fraction")
        if not 0 <= value <= 1:
            raise DomainValidationError("mass_fraction must be within [0, 1]")
        if type(self.uniform_density_confirmed) is not bool:
            raise DomainValidationError("uniform_density_confirmed must be boolean")
        object.__setattr__(self, "mass_fraction", value)
