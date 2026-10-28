"""Esquemas de registro de cuentas e inicio de sesión.

La validación del correo se hace con una expresión regular propia para no
depender de validadores externos: el contrato de la API solo exige rechazar los
correos mal formados con ``422``.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Longitud mínima de la contraseña exigida por el contrato de la API.
MIN_PASSWORD_LENGTH = 8

# Límite técnico de bcrypt: una contraseña más larga se truncaría en silencio.
MAX_PASSWORD_BYTES = 72

# Formato mínimo de un correo: parte local, arroba y dominio con punto.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Roles aceptados por la API.
Role = Literal["client", "vet"]


class RegisterRequest(BaseModel):
    """Cuerpo de ``POST /auth/register``.

    Attributes:
        email: Correo de la cuenta nueva.
        password: Contraseña de la cuenta nueva.
        role: Rol de la cuenta, ``client`` o ``vet``.
    """

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    role: Role

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Comprueba el formato del correo.

        Args:
            value: Correo recibido en la petición.

        Returns:
            El correo sin espacios sobrantes.

        Raises:
            ValueError: Si el correo no tiene un formato válido.
        """
        candidate = value.strip()
        if not EMAIL_PATTERN.match(candidate):
            raise ValueError("El correo no tiene un formato válido.")
        return candidate

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Comprueba que la contraseña quepa en el límite de bcrypt.

        Args:
            value: Contraseña recibida en la petición.

        Returns:
            La contraseña sin modificar.

        Raises:
            ValueError: Si la contraseña supera el máximo de bytes admitidos.
        """
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"La contraseña no puede superar los {MAX_PASSWORD_BYTES} bytes."
            )
        return value


class RegisterResponse(BaseModel):
    """Cuerpo de la respuesta ``201`` de ``POST /auth/register``.

    Attributes:
        id: Identificador de la cuenta creada.
        email: Correo de la cuenta creada.
        role: Rol de la cuenta creada.
    """

    id: int
    email: str
    role: str


class LoginRequest(BaseModel):
    """Cuerpo de ``POST /auth/login``.

    Attributes:
        email: Correo de la cuenta.
        password: Contraseña de la cuenta.
    """

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """Cuerpo de la respuesta ``200`` de ``POST /auth/login``.

    Attributes:
        access_token: Token JWT de acceso.
        token_type: Tipo del token, siempre ``bearer``.
    """

    access_token: str
    token_type: str = "bearer"
