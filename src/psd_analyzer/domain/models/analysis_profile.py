"""A frozen numerical convention for comparable historical results."""

from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import DomainValidationError
from ..validation import finite, identifier, positive, sizes, vector
from .psd import DistributionBasis

DEFAULT_Q_BOUNDS = (0.05, 1.0)


class InterpolationMethod(StrEnum):
    LINEAR = "linear"
    LOG_LINEAR = "log-linear"


class TailPolicy(StrEnum):
    """Explicit out-of-range behavior; STRICT retains missing coverage, ERROR raises."""

    STRICT = "strict"
    CONFIRMED = "confirmed"
    CLAMP = "clamp"
    ERROR = "error"


@dataclass(frozen=True)
class AnalysisProfile:
    profile_id: str
    version: str
    d_min_um: float
    d_max_um: float
    grid_points: int = 201
    mix_basis: DistributionBasis = DistributionBasis.MASS
    interpolation: InterpolationMethod = InterpolationMethod.LOG_LINEAR
    tail_policy: TailPolicy = TailPolicy.CONFIRMED
    model_id: str = "modified-andreasen"
    loss_id: str = "sse"
    q_bounds: tuple[float, float] = DEFAULT_Q_BOUNDS
    target_q: float | None = None
    key_sizes_um: tuple[float, ...] = (10.0, 45.0, 75.0, 100.0, 500.0, 1000.0)
    q_tolerance: float = 1e-8
    scan_points: int = 101
    weak_loss_span: float = 1e-12
    measurement_compatibility_confirmed: bool = False

    def __post_init__(self) -> None:
        if type(self.measurement_compatibility_confirmed) is not bool:
            raise DomainValidationError("Measurement compatibility confirmation must be boolean")
        for name in ("profile_id", "version", "model_id", "loss_id"):
            identifier(getattr(self, name), name)
        lo, hi = positive(self.d_min_um, "Dmin"), positive(self.d_max_um, "Dmax")
        if lo >= hi:
            raise DomainValidationError("Dmin must be smaller than Dmax")
        for name, minimum in (("grid_points", 3), ("scan_points", 5)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise DomainValidationError(f"{name} must be an integer >= {minimum}")
        if not isinstance(self.mix_basis, DistributionBasis) or self.mix_basis not in (
            DistributionBasis.MASS,
            DistributionBasis.VOLUME,
        ):
            raise DomainValidationError("Mixed PSD basis must be mass or volume")
        if not isinstance(self.interpolation, InterpolationMethod):
            raise DomainValidationError("Invalid interpolation method")
        if not isinstance(self.tail_policy, TailPolicy):
            raise DomainValidationError("Invalid tail policy")
        bounds = vector(self.q_bounds, "q_bounds")
        if len(bounds) != 2 or bounds[0] >= bounds[1]:
            raise DomainValidationError("q_bounds must contain two increasing finite values")
        tolerance = positive(self.q_tolerance, "q_tolerance")
        if tolerance >= bounds[1] - bounds[0]:
            raise DomainValidationError("q_tolerance must be smaller than the search interval")
        span = positive(self.weak_loss_span, "weak_loss_span")
        target = None if self.target_q is None else finite(self.target_q, "target_q")
        if self.model_id == "modified-andreasen":
            if bounds[0] <= 0 or (target is not None and target <= 0):
                raise DomainValidationError(
                    "Modified Andreasen requires positive q bounds and target q"
                )
        object.__setattr__(self, "d_min_um", lo)
        object.__setattr__(self, "d_max_um", hi)
        object.__setattr__(self, "q_bounds", bounds)
        object.__setattr__(self, "key_sizes_um", sizes(self.key_sizes_um))
        object.__setattr__(self, "q_tolerance", tolerance)
        object.__setattr__(self, "weak_loss_span", span)
        object.__setattr__(self, "target_q", target)
