"""Ruta pública de verificación de disponibilidad del servicio."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    """Comprueba que la API está viva.

    No requiere autenticación: se usa tanto desde el monitor de la clínica como
    desde el ``HEALTHCHECK`` del contenedor.

    Returns:
        Cuerpo ``{"status": "ok"}`` con el estado del servicio.
    """
    return HealthResponse(status="ok")
