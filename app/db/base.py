"""Base declarativa de SQLAlchemy.

Define la metadata común a todos los modelos y la convención de nombres de
las restricciones, para que el esquema generado sea estable y predecible.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convención de nombres: PK, FK, índices y unicidades con nombres derivados
# de la tabla y la columna, en lugar de nombres generados por el motor.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa de la que heredan los modelos ORM."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
