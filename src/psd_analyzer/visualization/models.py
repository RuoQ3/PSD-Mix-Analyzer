"""Small immutable presentation inputs; mathematical results stay in domain models."""

from dataclasses import dataclass
from typing import Literal

from psd_analyzer.domain.models.analysis_result import EvaluatedCurve, FitResult, KeyPassing
from psd_analyzer.domain.models.psd import PSD

SeriesRole = Literal["material", "mixed", "target", "baseline", "current"]


@dataclass(frozen=True)
class PSDSeries:
    """A named existing PSD; absent optional curves are omitted by the builder."""

    name: str
    psd: PSD | EvaluatedCurve | None
    role: SeriesRole = "material"


@dataclass(frozen=True)
class KeySizeSeries:
    """Named precomputed key-size observations, including unsupported coverage."""

    name: str
    values: tuple[KeyPassing, ...]


@dataclass(frozen=True)
class QSeries:
    """A named fit result whose status must remain visible alongside q."""

    name: str
    fit: FitResult
