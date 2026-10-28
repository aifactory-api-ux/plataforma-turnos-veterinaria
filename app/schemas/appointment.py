"""Esquemas de alta, consulta y cancelación de turnos.

La entrada se normaliza a UTC en un único punto: una marca de tiempo sin
desplazamiento se interpreta como UTC y una marca con desplazamiento se
convierte a su instante UTC equivalente. La salida se emite siempre en UTC con
el sufijo ``Z``, por ejemplo ``2025-03-10T09:00:00Z``.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_serializer, field_validator

# Estados posibles de un turno.
AppointmentStatus = Literal["scheduled", "cancelled"]


def to_utc_naive(value: datetime) -> datetime:
    """Normaliza una marca de tiempo al instante UTC sin zona horaria.

    Las marcas sin desplazamiento se interpretan como UTC; las que lo llevan se
    convierten a su instante UTC equivalente. El resultado se guarda en la base
    de datos como ``DateTime`` naive en UTC, de modo que el esquema funcione
    igual en PostgreSQL y en SQLite.

    Args:
        value: Marca de tiempo recibida en la petición.

    Returns:
        El mismo instante expresado en UTC, sin información de zona horaria.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def format_utc(value: datetime) -> str:
    """Serializa una marca de tiempo en ISO 8601 UTC con el sufijo ``Z``.

    Args:
        value: Marca de tiempo en UTC, con o sin zona horaria.

    Returns:
        La marca de tiempo en formato ``2025-03-10T09:00:00Z``.
    """
    if value.tzinfo is None:
        aware = value.replace(tzinfo=timezone.utc)
    else:
        aware = value.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


class AppointmentCreate(BaseModel):
    """Cuerpo de ``POST /appointments``.

    Attributes:
        pet_id: Identificador de la mascota que attends el turno.
        vet_id: Identificador del veterinario que atiende el turno.
        start_at: Inicio del turno, que se normaliza a UTC.
    """

    pet_id: int
    vet_id: int
    start_at: datetime

    @field_validator("start_at")
    @classmethod
    def normalize_start_at(cls, value: datetime) -> datetime:
        """Normaliza el inicio del turno al instante UTC.

        Args:
            value: Inicio del turno recibido en la petición.

        Returns:
            El mismo instante expresado en UTC, sin zona horaria.
        """
        return to_utc_naive(value)


class AppointmentRead(BaseModel):
    """Cuerpo de un turno en las respuestas de la API.

    Attributes:
        id: Identificador del turno.
        pet_id: Identificador de la mascota que attends el turno.
        vet_id: Identificador del veterinario que atiende el turno.
        start_at: Inicio del turno, en UTC.
        end_at: Final del turno, en UTC.
        status: Estado del turno, ``scheduled`` o ``cancelled``.
    """

    id: int
    pet_id: int
    vet_id: int
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus

    @field_serializer("start_at")
    def serialize_start_at(self, value: datetime) -> str:
        """Serializa el inicio del turno en UTC con el sufijo ``Z``.

        Args:
            value: Inicio del turno almacenado.

        Returns:
            La marca de tiempo en formato ISO 8601 UTC.
        """
        return format_utc(value)

    @field_serializer("end_at")
    def serialize_end_at(self, value: datetime) -> str:
        """Serializa el final del turno en UTC con el sufijo ``Z``.

        Args:
            value: Final del turno almacenado.

        Returns:
            La marca de tiempo en formato ISO 8601 UTC.
        """
        return format_utc(value)
