"""Esquemas de lectura de las cuentas de la API.

El directorio de veterinarios solo expone el identificador y el correo de cada
cuenta: ni la contraseña ni su hash salen de la capa de datos.
"""

from pydantic import BaseModel


class VetRead(BaseModel):
    """Cuerpo de un elemento del directorio de veterinarios.

    Attributes:
        id: Identificador de la cuenta del veterinario.
        email: Correo de la cuenta del veterinario.
    """

    id: int
    email: str
