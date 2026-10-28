"""Dependencias de autenticación y autorización de la API.

``get_current_user`` resuelve la cuenta que llama a partir del token bearer de
la petición y responde ``401`` ante cualquier credencial ausente o inválida.
``require_client`` y ``require_vet`` restringen el acceso por rol y responden
``403`` cuando el rol de la cuenta no corresponde.
"""

from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, extract_bearer_token
from app.db.models import User
from app.db.session import get_db

# Mensaje único para cualquier credencial inválida: no revela si el token
# existe, si expiró o si simplemente falta.
CREDENTIALS_ERROR = "Credenciales inválidas o ausentes."

# Mensaje único para un rol que no puede usar el recurso solicitado.
ROLE_ERROR = "El rol de la cuenta no permite esta operación."


def _unauthorized() -> HTTPException:
    """Construye el error ``401`` con el encabezado ``WWW-Authenticate``.

    Returns:
        Excepción con el detalle y el encabezado de autenticación por bearer.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=CREDENTIALS_ERROR,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Resuelve la cuenta autenticada de la petición.

    Args:
        authorization: Cabecera ``Authorization`` de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        La cuenta a la que pertenece el token.

    Raises:
        HTTPException: ``401`` si falta la cabecera, el token no es válido o la
            cuenta ya no existe.
    """
    token = extract_bearer_token(authorization)
    if token is None:
        raise _unauthorized()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise _unauthorized() from None

    subject = payload.get("sub")
    try:
        user_id = int(subject)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise _unauthorized() from None

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user


def require_client(current_user: User = Depends(get_current_user)) -> User:
    """Exige que la cuenta autenticada tenga el rol ``client``.

    Args:
        current_user: Cuenta autenticada de la petición.

    Returns:
        La misma cuenta, si su rol es ``client``.

    Raises:
        HTTPException: ``403`` cuando la cuenta no es un cliente.
    """
    if current_user.role != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ROLE_ERROR,
        )
    return current_user


def require_vet(current_user: User = Depends(get_current_user)) -> User:
    """Exige que la cuenta autenticada tenga el rol ``vet``.

    Args:
        current_user: Cuenta autenticada de la petición.

    Returns:
        La misma cuenta, si su rol es ``vet``.

    Raises:
        HTTPException: ``403`` cuando la cuenta no es un veterinario.
    """
    if current_user.role != "vet":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ROLE_ERROR,
        )
    return current_user
