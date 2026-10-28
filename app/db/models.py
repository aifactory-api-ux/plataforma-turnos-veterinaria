"""Modelos ORM de cuentas, mascotas y turnos.

Las columnas siguen la tabla de diseño de ``design.md``. Las fechas de turno se
guardan como ``DateTime`` naive en UTC para que el esquema funcione igual en
PostgreSQL (producción) y en SQLite (suite de tests local).
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Cuenta de acceso a la plataforma, con rol ``client`` o ``vet``."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    pets: Mapped[list["Pet"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    appointments_as_vet: Mapped[list["Appointment"]] = relationship(
        back_populates="vet",
        foreign_keys="Appointment.vet_id",
    )


class Pet(Base):
    """Mascota registrada por un cliente."""

    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    species: Mapped[str] = mapped_column(String(20), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    owner: Mapped["User"] = relationship(back_populates="pets")
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="pet",
        cascade="all, delete-orphan",
    )


class Appointment(Base):
    """Turno de 30 minutos entre una mascota y un veterinario."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vet_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    pet: Mapped["Pet"] = relationship(back_populates="appointments")
    vet: Mapped["User"] = relationship(
        back_populates="appointments_as_vet",
        foreign_keys=[vet_id],
    )

    __table_args__ = (
        # Índice compuesto para detectar solapamientos por veterinario.
        Index("ix_appointments_vet_start_at", "vet_id", "start_at"),
    )
