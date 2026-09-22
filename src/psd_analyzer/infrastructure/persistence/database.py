"""One explicit SQLite initialization boundary; sessions never escape Infrastructure."""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from ...application.dto.history import RepositoryError
from .schema import metadata

DEFAULT_DATABASE_PATH = Path("data/psd_analyzer.db")


def init_db(path: str | Path = DEFAULT_DATABASE_PATH) -> Engine:
    """Initialize a file database (or isolated :memory:) and enforce foreign keys."""
    try:
        if str(path) != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            url = "sqlite:///" + str(Path(path).expanduser().resolve())
        else:
            url = "sqlite:///:memory:"
        engine = (
            create_engine(url, poolclass=NullPool)
            if str(path) != ":memory:"
            else create_engine(url)
        )

        @event.listens_for(engine, "connect")
        def configure(connection: Any, record: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        metadata.create_all(engine)
        return engine
    except (SQLAlchemyError, OSError) as exc:
        raise RepositoryError("Unable to initialize the analysis database") from exc
