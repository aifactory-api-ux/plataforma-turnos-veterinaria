"""Pruebas del registro y la consulta de mascotas.

La suite comprueba que ``POST /pets`` solo lo pueden usar los clientes, que
valida la especie y la fecha de nacimiento, y que ``GET /pets`` devuelve
únicamente las mascotas de la cuenta autenticada.
"""

from collections.abc import Generator
from datetime import date, datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.dependencies import CREDENTIALS_ERROR
from app.db.models import Appointment, Pet, User

# Contraseña válida para las cuentas de la suite.
PASSWORD = "secret123"

# Encabezado con un token que no es un JWT válido.
INVALID_TOKEN_HEADERS = {"Authorization": "Bearer not-a-valid-token"}

# Datos de una mascota válida.
PET_PAYLOAD = {"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"}


def current_date() -> date:
    """Devuelve la fecha actual en UTC, la zona horaria de la plataforma.

    Returns:
        El día de hoy en UTC.
    """
    return datetime.now(timezone.utc).date()


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


def count_pets(db: Session) -> int:
    """Cuenta las mascotas guardadas en la base de datos.

    Args:
        db: Sesión de base de datos de la suite.

    Returns:
        Número de filas de la tabla ``pets``.
    """
    return len(db.execute(select(Pet)).scalars().all())


def test_post_pets_returns_201_with_the_exact_body(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """``POST /pets`` crea la mascota y devuelve solo los campos del contrato."""
    account = register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json=PET_PAYLOAD,
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "species", "birth_date", "owner_id"}
    assert isinstance(body["id"], int)
    assert body["name"] == "Firulais"
    assert body["species"] == "dog"
    assert body["birth_date"] == "2020-05-04"
    assert body["owner_id"] == account["id"]


def test_post_pets_stores_the_pet_with_the_caller_as_owner(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """La mascota queda guardada con el identificador del cliente autenticado."""
    account = register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json=PET_PAYLOAD,
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 201
    stored = db.execute(select(Pet)).scalars().one()
    assert stored.id == response.json()["id"]
    assert stored.name == "Firulais"
    assert stored.species == "dog"
    assert stored.birth_date == date(2020, 5, 4)
    assert stored.owner_id == account["id"]


def test_post_pets_accepts_the_species_other(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """La especie ``other`` es válida y se devuelve en la respuesta."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json={"name": "Rana", "species": "other", "birth_date": "2021-01-15"},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Rana"
    assert body["species"] == "other"
    assert body["birth_date"] == "2021-01-15"


def test_post_pets_echoes_the_submitted_values(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """La respuesta devuelve los mismos valores que se enviaron."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json={"name": "Mishi", "species": "cat", "birth_date": "2019-11-02"},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mishi"
    assert body["species"] == "cat"
    assert body["birth_date"] == "2019-11-02"


def test_post_pets_with_an_unsupported_species_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Una especie distinta de ``dog``, ``cat`` u ``other`` se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json={"name": "Firulais", "species": "hamster", "birth_date": "2020-05-04"},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 422
    assert count_pets(db) == 0


def test_post_pets_without_species_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Sin especie en el cuerpo la respuesta es ``422``."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json={"name": "Firulais", "birth_date": "2020-05-04"},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 422
    assert count_pets(db) == 0


def test_post_pets_without_a_name_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Sin nombre en el cuerpo la respuesta es ``422``."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json={"species": "dog", "birth_date": "2020-05-04"},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 422
    assert count_pets(db) == 0


def test_post_pets_with_a_future_birth_date_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Una fecha de nacimiento posterior a hoy se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/pets",
        json={"name": "Firulais", "species": "dog", "birth_date": "2999-01-01"},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 422
    assert count_pets(db) == 0


def test_post_pets_with_today_birth_date_returns_201(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """La fecha de nacimiento del día actual es válida y se guarda."""
    register_user(email="ana@example.com", role="client")
    today = current_date().isoformat()

    response = client.post(
        "/pets",
        json={"name": "Firulais", "species": "dog", "birth_date": today},
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 201
    assert response.json()["birth_date"] == today
    assert count_pets(db) == 1


def test_post_pets_by_a_vet_returns_403(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un veterinario no puede registrar mascotas."""
    register_user(email="dr@example.com", role="vet")

    response = client.post(
        "/pets",
        json=PET_PAYLOAD,
        headers=bearer_headers(email="dr@example.com"),
    )

    assert response.status_code == 403
    assert count_pets(db) == 0


def test_get_pets_returns_only_the_pets_of_the_caller(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """``GET /pets`` devuelve las mascotas de la cuenta autenticada."""
    account = register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    client.post(
        "/pets",
        json={"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"},
        headers=headers,
    )
    client.post(
        "/pets",
        json={"name": "Rana", "species": "other", "birth_date": "2021-01-15"},
        headers=headers,
    )

    response = client.get("/pets", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert sorted(pet["name"] for pet in body) == ["Firulais", "Rana"]
    for pet in body:
        assert set(pet) == {"id", "name", "species", "birth_date", "owner_id"}
        assert pet["owner_id"] == account["id"]
    assert sorted(pet["birth_date"] for pet in body) == ["2020-05-04", "2021-01-15"]


def test_get_pets_does_not_show_the_pets_of_another_client(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Las mascotas de otro cliente no aparecen en el listado."""
    register_user(email="ana@example.com", role="client")
    register_user(email="bruno@example.com", role="client")
    created = client.post(
        "/pets",
        json=PET_PAYLOAD,
        headers=bearer_headers(email="ana@example.com"),
    )

    response = client.get("/pets", headers=bearer_headers(email="bruno@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert body == []
    assert all(pet["name"] != "Firulais" for pet in body)
    assert all(pet["id"] != created.json()["id"] for pet in body)


def test_get_pets_by_a_vet_returns_an_empty_array(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un veterinario no tiene mascotas y su listado llega vacío."""
    register_user(email="dr@example.com", role="vet")
    register_user(email="ana@example.com", role="client")
    client.post(
        "/pets",
        json=PET_PAYLOAD,
        headers=bearer_headers(email="ana@example.com"),
    )

    response = client.get("/pets", headers=bearer_headers(email="dr@example.com"))

    assert response.status_code == 200
    assert response.json() == []


def test_post_pets_without_a_token_returns_401(
    client: TestClient,
    db: Session,
) -> None:
    """Sin cabecera ``Authorization`` el alta de mascotas responde ``401``."""
    response = client.post("/pets", json=PET_PAYLOAD)

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}
    assert count_pets(db) == 0


def test_get_pets_without_a_token_returns_401(client: TestClient) -> None:
    """Sin cabecera ``Authorization`` el listado de mascotas responde ``401``."""
    response = client.get("/pets")

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}


def test_post_pets_with_an_invalid_token_returns_401(
    client: TestClient,
    db: Session,
) -> None:
    """Con un token inválido el alta de mascotas responde ``401``."""
    response = client.post("/pets", json=PET_PAYLOAD, headers=INVALID_TOKEN_HEADERS)

    assert response.status_code == 401
    assert count_pets(db) == 0


def test_get_pets_with_an_invalid_token_returns_401(client: TestClient) -> None:
    """Con un token inválido el listado de mascotas responde ``401``."""
    response = client.get("/pets", headers=INVALID_TOKEN_HEADERS)

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}
