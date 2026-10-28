"""Hash de contraseñas y emisión y verificación de los tokens JWT.

Las contraseñas se guardan con ``bcrypt`` (sal por contraseña) y los tokens de
acceso son JWT firmados con HS256 usando ``JWT_SECRET_KEY``. El payload del
token lleva ``sub`` (identificador de la cuenta), ``role`` y ``exp``.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings

# Algoritmo de firma de los tokens de acceso.
ALGORITHM = "HS256"

# Claims que todo token válido debe incluir.
REQUIRED_CLAIMS = ["exp", "sub", "role"]

# Límite técnico de bcrypt: las contraseñas más largas se truncan en silencio,
# por lo que el esquema las rechaza antes de llegar al hash.
BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en texto plano.

    Args:
        password: Contraseña en texto plano.

    Returns:
        Hash bcrypt con su sal, listo para guardarse en la base de datos.
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Comprueba una contraseña en texto plano contra su hash bcrypt.

    Args:
        plain_password: Contraseña recibida en la petición.
        password_hash: Hash almacenado de la cuenta.

    Returns:
        ``True`` si la contraseña coincide con el hash, ``False`` en caso contrario.
    """
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def extract_bearer_token(authorization: str | None) -> str | None:
    """Extrae el token de una cabecera ``Authorization: Bearer <token>``.

    Args:
        authorization: Valor crudo de la cabecera ``Authorization``.

    Returns:
        El token si la cabecera es válida, ``None`` si falta o no es un bearer.
    """
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    candidate = token.strip()
    return candidate or None


def create_access_token(
    subject: str | int,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Emite un token de acceso JWT firmado con HS256.

    Args:
        subject: Identificador de la cuenta, que viaja en el claim ``sub``.
        role: Rol de la cuenta, que viaja en el claim ``role``.
        expires_delta: Vigencia del token; por defecto se usa la configurada
            en ``ACCESS_TOKEN_EXPIRE_MINUTES``.

    Returns:
        Token JWT en texto plano.
    """
    settings = get_settings()
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    issued_at = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodifica un token de acceso y valida su firma y su expiración.

    Args:
        token: Token JWT recibido en la cabecera ``Authorization``.

    Returns:
        Claims del token decodificado.

    Raises:
        InvalidTokenError: Si el token está mal formado, ha expirado, no lleva
            los claims obligatorios o está firmado con otra clave.
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[ALGORITHM],
        options={"require": REQUIRED_CLAIMS},
    )
