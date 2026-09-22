"""Key-size queries reuse the selected PSD interpolation strategy unchanged."""

from collections.abc import Sequence

from ..exceptions import DomainValidationError
from ..models.analysis_profile import TailPolicy
from ..models.analysis_result import EvaluatedCurve
from ..models.psd import PSD
from ..protocols import PSDInterpolator
from ..validation import sizes as validate_sizes


def evaluate_at_sizes(
    psd: PSD,
    sizes: Sequence[float],
    interpolator: PSDInterpolator,
    *,
    tail_policy: TailPolicy = TailPolicy.CLAMP,
) -> EvaluatedCurve:
    """Query arbitrary positive, strictly increasing sizes in μm, with no fixed key list.

    Constant measured-endpoint extension matches Task 3's mixing default. Callers
    may explicitly request another existing TailPolicy, including missing coverage.
    """
    if not isinstance(psd, PSD):
        raise DomainValidationError("Key-size queries require a validated PSD")
    grid = validate_sizes(sizes)
    if not isinstance(tail_policy, TailPolicy):
        raise DomainValidationError("Unknown tail policy")
    try:
        curve = interpolator.interpolate(psd, grid, tail_policy)
    except DomainValidationError:
        raise
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise DomainValidationError("Key-size interpolation failed") from exc
    if not isinstance(curve, EvaluatedCurve) or (
        curve.particle_size_um != grid or curve.basis != psd.basis
    ):
        raise DomainValidationError("Interpolator returned an incompatible key-size curve")
    return curve
