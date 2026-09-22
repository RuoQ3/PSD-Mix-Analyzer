"""Application failures retain domain exceptions as separate, identifiable errors."""


class AnalysisError(ValueError):
    """Invalid application request."""


class MissingMaterialPSD(AnalysisError):
    """A positive recipe line has no selected batch/PSD measurement."""


class InvalidAnalysisConfiguration(AnalysisError):
    """Injected strategies do not match the requested numerical convention."""
