"""Rutas de registro de cuentas e inicio de sesión.

El registro compara los correos sin distinguir mayúsculas de minúsculas para
que una misma dirección no pueda tener dos cuentas. El login responde siempre
``401`` ante credenciales incorrectas, sin indicar si el fallo fue la
contraseña o el correo.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Detalle del conflicto de correo duplicado.
DUPLICATE_EMAIL_ERROR = "El correo ya está registrado."

# Detalle único de un login fallido: no revela cuál de los dos datos falló.
INVALID_CREDENTIALS_ERROR = "Credenciales inválidas."


def normalize_email(email: str) -> str:
    """Normaliza un correo para compararlo y almacenarlo de forma canónica.

    Args:
        email: Correo recibido en la petición.

    Returns:
        El correo sin espacios y en minúsculas.
    """
    return email.strip().lower()


def find_user_by_email(db: Session, email: str) -> User | None:
    """Busca una cuenta por correo, ignorando mayúsculas y minúsculas.

    Args:
        db: Sesión de base de datos de la petición.
        email: Correo a buscar.

    Returns:
        La cuenta encontrada o ``None`` si no existe ninguna con ese correo.
    """
    statement = select(User).where(func.lower(User.email) == normalize_email(email))
    return db.execute(statement).scalars().first()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_account(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """Registra una cuenta nueva de cliente o de veterinario.

    Args:
        payload: Datos de la cuenta nueva.
        db: Sesión de base de datos de la petición.

    Returns:
        La cuenta creada, sin ningún dato de credencial.

    Raises:
        HTTPException: ``409`` si el correo ya está registrado.
    """
    email = normalize_email(payload.email)
    if find_user_by_email(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DUPLICATE_EMAIL_ERROR,
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DUPLICATE_EMAIL_ERROR,
        ) from None
    db.refresh(user)
    return RegisterResponse(id=user.id, email=user.email, role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Autentica una cuenta y emite su token de acceso.

    Args:
        payload: Credenciales de la cuenta.
        db: Sesión de base de datos de la petición.

    Returns:
        El token JWT de acceso y su tipo.

    Raises:
        HTTPException: ``401`` si el correo no existe o la contraseña no coincide.
    """
    user = find_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(access_token=access_token, token_type="bearer")
