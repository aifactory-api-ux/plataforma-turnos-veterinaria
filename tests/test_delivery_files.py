"""Pruebas de los artefactos de entrega del repositorio.

Comprueban que la raíz del repositorio incluye el ``Dockerfile`` y el
``docker-compose.yml`` que usa el equipo, que el compose ofrece PostgreSQL, la
API y un servicio que ejecuta la suite de pytest, que el script de verificación
de entrega es ejecutable y que el ``README.md`` documenta todos los endpoints
de la API con sus pasos de arranque y sus variables de entorno.

El módulo usa PyYAML para leer el archivo de compose; la librería llega como
dependencia de ``uvicorn[standard]``, que instala el runtime de la API.
"""

import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

# Raíz del repositorio: el directorio padre del que contiene los tests.
REPO_ROOT = Path(__file__).resolve().parents[1]

# Artefactos de entrega que deben existir en la raíz del repositorio.
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_stack.sh"
README = REPO_ROOT / "README.md"

# Servicios que debe declarar el archivo de compose.
EXPECTED_SERVICES = ("db", "api", "tests")

# Endpoints que el README debe documentar con su método HTTP.
DOCUMENTED_ENDPOINTS = (
    "GET /health",
    "POST /auth/register",
    "POST /auth/login",
    "GET /vets",
    "POST /pets",
    "GET /pets",
    "POST /appointments",
    "GET /appointments",
    "POST /appointments/{id}/cancel",
)

# Secciones obligatorias del README.
REQUIRED_SECTIONS = (
    "## Arranque local",
    "## Arranque con Docker",
    "## Ejecutar los tests",
    "## Variables de entorno",
)

# Imagen base de las dos etapas de construcción de la imagen.
BASE_IMAGE = "python:3.12-slim"

# Piezas del comando de arranque de la API dentro del contenedor.
API_COMMAND_TOKENS = ("uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000")

# Patrón de la instrucción USER del Dockerfile: cualquier usuario que no sea root.
USER_DIRECTIVE = re.compile(r"^USER\s+(?!root\b)\S+", re.MULTILINE)


def read_text(path: Path) -> str:
    """Lee un archivo de texto del repositorio.

    Args:
        path: Ruta del archivo a leer.

    Returns:
        El contenido del archivo como texto.
    """
    return path.read_text(encoding="utf-8")


def load_compose() -> dict[str, Any]:
    """Carga el archivo de compose del repositorio.

    Returns:
        El contenido del archivo de compose ya interpretado.
    """
    return yaml.safe_load(read_text(COMPOSE_FILE))


def compose_service(name: str) -> dict[str, Any]:
    """Devuelve la definición de un servicio del archivo de compose.

    Args:
        name: Nombre del servicio.

    Returns:
        La definición del servicio tal y como aparece en el compose.
    """
    return load_compose()["services"][name]


def healthcheck_command(service: dict[str, Any]) -> str:
    """Devuelve el comando de la comprobación de salud de un servicio.

    Args:
        service: Definición del servicio.

    Returns:
        El comando de la comprobación de salud unido en una sola cadena.
    """
    test = service.get("healthcheck", {}).get("test", [])
    if isinstance(test, list):
        return " ".join(str(part) for part in test)
    return str(test)


def test_delivery_files_exist_at_the_repository_root() -> None:
    """Los cuatro artefactos de entrega existen en la raíz del repositorio."""
    assert DOCKERFILE.is_file(), f"Falta {DOCKERFILE}"
    assert COMPOSE_FILE.is_file(), f"Falta {COMPOSE_FILE}"
    assert VERIFY_SCRIPT.is_file(), f"Falta {VERIFY_SCRIPT}"
    assert README.is_file(), f"Falta {README}"


def test_dockerfile_is_a_multi_stage_build_over_the_python_base_image() -> None:
    """El Dockerfile construye en dos etapas sobre la imagen base de Python."""
    content = read_text(DOCKERFILE)

    assert content.count(f"FROM {BASE_IMAGE}") >= 2, (
        "El Dockerfile debe declarar la etapa de construcción y la final "
        f"sobre {BASE_IMAGE}."
    )
    assert "AS builder" in content, "El Dockerfile debe declarar la etapa builder."
    assert "requirements.txt" in content, "El Dockerfile debe instalar requirements.txt."
    assert (
        "requirements-dev.txt" in content
    ), "El Dockerfile debe instalar requirements-dev.txt para poder correr los tests."


def test_dockerfile_runs_the_api_without_root_privileges() -> None:
    """El Dockerfile ejecuta la API con un usuario sin privilegios."""
    content = read_text(DOCKERFILE)

    assert USER_DIRECTIVE.search(content) is not None, (
        "El Dockerfile debe ejecutar el proceso con un usuario que no sea root."
    )
    assert "EXPOSE 8000" in content, "El Dockerfile debe exponer el puerto 8000."


def test_dockerfile_starts_the_api_and_declares_a_healthcheck() -> None:
    """El Dockerfile arranca uvicorn y comprueba la salud contra /health."""
    content = read_text(DOCKERFILE)

    assert "HEALTHCHECK" in content, "El Dockerfile debe declarar un HEALTHCHECK."
    assert "/health" in content, "El HEALTHCHECK debe consultar el endpoint /health."

    cmd_lines = [line for line in content.splitlines() if line.startswith("CMD ")]
    assert cmd_lines, "El Dockerfile debe declarar el comando de arranque."
    for token in API_COMMAND_TOKENS:
        assert token in cmd_lines[-1], (
            f"El comando de arranque del Dockerfile debe incluir «{token}»."
        )


def test_compose_declares_the_expected_services() -> None:
    """El archivo de compose declara los servicios db, api y tests."""
    services = load_compose()["services"]

    for name in EXPECTED_SERVICES:
        assert name in services, f"El compose debe declarar el servicio «{name}»."


def test_compose_db_service_uses_postgres_with_a_healthcheck_and_a_volume() -> None:
    """El servicio db usa PostgreSQL 16, comprueba su salud y guarda los datos."""
    compose = load_compose()
    db = compose["services"]["db"]

    assert db["image"].startswith("postgres:"), "El servicio db debe usar PostgreSQL."
    assert "pg_isready" in healthcheck_command(db), (
        "El servicio db debe comprobar su disponibilidad con pg_isready."
    )
    assert "pgdata" in compose["volumes"], "El compose debe declarar el volumen pgdata."
    assert any(
        str(volume).startswith("pgdata:") for volume in db["volumes"]
    ), "El servicio db debe montar el volumen nombrado pgdata."


def test_compose_api_service_is_built_from_the_root_dockerfile() -> None:
    """El servicio api se construye con el Dockerfile de la raíz."""
    api = compose_service("api")

    assert api["build"]["context"] == ".", "El servicio api debe construirse en la raíz."
    assert api["build"]["dockerfile"] == "Dockerfile", (
        "El servicio api debe construirse con el Dockerfile de la raíz."
    )


def test_compose_api_service_waits_for_a_healthy_database() -> None:
    """El servicio api solo arranca cuando la base de datos está sana."""
    api = compose_service("api")

    assert api["depends_on"]["db"]["condition"] == "service_healthy", (
        "El servicio api debe esperar a que db esté healthy."
    )


def test_compose_api_service_receives_the_configuration_from_the_environment() -> None:
    """El servicio api recibe la configuración desde el entorno."""
    api = compose_service("api")
    environment = api["environment"]

    assert environment["DATABASE_URL"].startswith("${DATABASE_URL"), (
        "El servicio api debe recibir DATABASE_URL del entorno."
    )
    assert environment["JWT_SECRET_KEY"].startswith("${JWT_SECRET_KEY"), (
        "El servicio api debe recibir JWT_SECRET_KEY del entorno."
    )
    assert "ACCESS_TOKEN_EXPIRE_MINUTES" in environment


def test_compose_api_service_publishes_the_port_and_checks_its_health() -> None:
    """El servicio api publica el puerto 8000 y comprueba su salud."""
    api = compose_service("api")

    assert "8000:8000" in api["ports"], "El servicio api debe publicar el puerto 8000."
    assert "/health" in healthcheck_command(api), (
        "El servicio api debe comprobar su salud contra /health."
    )


def test_compose_tests_service_runs_pytest_with_the_same_image() -> None:
    """El servicio tests ejecuta la suite con la misma imagen que la API."""
    compose = load_compose()
    tests = compose["services"]["tests"]

    assert tests["build"] == compose["services"]["api"]["build"], (
        "El servicio tests debe usar la misma imagen que el servicio api."
    )
    assert tests["command"] == ["pytest", "-q"], (
        "El servicio tests debe ejecutar la suite con «pytest -q»."
    )
    assert tests["depends_on"]["db"]["condition"] == "service_healthy", (
        "El servicio tests debe esperar a que db esté healthy."
    )


def test_verify_script_is_executable_and_runs_the_delivery_check() -> None:
    """El script de verificación es ejecutable y contiene los pasos del control."""
    assert os.access(VERIFY_SCRIPT, os.X_OK), (
        "El script de verificación debe tener permiso de ejecución."
    )

    content = read_text(VERIFY_SCRIPT)

    assert "docker compose up --build --wait" in content, (
        "El script debe levantar el stack con «docker compose up --build --wait»."
    )
    assert "curl -fsS" in content and "http://localhost:8000/health" in content, (
        "El script debe comprobar el endpoint /health con curl."
    )
    assert "docker compose run --rm tests" in content, (
        "El script debe ejecutar la suite con «docker compose run --rm tests»."
    )
    assert "docker compose down" in content, (
        "El script debe bajar el stack con «docker compose down»."
    )


def test_readme_documents_every_endpoint_of_the_api() -> None:
    """El README documenta cada endpoint de la API con su método HTTP."""
    content = read_text(README)

    for endpoint in DOCUMENTED_ENDPOINTS:
        assert endpoint in content, f"El README debe documentar «{endpoint}»."


def test_readme_contains_the_startup_test_and_configuration_sections() -> None:
    """El README incluye los apartados de arranque, tests y variables."""
    content = read_text(README)

    for section in REQUIRED_SECTIONS:
        assert section in content, f"El README debe incluir la sección «{section}»."


def test_readme_documents_the_docker_commands_of_the_stack() -> None:
    """El README documenta los comandos de arranque y parada del stack."""
    content = read_text(README)

    for command in (
        "docker compose up --build --wait",
        "docker compose down",
        "docker compose run --rm tests",
        "curl -fsS http://localhost:8000/health",
    ):
        assert command in content, f"El README debe documentar el comando «{command}»."


@pytest.mark.parametrize(
    "artifact",
    (DOCKERFILE, COMPOSE_FILE, VERIFY_SCRIPT, README),
    ids=("dockerfile", "compose", "verify-script", "readme"),
)
def test_delivery_artifacts_are_not_empty(artifact: Path) -> None:
    """Los artefactos de entrega no están vacíos."""
    assert artifact.stat().st_size > 0, f"El archivo {artifact} está vacío."
