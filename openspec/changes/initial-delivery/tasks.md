# Tasks

> Equipo: el agente **Developer** es el único responsable de la implementación y de escribir los tests de cada grupo (no hay QA ni DevSec en este flujo). Cada grupo entrega su propia implementación, sus propios tests y su sección en el `README.md`; la suite completa se ejecuta al final de cada grupo.

## 1. Project scaffolding and dependencies

- [x] 1.1 Create `/requirements.txt` (fastapi, uvicorn[standard], sqlalchemy>=2.0, psycopg2-binary, pydantic>=2, pydantic-settings, PyJWT, bcrypt) and `/requirements-dev.txt` (pytest, httpx) and verify that `pip install -r requirements.txt -r requirements-dev.txt` completes without errors.
- [x] 1.2 Create `/pyproject.toml` with `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `pythonpath = ["."]`) and verify that `pytest --collect-only` exits with code 0 collecting no tests yet.
- [x] 1.3 Create the package skeleton `/app/__init__.py`, `/app/core/__init__.py`, `/app/core/config.py` (settings `DATABASE_URL`, `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` read from the environment), `/app/db/__init__.py`, `/app/db/base.py`, `/app/db/session.py` (engine, `SessionLocal`, dependency `get_db`) and `/app/db/models.py` (`User`, `Pet`, `Appointment` with the columns of the design table) and verify that `python -c "from app.db.models import User, Pet, Appointment"` succeeds.
- [x] 1.4 Create `/.env.example` and `/.dockerignore` (excluding `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.opencode`, `openspec`) and verify that both files exist at the repository root and that `cat .dockerignore` lists those entries.

## 2. Health endpoint and application wiring

- [x] 2.1 Create `/app/schemas/health.py` (`HealthResponse`), `/app/api/routes/health.py` (`GET /health` answering `200 {"status": "ok"}`) and `/app/main.py` (FastAPI instance, `lifespan` that runs `Base.metadata.create_all`, router registration) and verify that a request to `GET /health` returns HTTP 200 with the body `{"status": "ok"}`.
- [x] 2.2 Create `/tests/conftest.py` (temporary SQLite engine, `get_db` override, `TestClient` fixture and helpers to register accounts and obtain bearer headers) and `/tests/test_health.py` covering the 200 status, the exact body `{"status": "ok"}` and the fact that no token is needed, and verify that `pytest tests/test_health.py` passes.
- [x] 2.3 Add the "Health" section to `/README.md` documenting `GET /health` with its curl example and verify that the documented body matches the assertion of `tests/test_health.py`.

## 3. Registration, login and bearer protection

- [x] 3.1 Create `/app/core/security.py` (bcrypt hashing and verification, JWT HS256 issuing and decoding with `sub`, `role` and `exp`, 401 on any invalid token) and `/app/api/dependencies.py` (`get_current_user` returning 401, `require_client` and `require_vet` returning 403), and verify that a protected route without a token answers 401.
- [x] 3.2 Create `/app/schemas/auth.py` and `/app/api/routes/auth.py` (`POST /auth/register` → `201 {id, email, role}`, duplicate email → 409 including case-insensitive duplicates, password shorter than 8 characters → 422, role other than `client`/`vet` → 422, malformed email → 422; `POST /auth/login` → `200 {access_token, token_type: "bearer"}`, wrong password or unknown email → 401 with the same body) and verify each of those statuses manually against the running app.
- [x] 3.3 Create `/tests/test_auth.py` covering registration as client and as vet, the 201 body without any password field, duplicate email 409, short password 422, invalid role 422, login 200 with a usable token, invalid credentials 401, and 401 for missing, malformed and invalid tokens on `GET /vets`, `POST /pets`, `GET /pets`, `POST /appointments`, `GET /appointments` and `POST /appointments/{id}/cancel`, and verify that `pytest tests/test_auth.py` passes.
- [x] 3.4 Add the "Autenticación" section to `/README.md` with the curl examples for registration and login and the `Authorization: Bearer <token>` usage, and verify that those examples work against a locally running app.

## 4. Veterinarian directory

- [x] 4.1 Create `/app/schemas/user.py` (`VetRead` with only `id` and `email`) and `/app/api/routes/vets.py` (`GET /vets` listing only the accounts with role `vet`) and verify that an authenticated client receives `200` with a JSON array of `{id, email}` objects.
- [x] 4.2 Create `/tests/test_vets.py` covering the array content, the exclusion of client accounts, the absence of any password field, the empty array when no vet exists and the 401 answers for a missing or invalid token, and verify that `pytest tests/test_vets.py` passes.
- [x] 4.3 Add the "Veterinarios" section to `/README.md` with the `GET /vets` curl example, and verify that the example returns the documented list.

## 5. Pets

- [x] 5.1 Create `/app/schemas/pet.py` (`PetCreate` with `name`, `species` restricted to `dog`/`cat`/`other` and `birth_date` as a date not in the future; `PetRead` with `id`, `name`, `species`, `birth_date`, `owner_id`) and `/app/api/routes/pets.py` (`POST /pets` restricted to clients → `201 {id, name, species, birth_date, owner_id}` with `owner_id` = the authenticated client; `GET /pets` returning only the pets owned by the caller, an empty array for a vet) and verify each status manually.
- [x] 5.2 Create `/tests/test_pets.py` covering pet creation and the exact 201 body, `species` `other` accepted, an unsupported species 422, a missing species 422, a future `birth_date` 422, today's `birth_date` accepted, a vet attempting to create a pet 403, the listing containing only the caller's pets, a vet's empty listing and the 401 answers for anonymous calls, and verify that `pytest tests/test_pets.py` passes.
- [x] 5.3 Add the "Mascotas" section to `/README.md` with the curl examples for creating and listing pets, and verify that the examples match the documented responses.

## 6. Appointments

- [x] 6.1 Create `/app/services/scheduling.py` (constants `SLOT_MINUTES = 30`, `OPENING_TIME = 09:00`, `CLOSING_TIME = 18:00`, `LAST_START_TIME = 17:30`, Monday-Saturday working days, plus the start-time validation and the overlap check) and `/app/schemas/appointment.py` (`AppointmentCreate`, `AppointmentRead` normalizing the input to UTC and serializing `start_at`/`end_at` as ISO 8601 UTC with the `Z` suffix), and verify that the slot rules reject a start at 09:15, on a Sunday, at 08:30 and at 18:00 with 422 while accepting 17:30.
- [x] 6.2 Create `/app/api/routes/appointments.py` (`POST /appointments` for clients only, requiring a pet owned by the caller, answering 404 for an unknown pet or vet, 422 for an invalid start, 409 when the vet already has an overlapping `scheduled` appointment and `201 {id, pet_id, vet_id, start_at, end_at, status: "scheduled"}`; `GET /appointments` scoped to the caller's pets or the caller's own agenda; `POST /appointments/{id}/cancel` allowed for the owner of the pet or the booked vet, answering 403 for any other user, 404 for an unknown appointment, 409 for an already cancelled one and 200 with `status: "cancelled"`), and verify each status manually against the running app.
- [x] 6.3 Create `/tests/test_appointments.py` covering a successful booking with `end_at` 30 minutes later and UTC `Z` timestamps, a vet booking 403, a pet owned by another client 403, an unknown pet and an unknown vet 404, the minute and window rules 422 (09:15, 08:30, 18:00, Sunday, Saturday accepted), a past start 422, an offset converted to UTC before validation, a double booking of the same vet 409, the same slot free for another vet 201, the client and vet listings, cancellation by the owner and by the vet, the cancellation of somebody else's appointment 403, cancelling twice 409, rebooking a cancelled slot 201, cancelling an unknown appointment 404 and the anonymous 401 answers, and verify that `pytest tests/test_appointments.py` passes.
- [x] 6.4 Add the "Turnos" section to `/README.md` with the curl examples for booking, listing and cancelling an appointment, including the cancellation of a slot and its rebooking, and verify that the examples match the documented responses.

## 7. Containerization, documentation and delivery verification

- [x] 7.1 Create `/Dockerfile` (multi-stage build over `python:3.12-slim`, non-root user, `EXPOSE 8000`, `HEALTHCHECK` against `/health`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`) and `/docker-compose.yml` at the repository root with the `db` (postgres:16-alpine with `pg_isready` healthcheck and a named volume), `api` (built from the root `Dockerfile`, `depends_on: db` with `condition: service_healthy`, `DATABASE_URL` and `JWT_SECRET_KEY` from the environment, port `8000:8000` published, healthcheck against `/health`) and `tests` (built from the same image, `command: pytest -q`) services, and verify that `docker compose config` exits with code 0 and prints the `db`, `api` and `tests` services.
- [x] 7.2 Create `/scripts/verify_stack.sh` that runs `docker compose up --build --wait` from the repository root, fails when that command does not exit with code 0, checks that `curl -fsS http://localhost:8000/health` answers `200` with `{"status": "ok"}`, runs `docker compose run --rm tests` expecting exit code 0 and always ends with `docker compose down`, and verify that `bash -n /scripts/verify_stack.sh` passes and that the file is executable.
- [x] 7.3 Create `/tests/test_delivery_files.py` asserting that `Dockerfile`, `docker-compose.yml`, `scripts/verify_stack.sh` and `README.md` exist at the repository root, that the compose file declares the `db`, `api` and `tests` services and that the README documents every endpoint of the API, and verify that `pytest tests/test_delivery_files.py` passes.
- [x] 7.4 Run the whole suite with `pytest -q` and verify that it finishes with 0 failures.
- [x] 7.5 Run the final delivery check from the repository root with `docker compose up --build --wait` and verify that the command exits with code 0, that `curl -fsS http://localhost:8000/health` answers `200` with `{"status": "ok"}`, that `docker compose run --rm tests` exits with code 0 running the same suite against PostgreSQL and that `docker compose down` leaves no container of the stack running.
- [x] 7.6 Complete `/README.md` with the "Arranque local", "Arranque con Docker", "Ejecutar los tests" and "Variables de entorno" sections, and verify that every command shown in the README runs exactly as written.

## Notas de ejecución

- Si hay que levantar la API en local para verificar un comportamiento, hacerlo en background guardando su PID con `$!` y detener únicamente ese PID; nunca usar `pkill`, `killall` ni `kill` por nombre o patrón.
- No usar el puerto 8202 para ningún servicio ni verificación; la API publica el puerto 8000.
- La suite local usa SQLite en un archivo temporal; la verificación de entrega usa la misma suite contra PostgreSQL 16 dentro del contenedor.
- El entorno de desarrollo no tiene Docker instalado: el `Dockerfile` y el `docker-compose.yml` se han verificado de forma estática (sintaxis del compose, salud de los servicios, comandos esperados y usuario sin privilegios) y `scripts/verify_stack.sh` ejecuta la comprobación completa, con Docker, en el entorno de entrega. Los ejemplos de `curl` del `README.md` se han comprobado contra la API en ejecución local.
- El servicio `tests` lleva el perfil `test` para que `docker compose up --build --wait` levante solo `db` y `api` y termine con código de salida 0; `docker compose run --rm tests` habilita el perfil al nombrar el servicio.
