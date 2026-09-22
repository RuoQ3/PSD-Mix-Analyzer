"""Material identity is independent of supplier batch and measurement version."""

from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import DomainValidationError
from ..validation import identifier, positive


class DensityKind(StrEnum):
    PARTICLE = "particle"
    TRUE = "true"
    BULK = "bulk"


@dataclass(frozen=True)
class Material:
    material_id: str
    name: str
    grade: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        identifier(self.material_id, "material_id")
        identifier(self.name, "name")


@dataclass(frozen=True)
class MaterialBatch:
    """A batch identity; an empty supplier denotes metadata not supplied."""

    batch_id: str
    material_id: str
    supplier: str
    batch_no: str
    density_kg_m3: float | None = None
    density_kind: DensityKind | None = None

    def __post_init__(self) -> None:
        for name in ("batch_id", "material_id", "batch_no"):
            identifier(getattr(self, name), name)
        if not isinstance(self.supplier, str):
            raise DomainValidationError("supplier must be a string; use empty text if unknown")
        if (self.density_kg_m3 is None) != (self.density_kind is None):
            raise DomainValidationError("Density value and kind must be supplied together")
        if self.density_kg_m3 is not None:
            object.__setattr__(self, "density_kg_m3", positive(self.density_kg_m3, "density"))
            if not isinstance(self.density_kind, DensityKind):
                raise DomainValidationError("density_kind must be a DensityKind")
