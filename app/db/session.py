"""Motor de base de datos, fábrica de sesiones y dependencia de FastAPI.

El engine se construye una única vez por proceso a partir de ``DATABASE_URL``.
El pool de conexiones se configura para PostgreSQL y se omite en SQLite, que
no admite los mismos parámetros de pool.
"""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _engine_kwargs(database_url: str) -> dict[str, Any]:
    """Devuelve los argumentos de pool según el motor de la URL.

    Args:
        database_url: URL de conexión a la base de datos.

    Returns:
        Argumentos para ``create_engine``.
    """
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if not database_url.startswith("sqlite"):
        kwargs.update({"pool_size": 5, "max_overflow": 10, "pool_recycle": 1800})
    return kwargs


engine: Engine = create_engine(
    settings.database_url,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Entrega una sesión de base de datos por petición y la cierra al final.

    Yields:
        Sesión de SQLAlchemy conectada al motor configurado.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
