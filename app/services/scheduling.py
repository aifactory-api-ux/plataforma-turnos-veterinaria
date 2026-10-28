"""Reglas de disponibilidad de la agenda de turnos.

Este módulo es la única fuente de verdad sobre las franjas horarias de la
clínica: duración de cada turno, ventana laboral, días con agenda y detección
de solapamientos por veterinario. Las rutas HTTP no replican estas reglas, solo
las aplican y traducen su rechazo al código de estado ``422`` del contrato.
"""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Appointment

# Duración de cada turno, en minutos.
SLOT_MINUTES = 30

# Hora de apertura de la clínica, en UTC.
OPENING_TIME = time(9, 0)

# Hora de cierre de la clínica, en UTC.
CLOSING_TIME = time(18, 0)

# Última hora a la que puede comenzar un turno, en UTC.
LAST_START_TIME = time(17, 30)

# Días con agenda: de lunes (0) a sábado (5). El domingo no atiende.
WORKING_WEEKDAYS = frozenset({0, 1, 2, 3, 4, 5})

# Estado de un turno que ocupa la agenda del veterinario.
SCHEDULED_STATUS = "scheduled"

# Estado de un turno liberado por el dueño de la mascota o por el veterinario.
CANCELLED_STATUS = "cancelled"

# Margen de tolerancia al comparar el inicio con el instante actual, para que
# un turno que empieza "en este momento" no se invalide por el paso del reloj
# entre la comprobación y la reserva.
PAST_TOLERANCE = timedelta(minutes=1)


def utc_now() -> datetime:
    """Devuelve el instante actual en UTC, sin información de zona horaria.

    Returns:
        El instante actual en UTC, con la misma representación que se usa en
        la base de datos.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def slot_end(start_at: datetime) -> datetime:
    """Devuelve el final del turno que empieza en el instante indicado.

    Args:
        start_at: Inicio del turno, en UTC.

    Returns:
        El instante en el que termina el turno.
    """
    return start_at + timedelta(minutes=SLOT_MINUTES)


def is_working_day(moment: datetime) -> bool:
    """Indica si el instante cae en un día con agenda.

    Args:
        moment: Instante a comprobar, en UTC.

    Returns:
        ``True`` si es de lunes a sábado.
    """
    return moment.weekday() in WORKING_WEEKDAYS


def is_on_grid(moment: datetime) -> bool:
    """Indica si el instante cae en punto o y media.

    Args:
        moment: Instante a comprobar, en UTC.

    Returns:
        ``True`` si el minuto es ``00`` o ``30`` y no hay segundos.
    """
    return moment.minute in (0, 30) and moment.second == 0 and moment.microsecond == 0


def is_within_window(moment: datetime) -> bool:
    """Indica si el turno completo cabe dentro de la ventana laboral.

    Args:
        moment: Inicio del turno, en UTC.

    Returns:
        ``True`` si el turno empieza dentro del horario y termina antes del
        cierre de la clínica.
    """
    if not OPENING_TIME <= moment.time() <= LAST_START_TIME:
        return False
    return slot_end(moment).time() <= CLOSING_TIME


def is_in_the_future(moment: datetime, now: datetime | None = None) -> bool:
    """Indica si el instante todavía no ha pasado.

    Args:
        moment: Instante a comprobar, en UTC.
        now: Instante de referencia; por defecto, el instante actual.

    Returns:
        ``True`` si el instante es igual o posterior a la referencia.
    """
    reference = utc_now() if now is None else now
    return moment >= reference - PAST_TOLERANCE


def validate_start_at(start_at: datetime, now: datetime | None = None) -> None:
    """Comprueba que el inicio del turno cumple todas las reglas de la agenda.

    Args:
        start_at: Inicio del turno, ya normalizado a UTC.
        now: Instante de referencia para la regla de pasado; por defecto, el
            instante actual.

    Raises:
        ValueError: Si el inicio incumple alguna regla, con el motivo del
            rechazo.
    """
    if not is_working_day(start_at):
        raise ValueError("Los turnos se agendan de lunes a sábado.")
    if not is_on_grid(start_at):
        raise ValueError("Los turnos comienzan en punto o y media.")
    if not is_within_window(start_at):
        raise ValueError(
            "Los turnos se agendan entre las 09:00 y las 17:30 y duran 30 minutos."
        )
    if not is_in_the_future(start_at, now):
        raise ValueError("El turno no puede empezar en el pasado.")


def slots_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    """Indica si dos intervalos de tiempo se solapan.

    Args:
        start_a: Inicio del primer intervalo.
        end_a: Final del primer intervalo.
        start_b: Inicio del segundo intervalo.
        end_b: Final del segundo intervalo.

    Returns:
        ``True`` si los intervalos comparten parte de su recorrido.
    """
    return start_a < end_b and start_b < end_a


def find_conflicting_appointment(
    db: Session,
    vet_id: int,
    start_at: datetime,
    end_at: datetime,
) -> Appointment | None:
    """Busca un turno activo del veterinario que se solape con la franja pedida.

    Solo se consideran los turnos con estado ``scheduled``: un turno cancelado
    libera su horario y no bloquea una reserva nueva.

    Args:
        db: Sesión de base de datos de la petición.
        vet_id: Identificador del veterinario.
        start_at: Inicio de la franja pedida, en UTC.
        end_at: Final de la franja pedida, en UTC.

    Returns:
        El turno que entra en conflicto o ``None`` si el horario está libre.
    """
    statement = (
        select(Appointment)
        .where(Appointment.vet_id == vet_id)
        .where(Appointment.status == SCHEDULED_STATUS)
        .where(Appointment.start_at < end_at)
        .where(Appointment.end_at > start_at)
        .order_by(Appointment.id)
    )
    return db.execute(statement).scalars().first()


def has_conflicting_appointment(
    db: Session,
    vet_id: int,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    """Indica si el veterinario ya tiene un turno activo en esa franja.

    Args:
        db: Sesión de base de datos de la petición.
        vet_id: Identificador del veterinario.
        start_at: Inicio de la franja pedida, en UTC.
        end_at: Final de la franja pedida, en UTC.

    Returns:
        ``True`` si ya hay un turno ``scheduled`` que se solapa.
    """
    return find_conflicting_appointment(db, vet_id, start_at, end_at) is not None
