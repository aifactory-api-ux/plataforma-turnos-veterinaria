"""Configuración de la aplicación leída desde el entorno.

Los valores se resuelven desde variables de entorno y, si existe un archivo
``.env`` en la raíz del repositorio, desde ese archivo. ``JWT_SECRET_KEY`` es
el único valor sensible: en producción debe proveerse desde el despliegue y
nunca debe usarse el valor por defecto de desarrollo.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuración de la API.

    Atributos:
        database_url: URL de conexión a PostgreSQL.
        jwt_secret_key: clave de firma de los tokens JWT.
        access_token_expire_minutes: vigencia del token en minutos.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg2://vetclinic:vetclinic@localhost:5432/vetclinic"
    jwt_secret_key: str = "clave-de-desarrollo-no-usar-en-produccion"
    access_token_expire_minutes: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración de la aplicación, cacheada por proceso."""
    return Settings()
