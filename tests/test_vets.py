"""Pruebas del directorio de veterinarios.

La suite comprueba que ``GET /vets`` devuelve únicamente las cuentas con rol
``vet``, que cada elemento expone solo ``id`` y ``email`` y que la ruta exige
un token bearer válido.
"""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.dependencies import CREDENTIALS_ERROR
from app.db.models import Appointment, Pet, User

# Contraseña válida para las cuentas de la suite.
PASSWORD = "secret123"

# Encabezado con un token que no es un JWT válido.
INVALID_TOKEN_HEADERS = {"Authorization": "Bearer not-a-valid-token"}

# Encabezado con un esquema que no es el de un token bearer.
MALFORMED_HEADERS = {"Authorization": "Basic dXNlcjpwYXNz"}


def clear_database(db: Session) -> None:
    """Borra las filas de las tres tablas de la suite.

    Args:
        db: Sesión de base de datos de la suite.
    """
    db.execute(delete(Appointment))
    db.execute(delete(Pet))
    db.execute(delete(User))
    db.commit()


@pytest.fixture(autouse=True)
def clean_database(db: Session) -> Generator[None, None, None]:
    """Deja la base de datos vacía antes y después de cada test.

    Args:
        db: Sesión de base de datos de la suite.

    Yields:
        Control devuelto al test.
    """
    clear_database(db)
    yield
    clear_database(db)


def test_get_vets_lists_every_vet(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """``GET /vets`` devuelve una entrada por cada cuenta con rol ``vet``."""
    first_vet = register_user(email="dr-uno@example.com", role="vet")
    second_vet = register_user(email="dr-dos@example.com", role="vet")
    register_user(email="ana@example.com", role="client")

    response = client.get("/vets", headers=bearer_headers(email="ana@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    # La comparación es independiente del orden en que llegan los veterinarios.
    assert sorted(vet["email"] for vet in body) == sorted(
        ["dr-uno@example.com", "dr-dos@example.com"]
    )
    assert sorted(vet["id"] for vet in body) == sorted([first_vet["id"], second_vet["id"]])
    assert all(isinstance(vet["id"], int) for vet in body)


def test_get_vets_excludes_client_accounts(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El directorio no incluye las cuentas con rol ``client``."""
    register_user(email="ana@example.com", role="client")
    register_user(email="dr@example.com", role="vet")

    response = client.get("/vets", headers=bearer_headers(email="ana@example.com"))

    assert response.status_code == 200
    emails = [vet["email"] for vet in response.json()]
    assert "dr@example.com" in emails
    assert "ana@example.com" not in emails


def test_get_vets_elements_expose_only_id_and_email(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Ningún elemento del directorio expone la contraseña ni su hash."""
    register_user(email="dr@example.com", role="vet")
    register_user(email="ana@example.com", role="client")

    response = client.get("/vets", headers=bearer_headers(email="ana@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert body
    for vet in body:
        assert set(vet) == {"id", "email"}
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert "$2b$" not in response.text


def test_get_vets_returns_an_empty_array_when_no_vet_exists(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Sin cuentas con rol ``vet`` el directorio es un arreglo vacío."""
    register_user(email="ana@example.com", role="client")

    response = client.get("/vets", headers=bearer_headers(email="ana@example.com"))

    assert response.status_code == 200
    assert response.json() == []


def test_get_vets_allows_a_vet_to_consult_the_directory(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un veterinario autenticado también puede consultar el directorio."""
    register_user(email="dr@example.com", role="vet")
    register_user(email="dr-dos@example.com", role="vet")

    response = client.get("/vets", headers=bearer_headers(email="dr@example.com"))

    assert response.status_code == 200
    assert sorted(vet["email"] for vet in response.json()) == sorted(
        ["dr@example.com", "dr-dos@example.com"]
    )


def test_get_vets_without_a_token_returns_401(client: TestClient) -> None:
    """Sin cabecera ``Authorization`` el directorio responde 401."""
    response = client.get("/vets")

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}


def test_get_vets_with_an_invalid_token_returns_401(client: TestClient) -> None:
    """Con un token inválido el directorio responde 401."""
    response = client.get("/vets", headers=INVALID_TOKEN_HEADERS)

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}


def test_get_vets_with_a_malformed_header_returns_401(client: TestClient) -> None:
    """Con una cabecera que no es de tipo bearer el directorio responde 401."""
    response = client.get("/vets", headers=MALFORMED_HEADERS)

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}
