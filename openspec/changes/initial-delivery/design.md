# Design

## Context

- El repositorio está vacío salvo la estructura de OpenSpec (`openspec/`). No hay código, ni dependencias, ni infraestructura previa que haya que preservar o migrar.
- La plataforma es interna a la clínica: un único equipo la usa, sin clientes externos, sin multi-tenant y sin frontend. La única superficie externa es la API REST.
- Requisito transversal del proyecto: todo se entrega containerizado (`Dockerfile` + `docker-compose.yml` en la raíz) y el último grupo de tareas debe verificar que `docker compose up --build` termina con código de salida 0.
- El equipo es el agente Developer únicamente: también escribe y mantiene las pruebas con pytest. No hay QA ni DevSec, por lo que la suite debe poder ejecutarse en un solo comando y ser legible para quien la lea.
- Los contratos de comportamiento (endpoints, códigos de estado, límites y reglas) están fijados en `openspec/changes/initial-delivery/specs/`; este documento explica cómo se implementan.

## Goals / Non-Goals

**Goals:**
- Un monolito modular pequeño: FastAPI + PostgreSQL, con capas claras (routers → servicios → modelos) y una sola fuente de verdad para las reglas de agenda.
- Una suite pytest que el Developer pueda ejecutar localmente sin infraestructura y también dentro del contenedor, contra PostgreSQL real.
- Una imagen Docker reproducible que sirva la API y sirva para correr los tests.
- Errores uniformes y predecibles: el contrato HTTP (201/200/401/403/404/409/422) queda garantizado en un solo lugar por endpoint.

**Non-Goals:**
- Multi-clínica, multi-tenant, roles adicionales (admin), facturación, notificaciones, frontend, reporting, OAuth/SSO, verificación de email o recuperación de contraseña.
- Alembic y cualquier tooling de migraciones versionadas: es la primera entrega y no hay datos que preservar.
- ReGLAS de negocio no pedidas (por ejemplo, impedir dos turnos simultáneos de una misma mascota, o bloqueos por Indonesian holidays, feriados o vacations).

## Decisions

### 1. Estructura del proyecto

```
/app/main.py                 # instancia FastAPI, lifespan (create_all), registro de routers
/app/core/config.py          # Settings (pydantic-settings) leídas del entorno
/app/core/security.py        # hash/verify de contraseñas y emisión/verificación del JWT
/app/db/base.py              # Base declarativa de SQLAlchemy
/app/db/session.py           # engine, SessionLocal y dependencia get_db
/app/db/models.py            # User, Pet, Appointment
/app/schemas/health.py       # HealthResponse
/app/schemas/auth.py         # RegisterRequest, RegisterResponse, LoginRequest, TokenResponse
/app/schemas/user.py         # VetRead {id, email}
/app/schemas/pet.py          # PetCreate, PetRead
/app/schemas/appointment.py  # AppointmentCreate, AppointmentRead
/app/api/dependencies.py     # get_current_user (401), require_client (403), require_vet
/app/api/routes/health.py
/app/api/routes/auth.py
/app/api/routes/vets.py
/app/api/routes/pets.py
/app/api/routes/appointments.py
/app/services/scheduling.py  # reglas de slot de 30 min, ventana laboral y solapamiento
/tests/conftest.py           # fixtures: engine/sesión de test, TestClient, factories de datos
/tests/test_health.py
/tests/test_auth.py
/tests/test_vets.py
/tests/test_pets.py
/tests/test_appointments.py
/tests/test_delivery_files.py
/requirements.txt            # dependencias de runtime
/requirements-dev.txt        # pytest, httpx y herramientas de desarrollo
/pyproject.toml              # configuración de pytest
/Dockerfile
/docker-compose.yml
/scripts/verify_stack.sh     # verificación de "docker compose up --build" con código de salida 0
/README.md
/.env.example
/.dockerignore
```

Alternativa descartada: un único módulo `main.py` con todo el código. Se descarta porque el tamaño del dominio (agenda, ownership, roles) hace que un solo archivo ilegible y las reglas de negocio quedarían mezcladas con el transporte HTTP.

### 2. Acceso a datos: SQLAlchemy 2.0 síncrono + PostgreSQL

SQLAlchemy 2.0 (ORM síncrono, `DeclarativeBase`) con driver `psycopg2-binary`; la URL de conexión viene de `DATABASE_URL`. Se usa el ORM síncrono en lugar de async porque el proyecto no tiene una carga que justifique el event loop y el ORM síncrono simplifica el manejo de transacciones y el uso de `TestClient`.

El esquema se crea al arrancar la aplicación con `Base.metadata.create_all(engine)` dentro del `lifespan` de FastAPI. Alternativa descartada: Alembic, porque no hay datos existentes que migrar y el pedido no lo pide; el coste es que no hay versionado de esquema (ver Riesgos).

Modelos (sin tipos exclusivos de PostgreSQL: `String`, `Integer`, `Date`, `DateTime`, `ForeignKey`):

| Tabla | Columnas | Notas |
| --- | --- | --- |
| `users` | `id` PK, `email` UNIQUE NOT NULL, `password_hash` NOT NULL, `role` NOT NULL | `role` en `{"client","vet"}`; `email` UNIQUE en BD + comparación case-insensitive en la capa de aplicación |
| `pets` | `id` PK, `name` NOT NULL, `species` NOT NULL, `birth_date` NOT NULL, `owner_id` FK `users.id` NOT NULL | índices por `owner_id` |
| `appointments` | `id` PK, `pet_id` FK `pets.id` NOT NULL, `vet_id` FK `users.id` NOT NULL, `start_at` NOT NULL, `end_at` NOT NULL, `status` NOT NULL | índices por `vet_id` y por `start_at`; `status` en `{"scheduled","cancelled"}` |

### 3. Horarios: UTC como única zona

`start_at` se almacena como `DateTime` **naive en UTC** y se serializa con sufijo `Z` (`2025-03-10T09:00:00Z`). Motivo: el mismo modelo debe funcionar sobre PostgreSQL (producción) y sobre SQLite (ejecución local de los tests) sin diferencias de comparación; con `TIMESTAMPTZ` la comparación naïve/aware se rompe entre backends. La conversión ocurre en un único punto (`app/schemas/appointment.py` validador + serializador de `AppointmentRead`): la entrada se normaliza a UTC (naive ⇒ se asume UTC; con offset ⇒ se convierte a UTC) y la salida se emite siempre en UTC con `Z`.

Reglas de agenda, todas en `app/services/scheduling.py` y parametrizadas por constantes (`SLOT_MINUTES = 30`, `OPENING_TIME = 09:00`, `CLOSING_TIME = 18:00`, `LAST_START_TIME = 17:30`, `WORKING_WEEKDAYS = {0..5}`):

- minuto de `start_at` ∈ {0, 30};
- día de la semana ∈ lunes..sábado;
- `09:00 <= start_at <= 17:30` (con `end_at = start_at + 30 min`, el turno nunca sobrepasa las 18:00);
- `start_at >= ahora` (comparación contra el instante actual, con margen de 1 minuto para evitar que un test se auto-invalide por el paso del reloj).

Alternativa descartada: calcular los slots válidos con una tabla de franjas en BD; es más flexible (feriados, excepciones) pero el pedido define una ventana fija, así que la regla se mantiene en código.

### 4. Autenticación: JWT HS256 + bcrypt

- Contraseñas con `bcrypt` (hash con sal por contraseña, coste por defecto de la librería). Alternativa descartada: `passlib[bcrypt]`, que tiene incompatibilidades conocidas con bcrypt 4.x+ y añade una capa de indirección. El límite técnico de 72 bytes de bcrypt se traduce en un máximo de 72 bytes para la contraseña (validación de esquema → 422), evitando errores 500.
- El token es un JWT HS256 firmado con `JWT_SECRET_KEY` (variable de entorno; valor por defecto solo para desarrollo local) y con expiración `ACCESS_TOKEN_EXPIRE_MINUTES` (por defecto 60 minutos). Alternativa descartada: sesiones opacas en BD, porque el pedido exige JWT.
- Dependencias: `get_current_user` extrae el header `Authorization: Bearer <token>`, valida firma/expiración y devuelve el usuario; ante cualquier fallo responde 401 con `{"detail": "..."}` sin revelar si el token existe. `require_client` y `require_vet` depending del rol del usuario: 403 cuando el rol no corresponde.
- El payload del token incluye `sub` (id del usuario), `role` y `exp`; el rol se relee de la BD al resolver el usuario para que un cambio de rol no dependa de un token viejo.

### 5. Contrato de errores

Se usa `HTTPException` de FastAPI con `{"detail": "..."}` en todos los errores Manuales (401, 403, 404, 409) y el 422 nativo de FastAPI para errores de validación del body y del path. Los mensajes son estables y NO revelan información sensible: un login con email inexistente y un login con contraseña incorrecta devuelven el mismo 401.

Orden de validación de `POST /appointments` (fijo, para que los códigos de estado sean deterministas):

1. token ausente/inválido → 401;
2. rol `vet` → 403;
3. `pet_id` inexistente → 404;
4. `pet_id` de otro cliente → 403;
5. `vet_id` inexistente → 404;
6. `start_at` inválido (formato, minuto, día, ventana, pasado) → 422;
7. solapamiento con un turno `scheduled` del mismo veterinario → 409.

### 6. Pruebas

- `pytest` + `httpx` mediante `TestClient` de FastAPI, con la sesión de BD sustituida por una sesión de test (dependencia `get_db` sobreescrita).
- El motor de la suite se toma de `TEST_DATABASE_URL` y, si no está definido, de `DATABASE_URL`, y por defecto usa un SQLite en archivo temporal. Motivo: el Developer debe poder ejecutar `pytest` sin levantar PostgreSQL, pero el compose ejecuta exactamente la misma suite contra PostgreSQL real (`postgres:16-alpine`) mediante el servicio `tests`. Los modelos evitan tipos exclusivos de PostgreSQL para que ambos backends sean equivalentes.
- Cada grupo de tareas de `tasks.md` añade sus propios tests y la suite se ejecuta al final de cada grupo (`pytest -q`).
- El Developer es el único agente que escribe los tests; no se abre una capa de QA.

### 7. Containerización

`Dockerfile` (multi-stage, base `python:3.12-slim`):

1. etapa `builder`: instala `requirements.txt` en un virtualenv;
2. etapa final: copia el código y el virtualenv, crea un usuario no root, `EXPOSE 8000`, `HEALTHCHECK` contra `/health` con `urllib` (sin instalar `curl`) y `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.

El mismo Dockerfile sirve para los tests: `docker compose run --rm tests` sobrescribe el comando con `pytest -q`.

`docker-compose.yml` (raíz) con tres servicios:

- `db`: `postgres:16-alpine`, volumen nombrado `pgdata`, `healthcheck` con `pg_isready`;
- `api`: `build: .`, `depends_on: db` con `condition: service_healthy`, variables `DATABASE_URL`, `JWT_SECRET_KEY`, puerto `8000:8000` publicado, `healthcheck` contra `/health`;
- `tests`: `build: .`, `command: pytest -q`, `depends_on: db` con `condition: service_healthy`.

El comando de verificación de entrega es `docker compose up --build --wait` (Compose v2.20+): construye las imágenes, levanta `db` y `api`, espera a que ambos estén healthy y **termina con código de salida 0**, momento en el cual `GET /health` en el puerto publicado devuelve `200 {"status": "ok"}`. Como alternativa para CI sin `--wait`, `docker compose up --build --abort-on-container-exit --exit-code-from tests` devuelve el código de salida de la suite de tests. Ambos comandos están envueltos en `scripts/verify_stack.sh`, que además ejecuta `docker compose down` al terminar. Motivo: `docker compose up --build` a secas no puede terminar solo porque la API es un servidor de larga duración; `--wait` es la forma soportada de que ese comando termine con éxito tras comprobar la salud de los contenedores.

### 8. Documentación

`README.md` con: requisitos (Python 3.12, Docker), arranque local (uvicorn + Postgres vía docker compose), arranque containerizado (`docker compose up --build`), variables de entorno, descripción de cada endpoint con sus códigos de estado, y ejemplos `curl` copiables para `/health`, `/auth/register`, `/auth/login`, `/vets`, `/pets`, `/appointments` y `/appointments/{id}/cancel`, incluyendo el uso del token en el header `Authorization: Bearer`.

## Risks / Trade-offs

- **Sin versionado de esquema (sin Alembic)** → la primera entrega crea el esquema al arrancar; si el modelo cambia después hay que recrear el volumen. Mitigación: el modelo es pequeño y el cambio de esquema se hace en la misma entrega que introduce el cambio; `docker compose down -v` deja el entorno limpio.
- **Naive UTC en base de datos** → si alguien inserta directamente una fila con otra zona, la comparación falla. Mitigación: toda entrada pasa por el normalizador de `app/schemas/appointment.py` y las pruebas cubren la conversión desde offsets.
- **SQLite en local vs PostgreSQL en el contenedor** → una diferencia de comportamiento podría escaparse en local. Mitigación: el compose ejecuta la misma suite contra PostgreSQL y es la verificación obligatoria del último grupo de tareas.
- **Ventana horaria fija en código** → adding holidays o excepciones de agenda requerirá cambiar el servicio de scheduling. Mitigación: todas las constantes viven en un único módulo, de modo que la extensión no toca routers ni esquemas.
- **Límite de 72 bytes de bcrypt** → contraseñas más largas se rechazan con 422. Mitigación: el mensaje de validación indica el máximo y no se trunca silenciosamente la contraseña.
- **Sin CORS ni rate limiting** → la API queda expuesta solo a la red interna; no es un requisito del pedido. Mitigación: se documenta en el README que la API es de uso interno.
