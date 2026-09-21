"""Immutable cumulative distributions in micrometres and fractions."""

from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import DomainValidationError
from ..validation import identifier, sizes, vector


class DistributionBasis(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    NUMBER = "number"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PSD:
    particle_size_um: tuple[float, ...]
    cumulative_passing: tuple[float, ...]
    basis: DistributionBasis = DistributionBasis.MASS
    lower_tail_confirmed: bool = False
    upper_tail_confirmed: bool = False

    def __post_init__(self) -> None:
        x = sizes(self.particle_size_um, minimum_count=2)
        p = vector(self.cumulative_passing, "cumulative_passing")
        if len(x) != len(p):
            raise DomainValidationError("Size and passing vectors must have equal length")
        if any(v < 0 or v > 1 for v in p):
            raise DomainValidationError("Cumulative passing must be within [0, 1]")
        if any(a > b for a, b in zip(p, p[1:], strict=False)):
            raise DomainValidationError("Cumulative passing must be nondecreasing")
        if not isinstance(self.basis, DistributionBasis):
            raise DomainValidationError("basis must be a DistributionBasis")
        if (
            type(self.lower_tail_confirmed) is not bool
            or type(self.upper_tail_confirmed) is not bool
        ):
            raise DomainValidationError("Tail confirmations must be booleans")
        if self.lower_tail_confirmed and p[0] != 0:
            raise DomainValidationError("Confirmed lower tail requires an observed zero endpoint")
        if self.upper_tail_confirmed and p[-1] != 1:
            raise DomainValidationError("Confirmed upper tail requires an observed one endpoint")
        object.__setattr__(self, "particle_size_um", x)
        object.__setattr__(self, "cumulative_passing", p)


@dataclass(frozen=True)
class PSDMeasurement:
    psd_id: str
    batch_id: str
    version: str
    psd: PSD
    method: str
    protocol_id: str
    source_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("psd_id", "batch_id", "version", "method", "protocol_id"):
            identifier(getattr(self, name), name)
        if not isinstance(self.psd, PSD):
            raise DomainValidationError("measurement.psd must be a validated PSD")
