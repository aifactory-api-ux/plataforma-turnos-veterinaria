# Imagen de la API de la clínica veterinaria.
#
# La construcción tiene dos etapas. La primera instala las dependencias de
# Python en un virtualenv; la segunda copia ese virtualenv y el código de la
# aplicación, de modo que la imagen final no arrastra las herramientas de
# compilación. La API se ejecuta con un usuario sin privilegios.
#
# La misma imagen sirve para la API y para la suite de tests: el servicio
# `tests` del `docker-compose.yml` sobrescribe el comando con `pytest -q`.

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-dev.txt ./

RUN pip install --upgrade pip \
    && pip install -r requirements.txt -r requirements-dev.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Cuenta de servicio sin privilegios:root para ejecutar la API.
RUN groupadd --system --gid 1001 vetclinic \
    && useradd --system --uid 1001 --gid vetclinic \
        --home-dir /app --shell /usr/sbin/nologin vetclinic

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=vetclinic:vetclinic app ./app
COPY --chown=vetclinic:vetclinic tests ./tests
COPY --chown=vetclinic:vetclinic pyproject.toml conftest.py ./

USER vetclinic

EXPOSE 8000

# Comprobación de disponibilidad contra el endpoint público de la API.
# Se usa urllib para no instalar curl en la imagen.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
