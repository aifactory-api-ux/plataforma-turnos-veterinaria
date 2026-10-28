"""Esquemas de alta y consulta de mascotas.

El alta valida la especie (solo ``dog``, ``cat`` u ``other``) y la fecha de
nacimiento, que no puede ser posterior al día actual. La fecha actual se toma
en UTC, la única zona horaria de la plataforma.
"""

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Especies admitidas por la API.
Species = Literal["dog", "cat", "other"]

# Longitud máxima del nombre, igual que la columna de la tabla ``pets``.
MAX_NAME_LENGTH = 120


def current_date() -> date:
    """Devuelve la fecha actual en UTC.

    Returns:
        El día de hoy en UTC, usado como límite de la fecha de nacimiento.
    """
    return datetime.now(timezone.utc).date()


class PetCreate(BaseModel):
    """Cuerpo de ``POST /pets``.

    Attributes:
        name: Nombre de la mascota.
        species: Especie de la mascota, ``dog``, ``cat`` u ``other``.
        birth_date: Fecha de nacimiento, que no puede ser futura.
    """

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    species: Species
    birth_date: date

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        """Comprueba que la fecha de nacimiento no sea posterior a hoy.

        Args:
            value: Fecha de nacimiento recibida en la petición.

        Returns:
            La fecha recibida, sin modificar.

        Raises:
            ValueError: Si la fecha de nacimiento está en el futuro.
        """
        if value > current_date():
            raise ValueError("La fecha de nacimiento no puede ser futura.")
        return value


class PetRead(BaseModel):
    """Cuerpo de una mascota en las respuestas de la API.

    Attributes:
        id: Identificador de la mascota.
        name: Nombre de la mascota.
        species: Especie de la mascota.
        birth_date: Fecha de nacimiento de la mascota.
        owner_id: Identificador de la cuenta propietaria.
    """

    id: int
    name: str
    species: str
    birth_date: date
    owner_id: int
