"""Pruebas del endpoint público de estado del servicio."""

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    """``GET /health`` responde con el código 200."""
    response = client.get("/health")

    assert response.status_code == 200


def test_health_returns_exact_body(client: TestClient) -> None:
    """``GET /health`` responde exactamente con el cuerpo ``{"status": "ok"}``."""
    response = client.get("/health")

    assert response.json() == {"status": "ok"}


def test_health_body_has_a_single_field(client: TestClient) -> None:
    """El cuerpo de ``GET /health`` no contiene ningún campo adicional."""
    response = client.get("/health")

    assert set(response.json()) == {"status"}


def test_health_does_not_require_a_token(client: TestClient) -> None:
    """``GET /health`` responde 200 aunque no se envíe cabecera ``Authorization``."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ignores_an_invalid_token(client: TestClient) -> None:
    """``GET /health`` responde 200 aunque el token enviado sea inválido."""
    response = client.get("/health", headers={"Authorization": "Bearer not-a-valid-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
