"""Rutas de registro y consulta de mascotas.

``POST /pets`` es exclusivo de los clientes: la mascota queda a nombre de la
cuenta autenticada y un veterinario recibe ``403``. ``GET /pets`` devuelve
únicamente las mascotas de la cuenta que llama, de modo que un cliente no ve
las mascotas de otro cliente y un veterinario obtiene un arreglo vacío.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_client
from app.db.models import Pet, User
from app.db.session import get_db
from app.schemas.pet import PetCreate, PetRead

router = APIRouter(tags=["pets"])


@router.post(
    "/pets",
    response_model=PetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_pet(
    payload: PetCreate,
    current_user: User = Depends(require_client),
    db: Session = Depends(get_db),
) -> PetRead:
    """Registra una mascota a nombre del cliente autenticado.

    Args:
        payload: Datos de la mascota nueva.
        current_user: Cuenta cliente autenticada de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        La mascota creada, con el identificador de su propietario.
    """
    pet = Pet(
        name=payload.name,
        species=payload.species,
        birth_date=payload.birth_date,
        owner_id=current_user.id,
    )
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return PetRead(
        id=pet.id,
        name=pet.name,
        species=pet.species,
        birth_date=pet.birth_date,
        owner_id=pet.owner_id,
    )


@router.get("/pets", response_model=list[PetRead])
def list_pets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PetRead]:
    """Lista las mascotas de la cuenta autenticada.

    Args:
        current_user: Cuenta autenticada de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        Las mascotas propiedad de la cuenta, vacías si no tiene ninguna.
    """
    statement = select(Pet).where(Pet.owner_id == current_user.id).order_by(Pet.id)
    pets = db.execute(statement).scalars().all()
    return [
        PetRead(
            id=pet.id,
            name=pet.name,
            species=pet.species,
            birth_date=pet.birth_date,
            owner_id=pet.owner_id,
        )
        for pet in pets
    ]
