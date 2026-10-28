"""Pruebas de la agenda de turnos.

La suite cubre las reglas de la franja horaria, la reserva de turnos, el
listado según el rol de la cuenta, la cancelación, la protección de las tres
rutas con token bearer y las funciones de servicio que aplican las reglas de
la agenda.
"""

from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.dependencies import CREDENTIALS_ERROR
from app.db.models import Appointment, Pet, User
from app.services import scheduling
from app.services.scheduling import (
    CLOSING_TIME,
    LAST_START_TIME,
    OPENING_TIME,
    SLOT_MINUTES,
    WORKING_WEEKDAYS,
    slot_end,
    validate_start_at,
)

# Contraseña válida para las cuentas de la suite.
PASSWORD = "secret123"

# Encabezado con un token que no es un JWT válido.
INVALID_TOKEN_HEADERS = {"Authorization": "Bearer not-a-valid-token"}

# Datos de una mascota válida.
PET_PAYLOAD = {"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"}

# Días de la semana en los que atiende la clínica.
MONDAY = 0
SATURDAY = 5
SUNDAY = 6

# Desplazamiento usado para comprobar la conversión a UTC.
PLUS_TWO_HOURS = timezone(timedelta(hours=2))


def next_weekday(target: int, *, min_days_ahead: int = 7) -> date:
    """Devuelve la próxima fecha futura que cae en el día de la semana pedido.

    Args:
        target: Día de la semana buscado, de lunes (0) a domingo (6).
        min_days_ahead: Distancia mínima en días respecto del día actual.

    Returns:
        La fecha futura del día de la semana pedido.
    """
    today = datetime.now(timezone.utc).date()
    for offset in range(min_days_ahead, min_days_ahead + 7):
        candidate = today + timedelta(days=offset)
        if candidate.weekday() == target:
            return candidate
    raise AssertionError("No se encontró la fecha buscada.")


def future_slot(hour: int, minute: int, *, weekday: int = MONDAY) -> datetime:
    """Devuelve un instante UTC futuro dentro de la ventana laboral.

    Args:
        hour: Hora del inicio del turno.
        minute: Minuto del inicio del turno.
        weekday: Día de la semana del inicio del turno.

    Returns:
        El instante futuro con zona horaria UTC.
    """
    day = next_weekday(weekday)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def iso_utc(moment: datetime) -> str:
    """Serializa un instante en ISO 8601 UTC con el sufijo ``Z``.

    Args:
        moment: Instante a serializar.

    Returns:
        La marca de tiempo con el formato que devuelve la API.
    """
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


def count_appointments(db: Session) -> int:
    """Cuenta los turnos guardados en la base de datos.

    Args:
        db: Sesión de base de datos de la suite.

    Returns:
        Número de filas de la tabla ``appointments``.
    """
    return len(db.execute(select(Appointment)).scalars().all())


def create_pet(
    client: TestClient,
    headers: dict[str, str],
    name: str = "Firulais",
) -> dict[str, Any]:
    """Registra una mascota con la cuenta autenticada.

    Args:
        client: Cliente HTTP de la API.
        headers: Cabecera ``Authorization`` del cliente.
        name: Nombre de la mascota.

    Returns:
        Cuerpo JSON de la mascota creada.
    """
    response = client.post(
        "/pets",
        json={**PET_PAYLOAD, "name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def book_appointment(
    client: TestClient,
    headers: dict[str, str],
    *,
    pet_id: int,
    vet_id: int,
    start_at: str,
) -> Response:
    """Intenta reservar un turno y devuelve la respuesta de la API.

    Args:
        client: Cliente HTTP de la API.
        headers: Cabecera ``Authorization`` del cliente.
        pet_id: Identificador de la mascota.
        vet_id: Identificador del veterinario.
        start_at: Inicio del turno en ISO 8601.

    Returns:
        La respuesta devuelta por la API.
    """
    return client.post(
        "/appointments",
        json={"pet_id": pet_id, "vet_id": vet_id, "start_at": start_at},
        headers=headers,
    )


def test_post_appointments_returns_201_with_the_exact_body(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """``POST /appointments`` crea el turno y devuelve solo los campos del contrato."""
    register_user(email="dr@example.com", role="vet")
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dra@example.com", role="vet")
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "pet_id", "vet_id", "start_at", "end_at", "status"}
    assert isinstance(body["id"], int)
    assert body["pet_id"] == pet["id"]
    assert body["vet_id"] == vet["id"]
    assert body["start_at"] == iso_utc(slot)
    assert body["end_at"] == iso_utc(slot + timedelta(minutes=SLOT_MINUTES))
    assert body["status"] == "scheduled"


def test_post_appointments_stores_the_times_in_utc(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El turno se guarda con el inicio y el final en UTC, sin zona horaria."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 201
    stored = db.execute(select(Appointment)).scalars().one()
    assert stored.id == response.json()["id"]
    assert stored.start_at == slot.replace(tzinfo=None)
    assert stored.end_at == (slot + timedelta(minutes=SLOT_MINUTES)).replace(tzinfo=None)
    assert stored.status == "scheduled"


def test_post_appointments_by_a_vet_returns_403(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un veterinario no puede reservar turnos."""
    register_user(email="dr@example.com", role="vet")
    register_user(email="ana@example.com", role="client")
    client_headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, client_headers)
    vet = register_user(email="dra@example.com", role="vet")
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        bearer_headers(email="dr@example.com"),
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 403
    assert count_appointments(db) == 0


def test_post_appointments_for_a_pet_of_another_client_returns_403(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un cliente no puede reservar un turno para la mascota de otro."""
    register_user(email="bruno@example.com", role="client")
    register_user(email="ana@example.com", role="client")
    bruno_headers = bearer_headers(email="bruno@example.com")
    pet = create_pet(client, bruno_headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        bearer_headers(email="ana@example.com"),
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 403
    assert count_appointments(db) == 0


def test_post_appointments_with_an_unknown_pet_returns_404(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Una mascota inexistente se responde con ``404``."""
    register_user(email="ana@example.com", role="client")
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        bearer_headers(email="ana@example.com"),
        pet_id=999999,
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 404
    assert count_appointments(db) == 0


def test_post_appointments_with_an_unknown_vet_returns_404(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un veterinario inexistente se responde con ``404``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=999999,
        start_at=iso_utc(slot),
    )

    assert response.status_code == 404
    assert count_appointments(db) == 0


def test_post_appointments_out_of_the_half_hour_grid_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un inicio que no cae en punto ni en y media se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 15)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 422
    assert count_appointments(db) == 0


def test_post_appointments_before_the_opening_time_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un inicio anterior a las 09:00 se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(8, 30)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 422
    assert count_appointments(db) == 0


def test_post_appointments_at_the_closing_time_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un inicio a las 18:00 se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(18, 0)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 422
    assert count_appointments(db) == 0


def test_post_appointments_at_the_last_start_of_the_day_returns_201(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El último inicio del día, a las 17:30, es válido y termina a las 18:00."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(17, 30)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["start_at"] == iso_utc(slot)
    assert body["end_at"] == iso_utc(slot + timedelta(minutes=SLOT_MINUTES))
    assert body["status"] == "scheduled"


def test_post_appointments_on_sunday_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El domingo no atiende la clínica y el turno se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0, weekday=SUNDAY)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 422
    assert count_appointments(db) == 0


def test_post_appointments_on_saturday_returns_201(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El sábado es día de atención y el turno se crea con estado ``scheduled``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0, weekday=SATURDAY)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "scheduled"


def test_post_appointments_in_the_past_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un inicio ya transcurrido se rechaza con ``422``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at="2000-01-03T09:00:00Z",
    )

    assert response.status_code == 422
    assert count_appointments(db) == 0


def test_post_appointments_with_an_offset_is_converted_to_utc(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un inicio con desplazamiento se aplica en su instante UTC equivalente."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=slot.astimezone(PLUS_TWO_HOURS).isoformat(),
    )

    assert response.status_code == 201
    assert response.json()["start_at"] == iso_utc(slot)


def test_post_appointments_with_an_offset_outside_the_window_returns_422(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un inicio con desplazamiento que cae fuera de la ventana se rechaza."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(6, 0)

    response = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=slot.astimezone(PLUS_TWO_HOURS).isoformat(),
    )

    assert response.status_code == 422
    assert count_appointments(db) == 0


def test_post_appointments_with_a_taken_slot_returns_409(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El veterinario no puede tener dos turnos activos en la misma franja."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    first_pet = create_pet(client, headers, "Firulais")
    second_pet = create_pet(client, headers, "Rana")
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)

    first = book_appointment(
        client,
        headers,
        pet_id=first_pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )
    second = book_appointment(
        client,
        headers,
        pet_id=second_pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert count_appointments(db) == 1


def test_post_appointments_with_the_same_slot_for_another_vet_returns_201(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """La misma franja queda libre para otro veterinario."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    first_vet = register_user(email="dr@example.com", role="vet")
    second_vet = register_user(email="dra@example.com", role="vet")
    slot = future_slot(9, 0)

    first = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=first_vet["id"],
        start_at=iso_utc(slot),
    )
    second = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=second_vet["id"],
        start_at=iso_utc(slot),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["vet_id"] == second_vet["id"]


def test_get_appointments_returns_the_appointments_of_the_client_pets(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """``GET /appointments`` devuelve los turnos de las mascotas del cliente."""
    register_user(email="bruno@example.com", role="client")
    register_user(email="ana@example.com", role="client")
    ana_headers = bearer_headers(email="ana@example.com")
    bruno_headers = bearer_headers(email="bruno@example.com")
    ana_pet = create_pet(client, ana_headers, "Firulais")
    bruno_pet = create_pet(client, bruno_headers, "Rana")
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    other_slot = future_slot(10, 0)

    own = book_appointment(
        client,
        ana_headers,
        pet_id=ana_pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )
    other = book_appointment(
        client,
        bruno_headers,
        pet_id=bruno_pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(other_slot),
    )

    response = client.get("/appointments", headers=ana_headers)

    assert response.status_code == 200
    body = response.json()
    assert [appointment["id"] for appointment in body] == [own.json()["id"]]
    assert body[0]["pet_id"] == ana_pet["id"]
    assert other.json()["id"] not in [appointment["id"] for appointment in body]


def test_get_appointments_returns_the_agenda_of_the_vet(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El veterinario ve los turnos que atiende y solo esos."""
    register_user(email="ana@example.com", role="client")
    register_user(email="bruno@example.com", role="client")
    ana_headers = bearer_headers(email="ana@example.com")
    bruno_headers = bearer_headers(email="bruno@example.com")
    ana_pet = create_pet(client, ana_headers, "Firulais")
    bruno_pet = create_pet(client, bruno_headers, "Rana")
    attended_vet = register_user(email="dr@example.com", role="vet")
    other_vet = register_user(email="dra@example.com", role="vet")
    slot = future_slot(9, 0)

    attended = book_appointment(
        client,
        ana_headers,
        pet_id=ana_pet["id"],
        vet_id=attended_vet["id"],
        start_at=iso_utc(slot),
    )
    other = book_appointment(
        client,
        bruno_headers,
        pet_id=bruno_pet["id"],
        vet_id=other_vet["id"],
        start_at=iso_utc(slot),
    )

    response = client.get("/appointments", headers=bearer_headers(email="dr@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert [appointment["id"] for appointment in body] == [attended.json()["id"]]
    assert all(appointment["vet_id"] == attended_vet["id"] for appointment in body)
    assert other.json()["id"] not in [appointment["id"] for appointment in body]


def test_get_appointments_elements_expose_the_appointment_fields(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Cada elemento del listado lleva los campos del contrato."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    response = client.get("/appointments", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert set(body[0]) == {"id", "pet_id", "vet_id", "start_at", "end_at", "status"}
    assert body[0]["start_at"] == iso_utc(slot)
    assert body[0]["end_at"] == iso_utc(slot + timedelta(minutes=SLOT_MINUTES))
    assert body[0]["status"] == "scheduled"


def test_post_appointments_cancel_by_the_owner_returns_200(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El dueño de la mascota cancela su turno y el estado pasa a ``cancelled``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    booked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    response = client.post(
        f"/appointments/{booked.json()['id']}/cancel",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == booked.json()["id"]
    assert body["status"] == "cancelled"
    assert body["pet_id"] == pet["id"]
    assert body["vet_id"] == vet["id"]
    assert body["start_at"] == iso_utc(slot)
    assert body["end_at"] == iso_utc(slot + timedelta(minutes=SLOT_MINUTES))
    assert db.execute(select(Appointment)).scalars().one().status == "cancelled"


def test_post_appointments_cancel_by_the_vet_returns_200(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """El veterinario que atiende el turno también puede cancelarlo."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    booked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    response = client.post(
        f"/appointments/{booked.json()['id']}/cancel",
        headers=bearer_headers(email="dr@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["id"] == booked.json()["id"]


def test_post_appointments_cancel_by_another_user_returns_403(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Otra cuenta no puede cancelar el turno y el estado no cambia."""
    register_user(email="ana@example.com", role="client")
    register_user(email="bruno@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    booked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    response = client.post(
        f"/appointments/{booked.json()['id']}/cancel",
        headers=bearer_headers(email="bruno@example.com"),
    )

    assert response.status_code == 403
    assert db.execute(select(Appointment)).scalars().one().status == "scheduled"


def test_post_appointments_cancel_twice_returns_409(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Cancelar un turno ya cancelado se rechaza con ``409``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    booked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )
    first = client.post(f"/appointments/{booked.json()['id']}/cancel", headers=headers)

    second = client.post(f"/appointments/{booked.json()['id']}/cancel", headers=headers)

    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert second.status_code == 409


def test_post_appointments_rebooks_a_cancelled_slot(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Un turno cancelado libera su horario y se puede volver a reservar."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    booked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )
    cancelled = client.post(
        f"/appointments/{booked.json()['id']}/cancel",
        headers=headers,
    )

    rebooked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    assert cancelled.status_code == 200
    assert rebooked.status_code == 201
    body = rebooked.json()
    assert body["status"] == "scheduled"
    assert body["id"] != booked.json()["id"]
    assert body["start_at"] == iso_utc(slot)


def test_post_appointments_cancel_of_an_unknown_appointment_returns_404(
    client: TestClient,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Cancelar un turno inexistente se responde con ``404``."""
    register_user(email="ana@example.com", role="client")

    response = client.post(
        "/appointments/999999/cancel",
        headers=bearer_headers(email="ana@example.com"),
    )

    assert response.status_code == 404


def test_post_appointments_without_a_token_returns_401(
    client: TestClient,
    db: Session,
) -> None:
    """Sin cabecera ``Authorization`` la reserva de turnos responde ``401``."""
    response = client.post(
        "/appointments",
        json={"pet_id": 1, "vet_id": 1, "start_at": "2030-03-10T09:00:00Z"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}
    assert count_appointments(db) == 0


def test_get_appointments_without_a_token_returns_401(client: TestClient) -> None:
    """Sin cabecera ``Authorization`` el listado de turnos responde ``401``."""
    response = client.get("/appointments")

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}


def test_post_appointments_cancel_without_a_token_returns_401(
    client: TestClient,
    db: Session,
    register_user: Any,
    bearer_headers: Any,
) -> None:
    """Sin cabecera ``Authorization`` la cancelación responde ``401``."""
    register_user(email="ana@example.com", role="client")
    headers = bearer_headers(email="ana@example.com")
    pet = create_pet(client, headers)
    vet = register_user(email="dr@example.com", role="vet")
    slot = future_slot(9, 0)
    booked = book_appointment(
        client,
        headers,
        pet_id=pet["id"],
        vet_id=vet["id"],
        start_at=iso_utc(slot),
    )

    response = client.post(f"/appointments/{booked.json()['id']}/cancel")

    assert response.status_code == 401
    assert response.json() == {"detail": CREDENTIALS_ERROR}
    assert db.execute(select(Appointment)).scalars().one().status == "scheduled"


def test_appointments_endpoints_with_an_invalid_token_return_401(
    client: TestClient,
    db: Session,
) -> None:
    """Con un token inválido las tres rutas de turnos responden ``401``."""
    booked = client.post("/appointments", headers=INVALID_TOKEN_HEADERS)
    agenda = client.get("/appointments", headers=INVALID_TOKEN_HEADERS)
    cancelled = client.post("/appointments/1/cancel", headers=INVALID_TOKEN_HEADERS)

    assert booked.status_code == 401
    assert agenda.status_code == 401
    assert cancelled.status_code == 401
    assert count_appointments(db) == 0


def test_scheduling_constants_match_the_agenda_rules() -> None:
    """Las constantes de la agenda son las fijadas por el contrato."""
    assert SLOT_MINUTES == 30
    assert OPENING_TIME == time(9, 0)
    assert CLOSING_TIME == time(18, 0)
    assert LAST_START_TIME == time(17, 30)
    assert WORKING_WEEKDAYS == frozenset({0, 1, 2, 3, 4, 5})


def test_slot_end_adds_thirty_minutes() -> None:
    """El turno termina 30 minutos después de su inicio."""
    start = future_slot(9, 0)

    assert slot_end(start) == start + timedelta(minutes=30)


def test_validate_start_at_accepts_the_last_slot_of_the_day() -> None:
    """Las 17:30 son un inicio válido."""
    validate_start_at(future_slot(17, 30).replace(tzinfo=None))


def test_validate_start_at_accepts_saturday() -> None:
    """El sábado es un día con agenda."""
    validate_start_at(future_slot(9, 0, weekday=SATURDAY).replace(tzinfo=None))


def test_validate_start_at_rejects_an_off_grid_start() -> None:
    """Un inicio a las 09:15 no cumple la rejilla de media hora."""
    with pytest.raises(ValueError):
        validate_start_at(future_slot(9, 15).replace(tzinfo=None))


def test_validate_start_at_rejects_sunday() -> None:
    """El domingo no es un día con agenda."""
    with pytest.raises(ValueError):
        validate_start_at(future_slot(9, 0, weekday=SUNDAY).replace(tzinfo=None))


def test_validate_start_at_rejects_the_opening_time() -> None:
    """Un inicio a las 08:30 es anterior a la apertura."""
    with pytest.raises(ValueError):
        validate_start_at(future_slot(8, 30).replace(tzinfo=None))


def test_validate_start_at_rejects_the_closing_time() -> None:
    """Un inicio a las 18:00 supera el último inicio permitido."""
    with pytest.raises(ValueError):
        validate_start_at(future_slot(18, 0).replace(tzinfo=None))


def test_validate_start_at_rejects_a_start_in_the_past() -> None:
    """Un inicio ya transcurrido se rechaza."""
    with pytest.raises(ValueError):
        validate_start_at(datetime(2000, 1, 3, 9, 0))


def test_utc_now_returns_a_naive_utc_instant() -> None:
    """El instante actual de la agenda se expresa en UTC sin zona horaria."""
    now = scheduling.utc_now()

    assert now.tzinfo is None
    assert abs((now - datetime.now(timezone.utc).replace(tzinfo=None))) < timedelta(
        minutes=1
    )
