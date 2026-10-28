"""Punto de entrada de la API de la clínica veterinaria.

La instancia de FastAPI registra los routers de la aplicación, protege con un
token bearer todas las rutas que no son públicas y, durante el arranque, crea
el esquema de la base de datos a partir de los modelos ORM.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from jwt.exceptions import InvalidTokenError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.dependencies import CREDENTIALS_ERROR
from app.api.routes import appointments, auth, health, pets, vets
from app.core.security import decode_access_token, extract_bearer_token

# Importar los modelos registra sus tablas en Base.metadata para el create_all.
from app.db import models  # noqa: F401
from app.db import session as db_session
from app.db.base import Base

# Rutas accesibles sin credenciales.
PUBLIC_PATHS = frozenset({"/health", "/auth/register", "/auth/login"})

# Rutas de documentación de la API, que no exponen datos de la clínica.
DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


def unauthorized_response() -> JSONResponse:
    """Construye la respuesta ``401`` para una credencial ausente o inválida.

    Returns:
        Respuesta JSON con el detalle del error y el encabezado ``WWW-Authenticate``.
    """
    return JSONResponse(
        status_code=401,
        content={"detail": CREDENTIALS_ERROR},
        headers={"WWW-Authenticate": "Bearer"},
    )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Exige un token bearer válido en todas las rutas que no son públicas.

    La comprobación se hace antes del enrutado para que ninguna ruta de la API
    quede accesible sin credenciales. Las rutas que declaran la dependencia
    ``get_current_user`` vuelven a validar el token para resolver la cuenta en
    la base de datos.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Comprueba las credenciales antes de atender la petición.

        Args:
            request: Petición entrante.
            call_next: Siguiente paso de la cadena de middlewares.

        Returns:
            La respuesta de la ruta o un ``401`` si faltan credenciales válidas.
        """
        path = request.url.path.rstrip("/") or "/"
        if path in PUBLIC_PATHS or path in DOCS_PATHS:
            return await call_next(request)

        token = extract_bearer_token(request.headers.get("authorization"))
        if token is None:
            return unauthorized_response()
        try:
            decode_access_token(token)
        except InvalidTokenError:
            return unauthorized_response()
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Crea el esquema de la base de datos al arrancar la aplicación.

    Args:
        app: Instancia de FastAPI que se está arrancando.

    Yields:
        Control devuelto a la aplicación mientras el proceso sigue vivo.
    """
    Base.metadata.create_all(bind=db_session.engine)
    yield


app = FastAPI(
    title="API Clínica Veterinaria",
    description="Gestión de cuentas, mascotas y turnos de la clínica veterinaria.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(BearerAuthMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(vets.router)
app.include_router(pets.router)
app.include_router(appointments.router)
