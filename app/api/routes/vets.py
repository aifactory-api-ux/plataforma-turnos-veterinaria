"""Ruta del directorio de veterinarios.

``GET /vets`` devuelve las cuentas registradas con el rol ``vet`` para que un
cliente pueda saber a qué veterinario agendar un turno. La ruta exige un token
bearer válido y cada elemento del arreglo lleva únicamente el identificador y
el correo de la cuenta.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.user import VetRead

router = APIRouter(tags=["vets"])

# Rol de las cuentas que forman el directorio de veterinarios.
VET_ROLE = "vet"


@router.get("/vets", response_model=list[VetRead])
def list_vets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VetRead]:
    """Lista las cuentas de los veterinarios de la clínica.

    Args:
        current_user: Cuenta autenticada de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        Una lista con el identificador y el correo de cada veterinario, vacía si
        todavía no hay ninguna cuenta con ese rol.
    """
    statement = select(User).where(User.role == VET_ROLE).order_by(User.id)
    vets = db.execute(statement).scalars().all()
    return [VetRead(id=vet.id, email=vet.email) for vet in vets]
