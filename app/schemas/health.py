"""Esquemas del endpoint de estado del servicio."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Cuerpo de la respuesta de ``GET /health``.

    Attributes:
        status: Estado del servicio; vale ``ok`` cuando la API responde.
    """

    status: str
