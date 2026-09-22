"""Separate raw-node union grids from the existing fixed model evaluation grid."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..exceptions import DomainValidationError
from ..models.analysis_profile import AnalysisProfile
from ..models.psd import PSD


@dataclass(frozen=True)
class ParticleSizeGridBuilder:
    """Sorted exact union of validated source nodes in μm; no smoothing or logspace."""

    def build(self, psds: Sequence[PSD]) -> tuple[float, ...]:
        if not psds or any(not isinstance(psd, PSD) for psd in psds):
            raise DomainValidationError("Grid construction requires at least one validated PSD")
        # Duplicates within a PSD were rejected at construction; duplicates across PSDs are valid.
        nodes = np.concatenate([psd.particle_size_um for psd in psds])
        return tuple(float(value) for value in np.unique(nodes))


def build_grid(profile: AnalysisProfile) -> tuple[float, ...]:
    """Existing fixed model grid. Do not replace this with data-dependent union nodes."""
    values = np.geomspace(profile.d_min_um, profile.d_max_um, profile.grid_points)
    values[0], values[-1] = profile.d_min_um, profile.d_max_um
    return tuple(float(v) for v in values)
