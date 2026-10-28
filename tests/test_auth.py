"""Pruebas del registro, el inicio de sesión y la protección por token bearer."""

import time
import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_client, require_vet
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Appointment, Pet, User

# Contraseña válida para las cuentas de la suite.
PASSWORD = "secret123"

# Rutas protegidas por el token bearer, con el método y el cuerpo que usan.
PROTECTED_REQUESTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/vets", None),
    (
        "POST",
        "/pets",
        {"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"},
    ),
    ("GET", "/pets", None),
    (
        "POST",
        "/appointments",
        {"pet_id": 1, "vet_id": 1, "start_at": "2030-03-11T09:00:00Z"},
    ),
    ("GET", "/appointments", None),
    ("POST", "/appointments/1/cancel", None),
]


def unique_email(prefix: str = "user") -> str:
    """Devuelve un correo distinto en cada invocación.

    Args:
        prefix: Prefijo del correo generado.

    Returns:
        Un correo válido y único para la base de datos de la suite.
    """
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def login_token(client: TestClient, email: str, password: str = PASSWORD) -> str:
    """Inicia sesión y devuelve el token de acceso.

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


@pytest.fixture(autouse=True)
def clean_database(db: Session) -> Generator[None, None, None]:
    """Borra los datos creados por cada test para no arrastrar estado.

    Args:
        db: Sesión de base de datos de la suite.

    Yields:
        Control devuelto al test.
    """
    yield
    db.execute(delete(Appointment))
    db.execute(delete(Pet))
    db.execute(delete(User))
    db.commit()


def test_hash_password_hides_the_password() -> None:
    """El hash bcrypt no contiene la contraseña y sí la verifica."""
    hashed = hash_password(PASSWORD)

    assert hashed != PASSWORD
    assert PASSWORD not in hashed
    assert verify_password(PASSWORD, hashed) is True
    assert verify_password("otra-contrasena", hashed) is False


def test_register_client_returns_201_with_the_account_data(client: TestClient) -> None:
    """``POST /auth/register`` crea una cuenta de cliente."""
    email = unique_email()

    response = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "client"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "client"
    assert isinstance(body["id"], int)


def test_register_vet_returns_201_with_the_account_data(client: TestClient) -> None:
    """``POST /auth/register`` crea una cuenta de veterinario."""
    email = unique_email()

    response = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "vet"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "vet"
    assert isinstance(body["id"], int)


def test_register_response_never_exposes_the_password(client: TestClient) -> None:
    """El cuerpo del ``201`` solo contiene ``id``, ``email`` y ``role``."""
    response = client.post(
        "/auth/register",
        json={"email": unique_email(), "password": PASSWORD, "role": "client"},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "role"}
    assert "password" not in body
    assert "password_hash" not in body


def test_register_with_a_duplicate_email_returns_409(
    client: TestClient,
    register_user: Any,
) -> None:
    """Un correo ya registrado se rechaza con ``409``."""
    email = unique_email()
    register_user(email=email)

    response = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "client"},
    )

    assert response.status_code == 409


def test_register_with_a_duplicate_email_in_another_case_returns_409(
    client: TestClient,
    register_user: Any,
) -> None:
    """Un correo duplicado que solo difiere en mayúsculas se rechaza con ``409``."""
    email = unique_email()
    register_user(email=email)

    response = client.post(
        "/auth/register",
        json={"email": email.upper(), "password": PASSWORD, "role": "client"},
    )

    assert response.status_code == 409


def test_register_with_a_short_password_returns_422(client: TestClient) -> None:
    """Una contraseña de menos de ocho caracteres se rechaza con ``422``."""
    email = unique_email()

    response = client.post(
        "/auth/register",
        json={"email": email, "password": "short7c", "role": "client"},
    )

    assert response.status_code == 422
    retry = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "client"},
    )
    assert retry.status_code == 201


def test_register_with_an_invalid_role_returns_422(client: TestClient) -> None:
    """Un rol distinto de ``client`` o ``vet`` se rechaza con ``422``."""
    email = unique_email()

    response = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "admin"},
    )

    assert response.status_code == 422
    retry = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "client"},
    )
    assert retry.status_code == 201


def test_register_with_a_malformed_email_returns_422(client: TestClient) -> None:
    """Un correo con formato inválido se rechaza con ``422``."""
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": PASSWORD, "role": "client"},
    )

    assert response.status_code == 422


def test_register_with_a_password_longer_than_bcrypt_limit_returns_422(
    client: TestClient,
) -> None:
    """Una contraseña que supera el límite de bcrypt se rechaza con ``422``."""
    response = client.post(
        "/auth/register",
        json={"email": unique_email(), "password": "a" * 73, "role": "client"},
    )

    assert response.status_code == 422


def test_login_returns_200_with_a_bearer_token(
    client: TestClient,
    register_user: Any,
) -> None:
    """``POST /auth/login`` devuelve el token y su tipo."""
    email = unique_email()
    register_user(email=email)

    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["access_token"]


def test_login_token_identifies_the_account_and_its_role(
    client: TestClient,
    register_user: Any,
) -> None:
    """El token lleva el identificador y el rol de la cuenta."""
    email = unique_email()
    account = register_user(email=email, role="vet")

    token = login_token(client, email)
    payload = jwt.decode(
        token,
        get_settings().jwt_secret_key,
        algorithms=["HS256"],
    )

    assert payload["sub"] == str(account["id"])
    assert payload["role"] == "vet"
    assert payload["exp"] > time.time()


def test_login_accepts_the_email_in_another_case(
    client: TestClient,
    register_user: Any,
) -> None:
    """El login acepta el correo escrito con otras mayúsculas."""
    email = unique_email()
    register_user(email=email)

    response = client.post(
        "/auth/login",
        json={"email": email.upper(), "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_login_with_a_wrong_password_returns_401(
    client: TestClient,
    register_user: Any,
) -> None:
    """Una contraseña incorrecta se rechaza con ``401``."""
    email = unique_email()
    register_user(email=email)

    response = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_with_an_unknown_email_returns_401(client: TestClient) -> None:
    """Un correo no registrado se rechaza con ``401``."""
    response = client.post(
        "/auth/login",
        json={"email": unique_email(), "password": PASSWORD},
    )

    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_failures_return_the_same_body(
    client: TestClient,
    register_user: Any,
) -> None:
    """El login no revela si falló la contraseña o el correo."""
    email = unique_email()
    register_user(email=email)

    wrong_password = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/auth/login",
        json={"email": unique_email(), "password": PASSWORD},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_auth_endpoints_do_not_require_a_token(client: TestClient) -> None:
    """El registro y el login son accesibles sin credenciales."""
    email = unique_email()

    registered = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "role": "client"},
    )
    logged_in = client.post("/auth/login", json={"email": email, "password": PASSWORD})

    assert registered.status_code == 201
    assert logged_in.status_code == 200


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_endpoints_answer_401_without_a_token(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Sin cabecera ``Authorization`` las rutas protegidas responden ``401``."""
    response = client.request(method, path, json=body)

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_endpoints_answer_401_with_a_malformed_header(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Una cabecera ``Authorization`` mal formada responde ``401``."""
    malformed_headers = [
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer   ",
        "token abc",
    ]

    for header in malformed_headers:
        response = client.request(
            method,
            path,
            json=body,
            headers={"Authorization": header},
        )
        assert response.status_code == 401, header


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_endpoints_answer_401_with_an_invalid_token(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Un token que no es un JWT válido responde ``401``."""
    response = client.request(
        method,
        path,
        json=body,
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_endpoints_answer_401_with_a_token_signed_with_an_unknown_key(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Un JWT firmado con otra clave responde ``401``."""
    token = jwt.encode(
        {"sub": "1", "role": "client", "exp": int(time.time()) + 600},
        "clave-inexistente-de-la-prueba-0123456789",
        algorithm="HS256",
    )

    response = client.request(
        method,
        path,
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_endpoints_answer_401_with_an_expired_token(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Un token caducado responde ``401``."""
    token = create_access_token(
        subject=1,
        role="client",
        expires_delta=timedelta(minutes=-5),
    )

    response = client.request(
        method,
        path,
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_get_current_user_resolves_the_account_of_the_token(
    client: TestClient,
    db: Session,
    register_user: Any,
) -> None:
    """``get_current_user`` devuelve la cuenta a la que pertenece el token."""
    email = unique_email()
    account = register_user(email=email, role="vet")
    token = login_token(client, email)

    user = get_current_user(authorization=f"Bearer {token}", db=db)

    assert user.id == account["id"]
    assert user.email == email
    assert user.role == "vet"


def test_get_current_user_answers_401_without_a_token(db: Session) -> None:
    """``get_current_user`` responde ``401`` si no hay cabecera ``Authorization``."""
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(authorization=None, db=db)

    assert excinfo.value.status_code == 401


def test_get_current_user_answers_401_with_an_invalid_token(db: Session) -> None:
    """``get_current_user`` responde ``401`` si el token no es válido."""
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(authorization="Bearer not-a-valid-token", db=db)

    assert excinfo.value.status_code == 401


def test_require_client_allows_a_client(
    client: TestClient,
    db: Session,
    register_user: Any,
) -> None:
    """``require_client`` deja pasar a una cuenta de cliente."""
    email = unique_email()
    register_user(email=email, role="client")
    token = login_token(client, email)
    user = get_current_user(authorization=f"Bearer {token}", db=db)

    assert require_client(user) is user


def test_require_client_answers_403_for_a_vet(
    client: TestClient,
    db: Session,
    register_user: Any,
) -> None:
    """``require_client`` responde ``403`` ante una cuenta de veterinario."""
    email = unique_email()
    register_user(email=email, role="vet")
    token = login_token(client, email)
    user = get_current_user(authorization=f"Bearer {token}", db=db)

    with pytest.raises(HTTPException) as excinfo:
        require_client(user)

    assert excinfo.value.status_code == 403


def test_require_vet_allows_a_vet(
    client: TestClient,
    db: Session,
    register_user: Any,
) -> None:
    """``require_vet`` deja pasar a una cuenta de veterinario."""
    email = unique_email()
    register_user(email=email, role="vet")
    token = login_token(client, email)
    user = get_current_user(authorization=f"Bearer {token}", db=db)

    assert require_vet(user) is user


def test_require_vet_answers_403_for_a_client(
    client: TestClient,
    db: Session,
    register_user: Any,
) -> None:
    """``require_vet`` responde ``403`` ante una cuenta de cliente."""
    email = unique_email()
    register_user(email=email, role="client")
    token = login_token(client, email)
    user = get_current_user(authorization=f"Bearer {token}", db=db)

    with pytest.raises(HTTPException) as excinfo:
        require_vet(user)

    assert excinfo.value.status_code == 403
