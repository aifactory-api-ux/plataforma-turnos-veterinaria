"""Fixtures compartidas por la suite de tests de la API.

La suite corre contra un motor SQLite en un archivo temporal por defecto, de
modo que pueda ejecutarse sin levantar PostgreSQL. Si se define
``TEST_DATABASE_URL`` o ``DATABASE_URL`` (por ejemplo, dentro del servicio
``tests`` del ``docker-compose.yml``), se usa esa base de datos en su lugar y
la misma suite se ejecuta contra PostgreSQL.
"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import session as db_session
from app.db.base import Base
from app.db.session import get_db
from app.main import app

DEFAULT_PASSWORD = "secret123"


def _test_database_url() -> tuple[str, tempfile.TemporaryDirectory | None]:
    """Resuelve la URL de la base de datos de la suite.

    Returns:
        La URL a usar y el directorio temporal que hay que limpiar, si lo hubo.
    """
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url:
        return url, None
    tmp_dir = tempfile.TemporaryDirectory()
    return f"sqlite:///{Path(tmp_dir.name) / 'vetclinic_test.db'}", tmp_dir


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """Motor de base de datos aislado en el que corre la suite."""
    url, tmp_dir = _test_database_url()
    test_engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    try:
        yield test_engine
    finally:
        test_engine.dispose()
        if tmp_dir is not None:
            tmp_dir.cleanup()


@pytest.fixture
def db(engine: Engine) -> Generator[Session, None, None]:
    """Sesión de base de datos que usa el test en curso."""
    factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(
    engine: Engine,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Cliente HTTP con la dependencia de base de datos sustituida por la de test."""
    monkeypatch.setattr(db_session, "engine", engine)

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register_account(
    client: TestClient,
    *,
    email: str = "ana@example.com",
    password: str = DEFAULT_PASSWORD,
    role: str = "client",
) -> dict[str, Any]:
    """Registra una cuenta y devuelve el cuerpo de la respuesta.

    Args:
        client: Cliente HTTP de la API.
        email: Correo de la cuenta nueva.
        password: Contraseña de la cuenta nueva.
        role: Rol de la cuenta (``client`` o ``vet``).

    Returns:
        Cuerpo JSON con ``id``, ``email`` y ``role`` de la cuenta creada.
    """
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(
    client: TestClient,
    *,
    email: str = "ana@example.com",
    password: str = DEFAULT_PASSWORD,
) -> str:
    """Autentica una cuenta y devuelve el token de acceso.

    Args:
        client: Cliente HTTP de la API.
        email: Correo de la cuenta.
        password: Contraseña de la cuenta.

    Returns:
        Token JWT de acceso.
    """
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(
    client: TestClient,
    *,
    email: str = "ana@example.com",
    password: str = DEFAULT_PASSWORD,
) -> dict[str, str]:
    """Devuelve la cabecera ``Authorization`` con un token válido.

    Args:
        client: Cliente HTTP de la API.
        email: Correo de la cuenta.
        password: Contraseña de la cuenta.

    Returns:
        Cabeceras HTTP con el token bearer de la cuenta.
    """
    return {"Authorization": f"Bearer {login(client, email=email, password=password)}"}


@pytest.fixture
def register_user(client: TestClient) -> Any:
    """Fixture que registra cuentas contra la API de pruebas."""

    def _register(**kwargs: Any) -> dict[str, Any]:
        return register_account(client, **kwargs)

    return _register


@pytest.fixture
def bearer_headers(client: TestClient) -> Any:
    """Fixture que entrega la cabecera ``Authorization`` con un token válido."""

    def _headers(**kwargs: Any) -> dict[str, str]:
        return auth_headers(client, **kwargs)

    return _headers
