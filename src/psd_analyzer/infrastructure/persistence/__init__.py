"""SQLite lifecycle and repository factory; imported only at composition boundaries."""

from pathlib import Path
from typing import TYPE_CHECKING

from .database import DEFAULT_DATABASE_PATH, init_db

if TYPE_CHECKING:
    from ..repositories.analysis import SqlAlchemyAnalysisRepository


def create_repository(path: str | Path = DEFAULT_DATABASE_PATH) -> "SqlAlchemyAnalysisRepository":
    """Create a repository without maintaining a hidden process-global instance."""
    from ..repositories.analysis import create_repository as factory

    return factory(path)


__all__ = ["DEFAULT_DATABASE_PATH", "create_repository", "init_db"]
