"""Rutas de la agenda de turnos.

``POST /appointments`` es exclusivo de los clientes y solo admite mascotas
propias; ``GET /appointments`` muestra al cliente los turnos de sus mascotas y
al veterinario los suyos; ``POST /appointments/{id}/cancel`` deja cancelar el
turno al dueño de la mascota y al veterinario que lo atiende.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_client
from app.db.models import Appointment, Pet, User
from app.db.session import get_db
from app.schemas.appointment import AppointmentCreate, AppointmentRead
from app.services.scheduling import (
    CANCELLED_STATUS,
    SCHEDULED_STATUS,
    find_conflicting_appointment,
    slot_end,
    validate_start_at,
)

router = APIRouter(tags=["appointments"])

# Rol de las cuentas que pueden atender turnos.
VET_ROLE = "vet"

# Detalle del error cuando la mascota no existe.
PET_NOT_FOUND_ERROR = "La mascota no existe."

# Detalle del error cuando el veterinario no existe.
VET_NOT_FOUND_ERROR = "El veterinario no existe."

# Detalle del error cuando el turno no existe.
APPOINTMENT_NOT_FOUND_ERROR = "El turno no existe."

# Detalle del error cuando la mascota pertenece a otra cuenta.
PET_NOT_OWNED_ERROR = "La mascota no pertenece a la cuenta autenticada."

# Detalle del error cuando el turno no es del dueño de la mascota ni del
# veterinario que lo atiende.
APPOINTMENT_NOT_OWNED_ERROR = "El turno no corresponde a la cuenta autenticada."

# Detalle del error cuando el veterinario ya tiene un turno en esa franja.
SLOT_TAKEN_ERROR = "El veterinario ya tiene un turno en ese horario."

# Detalle del error cuando el turno ya estaba cancelado.
ALREADY_CANCELLED_ERROR = "El turno ya está cancelado."

# Código de estado de un inicio que no cumple las reglas de la agenda.
INVALID_START_STATUS = 422


def build_appointment_read(appointment: Appointment) -> AppointmentRead:
    """Construye el cuerpo de respuesta de un turno.

    Args:
        appointment: Turno almacenado en la base de datos.

    Returns:
        El turno con los campos del contrato de la API.
    """
    return AppointmentRead(
        id=appointment.id,
        pet_id=appointment.pet_id,
        vet_id=appointment.vet_id,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        status=appointment.status,
    )


@router.post(
    "/appointments",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    payload: AppointmentCreate,
    current_user: User = Depends(require_client),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Reserva un turno de 30 minutos para una mascota del cliente.

    Args:
        payload: Datos del turno solicitado.
        current_user: Cuenta cliente autenticada de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        El turno creado, con su inicio y su final en UTC.

    Raises:
        HTTPException: ``404`` si la mascota o el veterinario no existen, ``403``
            si la mascota es de otra cuenta, ``422`` si el inicio no cumple las
            reglas de la agenda y ``409`` si el horario ya está ocupado.
    """
    pet = db.get(Pet, payload.pet_id)
    if pet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PET_NOT_FOUND_ERROR,
        )
    if pet.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PET_NOT_OWNED_ERROR,
        )

    vet = db.get(User, payload.vet_id)
    if vet is None or vet.role != VET_ROLE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=VET_NOT_FOUND_ERROR,
        )

    try:
        validate_start_at(payload.start_at)
    except ValueError as error:
        raise HTTPException(
            status_code=INVALID_START_STATUS,
            detail=str(error),
        ) from None

    end_at = slot_end(payload.start_at)
    conflict = find_conflicting_appointment(db, vet.id, payload.start_at, end_at)
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=SLOT_TAKEN_ERROR,
        )

    appointment = Appointment(
        pet_id=pet.id,
        vet_id=vet.id,
        start_at=payload.start_at,
        end_at=end_at,
        status=SCHEDULED_STATUS,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return build_appointment_read(appointment)


@router.get("/appointments", response_model=list[AppointmentRead])
def list_appointments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AppointmentRead]:
    """Lista los turnos del cliente o la agenda del veterinario.

    Args:
        current_user: Cuenta autenticada de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        Los turnos de las mascotas del cliente o los turnos atendidos por el
        veterinario, vacíos si no tiene ninguno.
    """
    if current_user.role == VET_ROLE:
        statement = select(Appointment).where(Appointment.vet_id == current_user.id)
    else:
        statement = (
            select(Appointment)
            .join(Pet, Appointment.pet_id == Pet.id)
            .where(Pet.owner_id == current_user.id)
        )
    statement = statement.order_by(Appointment.start_at, Appointment.id)
    appointments = db.execute(statement).scalars().all()
    return [build_appointment_read(appointment) for appointment in appointments]


@router.post("/appointments/{id}/cancel", response_model=AppointmentRead)
def cancel_appointment(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Cancela un turno propio o el atendido por el veterinario.

    Args:
        id: Identificador del turno a cancelar.
        current_user: Cuenta autenticada de la petición.
        db: Sesión de base de datos de la petición.

    Returns:
        El turno cancelado, con los mismos datos y el estado ``cancelled``.

    Raises:
        HTTPException: ``404`` si el turno no existe, ``403`` si el turno no es
            del dueño de la mascota ni del veterinario y ``409`` si el turno ya
            estaba cancelado.
    """
    appointment = db.get(Appointment, id)
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APPOINTMENT_NOT_FOUND_ERROR,
        )

    pet = db.get(Pet, appointment.pet_id)
    is_owner = pet is not None and pet.owner_id == current_user.id
    is_appointed_vet = appointment.vet_id == current_user.id
    if not is_owner and not is_appointed_vet:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=APPOINTMENT_NOT_OWNED_ERROR,
        )

    if appointment.status == CANCELLED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ALREADY_CANCELLED_ERROR,
        )

    appointment.status = CANCELLED_STATUS
    db.commit()
    db.refresh(appointment)
    return build_appointment_read(appointment)
