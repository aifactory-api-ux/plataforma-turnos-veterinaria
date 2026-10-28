# Proposal

## Why

La clínica veterinaria no tiene hoy ninguna forma de registrar mascotas ni de agendar turnos con veterinarios: el proceso es manual y no deja trazabilidad. Se necesita una API REST interna (FastAPI + PostgreSQL) que permita a clientes registrar sus mascotas, reservar y cancelar turnos, y a los veterinarios ver su agenda, con reglas de agenda claras (franjas de 30 minutos, lunes a sábado, 09:00–18:00) y sin conflictos de doble reserva.

## What Changes

- Se crea la API REST del backend de la clínica veterinaria, ejecutada con FastAPI sobre PostgreSQL.
- Se agrega `GET /health` que responde `200 {"status": "ok"}` sin exigir autenticación, para verificar disponibilidad del servicio.
- Se agrega el registro `POST /auth/register {email, password, role}` con `role` "client" o "vet", respuestas `201 {id, email, role}`, `409` para email duplicado y `422` para password de menos de 8 caracteres o role inválido.
- Se agrega el login `POST /auth/login {email, password}` que responde `200 {access_token, token_type: "bearer"}` con JWT, y `401` ante credenciales incorrectas.
- Se protege todo endpoint distinto de `/health`, `/auth/register` y `/auth/login` con `Authorization: Bearer <token>`; la ausencia de token o un token inválido producen `401`.
- Se agrega `GET /vets` que lista los veterinarios como `[{id, email}]`.
- Se agrega `POST /pets {name, species, birth_date}` exclusivo de clientes (`403` para veterinarios), con `species` "dog", "cat" u "other" (otro valor → `422`), `birth_date` no futura (`422`), respondiendo `201 {id, name, species, birth_date, owner_id}`; `GET /pets` devuelve únicamente las mascotas del cliente autenticado.
- Se agrega `POST /appointments {pet_id, vet_id, start_at}` exclusivo de clientes y solo sobre mascotas propias (`403` si la mascota es ajena, `404` si la mascota o el veterinario no existen), con turnos de 30 minutos que arrancan en punto o y media, de lunes a sábado entre 09:00 y 18:00 (último inicio 17:30); fuera de horario, con minutos distintos de 00/30 o con fecha pasada responde `422`, y responde `409` si el veterinario ya tiene un turno activo en ese horario. Responde `201 {id, pet_id, vet_id, start_at, end_at, status: "scheduled"}`.
- Se agrega `GET /appointments` donde el cliente ve los turnos de sus mascotas y el veterinario ve los suyos.
- Se agrega `POST /appointments/{id}/cancel` que sólo permite cancelar al cliente dueño de la mascota o al veterinario del turno (`403` para otros usuarios), devuelve el turno con `status: "cancelled"`, responde `409` al cancelar un turno ya cancelado y libera el horario para volver a agendar.
- Se entrega la plataforma containerizada: `Dockerfile` en la raíz y `docker-compose.yml` en la raíz que construyen y levantan la API con PostgreSQL, con una tarea final que verifica que `docker compose up --build` termina con código de salida 0.
- Se entrega una suite de pruebas automatizadas con pytest y un `README.md` con instrucciones de arranque y ejemplos con curl.

## Capabilities

### New Capabilities
- `service-health`: verificación de disponibilidad del servicio vía `GET /health`.
- `user-auth`: registro, login con JWT y aplicación del encabezado `Authorization: Bearer` en los endpoints protegidos.
- `vet-directory`: consulta del directorio de veterinarios disponibles para agendar.
- `pet-management`: alta y consulta de las mascotas registradas por un cliente.
- `appointment-scheduling`: creación, consulta y cancelación de turnos de 30 minutos con las reglas de agenda y de autorización.
- `delivery-tooling`: empaquetado y flujo de trabajo del equipo: `Dockerfile` y `docker-compose.yml` en la raíz del repositorio, suite de pruebas con pytest y `README.md` con arranque y ejemplos con curl.

### Modified Capabilities
Ninguna. El proyecto no tiene especificaciones previos (`openspec list --specs` no reporta ninguna).

## Impact

- **Código nuevo**: backend FastAPI con modelos, esquemas y rutas (`app/`), configuración por variables de entorno (`app/core/config.py`), capa de datos (`app/db/`), autenticación (`app/api/` + `app/core/security.py`) y pruebas (`tests/`).
- **Dependencias nuevas**: FastAPI, Uvicorn, SQLAlchemy 2.x, driver PostgreSQL, PyJWT, bcrypt, Pydantic v2, pytest y httpx para las pruebas.
- **Persistencia**: base de datos PostgreSQL 16 con tablas `users`, `pets` y `appointments` creadas al iniciar la aplicación.
- **Infraestructura**: `Dockerfile` multi-stage en la raíz y `docker-compose.yml` en la raíz con servicios `db` (PostgreSQL) y `api` (FastAPI), más un servicio `tests` que corre la suite dentro del contenedor.
- **Documentación**: `README.md` con pasos de arranque (local y con Docker) y ejemplos con curl.
- **Fuera de alcance**: multi-clínica o multi-tenant, pagos, notificaciones por email/SMS, panel web o frontend, OAuth/SSO, verificación de email, recuperación de contraseña,roles de administrador, reportes, y reglas adicionales de disponibilidad (por ejemplo, impedir dos turnos simultáneos para una misma mascota) que el pedido original no define.
- **Equipo**: la entrega la realiza únicamente el agente Developer, que también escribe las pruebas; no hay QA ni DevSec en el flujo.


<!-- specs/appointment-scheduling/spec.md -->
# Spec Delta

## Purpose

Define how clients book, review and cancel 30-minute veterinary appointments, including the working-window rules, the double-booking protection and the per-role visibility of the agenda.

## ADDED Requirements

### Requirement: Clients book an appointment for their own pet
The API SHALL expose `POST /appointments` accepting `pet_id`, `vet_id` and `start_at`, SHALL create a 30-minute appointment, and SHALL answer HTTP 201 with the JSON body `{"id": ..., "pet_id": ..., "vet_id": ..., "start_at": ..., "end_at": ..., "status": "scheduled"}` where `end_at` is `start_at` plus 30 minutes.

#### Scenario: Client books an appointment
- **WHEN** an authenticated client who owns the pet `7` posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T09:00:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 201 and a JSON body holding the new `id`, the `pet_id` `7`, the `vet_id` `3`, the `start_at` `2025-03-10T09:00:00Z`, the `end_at` `2025-03-10T09:30:00Z` and the `status` `scheduled`

#### Scenario: Times are serialized in UTC ISO 8601
- **WHEN** a client inspects `start_at` and `end_at` in the body of a created appointment
- **THEN** both values are ISO 8601 timestamps in UTC expressed with the `Z` suffix

### Requirement: Only clients can book appointments
The API SHALL answer HTTP 403 when an authenticated account whose role is `vet` calls `POST /appointments`, and SHALL NOT create any appointment.

#### Scenario: Vet attempts to book an appointment
- **WHEN** an authenticated vet posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T09:00:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 403 and no appointment is created

### Requirement: Appointments can only reference pets owned by the caller
The API SHALL answer HTTP 403 when the client books an appointment for a pet owned by another account, and SHALL NOT create the appointment.

#### Scenario: Booking a pet owned by another client
- **WHEN** the client `ana@example.com` books `{"pet_id": 9, "vet_id": 3, "start_at": "2025-03-10T09:00:00Z"}` and the pet `9` belongs to `bruno@example.com`
- **THEN** the API responds with HTTP 403 and no appointment is created

### Requirement: Unknown pets and vets are reported as not found
The API SHALL answer HTTP 404 when `POST /appointments` references a `pet_id` that does not exist or a `vet_id` that does not exist, and SHALL NOT create the appointment.

#### Scenario: Pet does not exist
- **WHEN** an authenticated client posts `{"pet_id": 999999, "vet_id": 3, "start_at": "2025-03-10T09:00:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 404 and no appointment is created

#### Scenario: Vet does not exist
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 999999, "start_at": "2025-03-10T09:00:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 404 and no appointment is created

### Requirement: Appointments start on the half-hour grid
The API SHALL answer HTTP 422 when the UTC minute of `start_at` is neither `00` nor `30`, and SHALL NOT create the appointment.

#### Scenario: Start time off the grid
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T09:15:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 422 and no appointment is created

### Requirement: Appointments fall inside the working window
The API SHALL only accept `start_at` values on a Monday, Tuesday, Wednesday, Thursday, Friday or Saturday, between 09:00 and 18:00 UTC, with the last allowed start at 17:30 UTC, and SHALL answer HTTP 422 for any other value.

#### Scenario: Start before the working window
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T08:30:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 422 and no appointment is created

#### Scenario: Start after the last allowed slot
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T18:00:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 422 and no appointment is created

#### Scenario: Last allowed start of the day is accepted
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T17:30:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 201 and the `end_at` `2025-03-10T18:00:00Z`

#### Scenario: Sunday is outside the working days
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-09T09:00:00Z"}` to `/appointments`, and that date is a Sunday
- **THEN** the API responds with HTTP 422 and no appointment is created

#### Scenario: Saturday is a working day
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-08T09:00:00Z"}` to `/appointments`, and that date is a Saturday
- **THEN** the API responds with HTTP 201 and the `status` `scheduled`

### Requirement: Appointments cannot start in the past
The API SHALL answer HTTP 422 when `start_at` is earlier than the current moment, and SHALL NOT create the appointment.

#### Scenario: Start time already elapsed
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2000-01-03T09:00:00Z"}` to `/appointments`
- **THEN** the API responds with HTTP 422 and no appointment is created

### Requirement: Start times are interpreted in UTC
The API SHALL interpret a `start_at` without a UTC offset as a UTC instant, SHALL convert a `start_at` carrying a non-zero offset to the equivalent UTC instant, and SHALL apply every scheduling rule to that UTC instant.

#### Scenario: Offset is converted to UTC before validating
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T11:00:00+02:00"}` to `/appointments`
- **THEN** the API treats the start as `2025-03-10T09:00:00Z`, responds with HTTP 201 and returns the `start_at` `2025-03-10T09:00:00Z`

#### Scenario: Offset that falls outside the working window
- **WHEN** an authenticated client posts `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T08:00:00+02:00"}` to `/appointments`
- **THEN** the API treats the start as `2025-03-10T06:00:00Z` and responds with HTTP 422

### Requirement: A vet cannot have two active appointments in the same slot
The API SHALL answer HTTP 409 when the requested veterinarian already has an appointment with status `scheduled` that overlaps the requested slot, and SHALL NOT create the appointment.

#### Scenario: Vet is already booked in that slot
- **WHEN** the vet `3` already has an appointment `scheduled` from `2025-03-10T09:00:00Z` to `2025-03-10T09:30:00Z` and a client books `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T09:00:00Z"}`
- **THEN** the API responds with HTTP 409 and no second appointment is created for that slot

#### Scenario: The same slot is free for another vet
- **WHEN** the vet `3` has an appointment `scheduled` from `2025-03-10T09:00:00Z` to `2025-03-10T09:30:00Z` and a client books `{"pet_id": 7, "vet_id": 4, "start_at": "2025-03-10T09:00:00Z"}`
- **THEN** the API responds with HTTP 201 and creates the appointment for the vet `4`

### Requirement: The agenda lists the appointments relevant to the caller
The API SHALL expose `GET /appointments` and SHALL answer HTTP 200 with a JSON array containing, for a client, the appointments of the pets the client owns and, for a vet, the appointments where the caller is the veterinarian.

#### Scenario: Client sees the appointments of their pets
- **WHEN** the client `ana@example.com` owns the pets `7` and `8` and calls `GET /appointments`
- **THEN** the JSON array holds the appointments whose `pet_id` is `7` or `8` and no appointment of another client

#### Scenario: Vet sees their own agenda
- **WHEN** the vet `3` calls `GET /appointments`
- **THEN** the JSON array holds only the appointments whose `vet_id` is `3`

#### Scenario: Each element exposes the appointment fields
- **WHEN** a client inspects an element of the array returned by `GET /appointments`
- **THEN** the element contains the keys `id`, `pet_id`, `vet_id`, `start_at`, `end_at` and `status`

### Requirement: The pet owner or the appointed vet can cancel an appointment
The API SHALL expose `POST /appointments/{id}/cancel`, SHALL accept the request when the caller is the client who owns the pet of the appointment or the vet booked in it, and SHALL answer HTTP 200 with the JSON body of that appointment whose `status` is `cancelled`.

#### Scenario: Owner cancels their own appointment
- **WHEN** the client who owns the pet of the appointment `12` calls `POST /appointments/12/cancel`
- **THEN** the API responds with HTTP 200 and the JSON body of the appointment `12` with the `status` `cancelled`

#### Scenario: The appointed vet cancels the appointment
- **WHEN** the vet booked in the appointment `12` calls `POST /appointments/12/cancel`
- **THEN** the API responds with HTTP 200 and the JSON body of the appointment `12` with the `status` `cancelled`

#### Scenario: Other fields of the appointment survive the cancellation
- **WHEN** an authorized caller cancels the appointment `12`
- **THEN** the returned `id`, `pet_id`, `vet_id`, `start_at` and `end_at` are the ones of the original appointment and only the `status` changes to `cancelled`

### Requirement: Cancelling an appointment of another account is forbidden
The API SHALL answer HTTP 403 when a caller that is neither the owner of the pet nor the vet of the appointment calls `POST /appointments/{id}/cancel`, and SHALL NOT change the appointment status.

#### Scenario: Another client tries to cancel the appointment
- **WHEN** the client `bruno@example.com` calls `POST /appointments/12/cancel` and the appointment `12` belongs to the pets of `ana@example.com`
- **THEN** the API responds with HTTP 403 and the appointment `12` keeps the status `scheduled`

### Requirement: Cancelling twice is rejected
The API SHALL answer HTTP 409 when `POST /appointments/{id}/cancel` is called for an appointment whose status is already `cancelled`, and SHALL keep the status `cancelled`.

#### Scenario: Cancelling an already cancelled appointment
- **WHEN** the owner of the pet of the appointment `12` calls `POST /appointments/12/cancel` twice
- **THEN** the first call responds with HTTP 200 and the `status` `cancelled`, and the second call responds with HTTP 409

### Requirement: A cancelled slot can be booked again
The API SHALL allow a new appointment for a slot whose previous appointment was cancelled, and SHALL answer HTTP 201 for it.

#### Scenario: Rebooking a cancelled slot
- **WHEN** the vet `3` had the appointment `12` from `2025-03-10T09:00:00Z` to `2025-03-10T09:30:00Z` and it was cancelled, and a client books `{"pet_id": 7, "vet_id": 3, "start_at": "2025-03-10T09:00:00Z"}`
- **THEN** the API responds with HTTP 201 and creates a new appointment with the `status` `scheduled` for that slot

### Requirement: Cancelling an unknown appointment is reported as not found
The API SHALL answer HTTP 404 when `POST /appointments/{id}/cancel` references an appointment that does not exist.

#### Scenario: Cancelling a missing appointment
- **WHEN** an authenticated client calls `POST /appointments/999999/cancel`
- **THEN** the API responds with HTTP 404

### Requirement: Appointment endpoints require authentication
The API SHALL answer HTTP 401 to `POST /appointments`, `GET /appointments` and `POST /appointments/{id}/cancel` when the `Authorization: Bearer` header is absent or carries an invalid token.

#### Scenario: Anonymous booking is rejected
- **WHEN** a client sends `POST /appointments` without an `Authorization` header
- **THEN** the API responds with HTTP 401 and no appointment is created

#### Scenario: Anonymous agenda access is rejected
- **WHEN** a client sends `GET /appointments` without an `Authorization` header
- **THEN** the API responds with HTTP 401

#### Scenario: Anonymous cancellation is rejected
- **WHEN** a client sends `POST /appointments/12/cancel` without an `Authorization` header
- **THEN** the API responds with HTTP 401 and the appointment keeps its status


<!-- specs/delivery-tooling/spec.md -->
# Spec Delta

## Purpose

Define how the veterinary clinic backend is packaged, started and verified as a containerized stack, and what the repository must ship so the internal team can run it and call it.

## ADDED Requirements

### Requirement: The repository ships a root Dockerfile for the API
The repository SHALL contain a file named `Dockerfile` at its root that installs the application and its runtime dependencies into an image, exposes the API port and starts the API server. The same image SHALL be able to run the test suite.

#### Scenario: Build the image from the repository root
- **WHEN** the team runs `docker build -t vetclinic-api .` from the repository root
- **THEN** the command exits with code 0 and produces an image that contains the application code and its dependencies

#### Scenario: Run the API from the image
- **WHEN** the team starts the built image with the API port published and requests `GET /health` on that port
- **THEN** the API answers HTTP 200 with the JSON body `{"status": "ok"}`

#### Scenario: Run the test suite from the image
- **WHEN** the team runs the test suite inside the built image
- **THEN** the pytest run completes and the command exits with code 0 when every test passes

### Requirement: The repository ships a root docker-compose.yml for the API and PostgreSQL
The repository SHALL contain a file named `docker-compose.yml` at its root that defines a PostgreSQL service and an API service built from the root `Dockerfile`, connects the API service to the database service and publishes the API port on the host. The file SHALL also define a service that runs the test suite against the same PostgreSQL service.

#### Scenario: The compose file is valid
- **WHEN** the team runs `docker compose config` from the repository root
- **THEN** the command exits with code 0 and prints the resolved services `db`, `api` and `tests`

#### Scenario: The API service is wired to PostgreSQL
- **WHEN** the team inspects the resolved compose configuration
- **THEN** the `api` service is built from the root `Dockerfile`, declares a dependency on the `db` service and receives the database connection settings through the environment

### Requirement: The stack starts from a clean build and exits successfully
Running `docker compose up --build` from the repository root SHALL build the images, start PostgreSQL and the API, and the command SHALL exit with code 0 while the published API answers `GET /health` with HTTP 200 and the JSON body `{"status": "ok"}`.

#### Scenario: Build and start the whole stack
- **WHEN** the team runs `docker compose up --build` from the repository root
- **THEN** the images are rebuilt, the `db` and `api` services start, the command exits with code 0 and `GET /health` on the published port returns HTTP 200 with `{"status": "ok"}`

#### Scenario: The stack initializes its schema on an empty database
- **WHEN** the team starts the stack against an empty PostgreSQL volume
- **THEN** the API creates the `users`, `pets` and `appointments` tables and the health check answers HTTP 200

#### Scenario: The stack can be stopped
- **WHEN** the team runs `docker compose down` after the stack has been started
- **THEN** the command exits with code 0 and the containers of the stack are stopped and removed

### Requirement: The containerized test suite runs against PostgreSQL
The compose stack SHALL offer a way to execute the pytest suite inside the container image against the PostgreSQL service, and the exit code of that command SHALL equal the exit code of the test run.

#### Scenario: Run the suite in the container
- **WHEN** the team runs `docker compose run --rm tests` from the repository root
- **THEN** the command exits with code 0 and the pytest output reports that every test passed

#### Scenario: A failing test fails the command
- **WHEN** the team runs `docker compose run --rm tests` and one test fails
- **THEN** the command exits with a non-zero code

### Requirement: The repository ships an automated pytest suite
The repository SHALL contain a pytest suite that exercises the documented behavior of the API (health, registration, login, bearer protection, vets, pets, appointments and cancellation) and that SHALL be runnable with the `pytest` command in a prepared environment.

#### Scenario: The suite passes on a clean checkout
- **WHEN** the developer runs `pytest` in an environment with the dependencies installed and a database reachable
- **THEN** the run reports that every test passed and the command exits with code 0

#### Scenario: Each documented behavior is covered
- **WHEN** the developer lists the collected tests
- **THEN** the suite contains at least one test for each documented endpoint, status code and rule of the API

### Requirement: The repository ships a README with startup steps and curl examples
The repository SHALL contain a `README.md` explaining how to start the API locally and with Docker, describing the endpoints and their status codes, and giving a curl example for the health check, the registration, the login, the vet directory, the pet registration and listing, the appointment booking, listing and cancellation.

#### Scenario: The team can start the project from the README
- **WHEN** a developer reads `README.md` and follows the documented commands
- **THEN** the commands start the API with PostgreSQL and the documented health check succeeds

#### Scenario: The curl examples match the API contract
- **WHEN** the team runs the curl examples of `README.md` against a running API using the tokens they obtain from the documented login example
- **THEN** each example receives the documented status code and response body


<!-- specs/pet-management/spec.md -->
# Spec Delta

## Purpose

Define how clients register the pets they own and how the API returns only the pets of the authenticated client, keeping ownership explicit for appointment booking.

## ADDED Requirements

### Requirement: Clients register their pets
The API SHALL expose `POST /pets` accepting `name`, `species` and `birth_date`, SHALL assign the new pet to the authenticated client as its owner, and SHALL answer HTTP 201 with the JSON body `{"id": ..., "name": ..., "species": ..., "birth_date": ..., "owner_id": ...}`.

#### Scenario: Client creates a pet
- **WHEN** an authenticated client posts `{"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"}` to `/pets`
- **THEN** the API responds with HTTP 201 and a JSON body holding the new `id`, the `name` `Firulais`, the `species` `dog`, the `birth_date` `2020-05-04` and the `owner_id` of the authenticated client

#### Scenario: The species other is accepted
- **WHEN** an authenticated client posts `{"name": "Rana", "species": "other", "birth_date": "2021-01-15"}` to `/pets`
- **THEN** the API responds with HTTP 201 and the `species` `other` in the JSON body

#### Scenario: The response echoes the submitted values
- **WHEN** an authenticated client creates a pet
- **THEN** the JSON body of the HTTP 201 response contains the same `name`, `species` and `birth_date` that were submitted

### Requirement: Only clients can register pets
The API SHALL answer HTTP 403 when an authenticated account whose role is `vet` calls `POST /pets`, and SHALL NOT create any pet.

#### Scenario: Vet attempts to create a pet
- **WHEN** an authenticated vet posts `{"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"}` to `/pets`
- **THEN** the API responds with HTTP 403 and no pet is created

### Requirement: Species is restricted to dog, cat and other
The API SHALL answer HTTP 422 when `species` is any value other than `dog`, `cat` or `other`, and SHALL NOT create the pet.

#### Scenario: Unsupported species value
- **WHEN** an authenticated client posts `{"name": "Firulais", "species": "hamster", "birth_date": "2020-05-04"}` to `/pets`
- **THEN** the API responds with HTTP 422 and no pet is created

#### Scenario: Missing species
- **WHEN** an authenticated client posts `{"name": "Firulais", "birth_date": "2020-05-04"}` to `/pets`
- **THEN** the API responds with HTTP 422 and no pet is created

### Requirement: Birth date cannot be in the future
The API SHALL answer HTTP 422 when `birth_date` is later than the current date and SHALL NOT create the pet.

#### Scenario: Birth date in the future
- **WHEN** an authenticated client posts `{"name": "Firulais", "species": "dog", "birth_date": "2999-01-01"}` to `/pets`
- **THEN** the API responds with HTTP 422 and no pet is created

#### Scenario: Birth date today is accepted
- **WHEN** an authenticated client posts a pet whose `birth_date` is the current date
- **THEN** the API responds with HTTP 201 and stores that `birth_date`

### Requirement: Pet listing returns only the caller's pets
The API SHALL expose `GET /pets` and SHALL answer HTTP 200 with a JSON array containing only the pets whose `owner_id` is the authenticated account.

#### Scenario: Client lists their own pets
- **WHEN** a client owns the pets `Firulais` and `Rana` and calls `GET /pets`
- **THEN** the API responds with HTTP 200 and the JSON array holds exactly those two pets with their `id`, `name`, `species`, `birth_date` and `owner_id`

#### Scenario: Another client's pets are not visible
- **WHEN** the client `ana@example.com` owns the pet `Firulais` and the client `bruno@example.com` calls `GET /pets`
- **THEN** the JSON array returned to `bruno@example.com` does not contain `Firulais` nor the `id` of that pet

#### Scenario: A vet owns no pets
- **WHEN** an authenticated vet calls `GET /pets`
- **THEN** the API responds with HTTP 200 and the JSON array `[]`

### Requirement: Pet endpoints require authentication
The API SHALL answer HTTP 401 to `POST /pets` and `GET /pets` when the `Authorization: Bearer` header is absent or carries an invalid token.

#### Scenario: Anonymous pet creation is rejected
- **WHEN** a client sends `POST /pets` without an `Authorization` header
- **THEN** the API responds with HTTP 401 and no pet is created

#### Scenario: Anonymous pet listing is rejected
- **WHEN** a client sends `GET /pets` without an `Authorization` header
- **THEN** the API responds with HTTP 401


<!-- specs/service-health/spec.md -->
# Spec Delta

## Purpose

Define the public liveness probe of the veterinary clinic API so the internal team and the container stack can confirm that the service is up and serving requests.

## ADDED Requirements

### Requirement: Health endpoint reports service status
The API SHALL expose `GET /health` as a public endpoint and SHALL answer HTTP 200 with the JSON body `{"status": "ok"}`.

#### Scenario: Unauthenticated health check succeeds
- **WHEN** a client sends `GET /health` without any `Authorization` header
- **THEN** the API responds with HTTP 200 and the JSON body `{"status": "ok"}`

#### Scenario: Health check body has exactly one key
- **WHEN** a client inspects the JSON body returned by `GET /health`
- **THEN** the body is exactly `{"status": "ok"}` and no other field is present

### Requirement: Health endpoint is exempt from bearer authentication
The API SHALL NOT require the `Authorization` header on `GET /health` and SHALL NOT answer 401 for that path, even when the supplied token is missing, malformed or invalid.

#### Scenario: Invalid token on the health endpoint does not fail
- **WHEN** a client sends `GET /health` with the header `Authorization: Bearer not-a-valid-token`
- **THEN** the API responds with HTTP 200 and the JSON body `{"status": "ok"}`


<!-- specs/user-auth/spec.md -->
# Spec Delta

## Purpose

Define how accounts are created, how credentials are exchanged for a JWT bearer token, and how that token gates every non-public endpoint of the veterinary clinic API.

## ADDED Requirements

### Requirement: Accounts are registered with a client or vet role
The API SHALL expose `POST /auth/register` accepting `email`, `password` and `role`, SHALL accept only the roles `client` and `vet`, and SHALL answer HTTP 201 with the JSON body `{"id": ..., "email": ..., "role": ...}` of the created account.

#### Scenario: Register a client account
- **WHEN** an unauthenticated client posts `{"email": "ana@example.com", "password": "secret123", "role": "client"}` to `/auth/register`
- **THEN** the API responds with HTTP 201 and a JSON body containing the new account `id`, the `email` `ana@example.com` and the `role` `client`

#### Scenario: Register a vet account
- **WHEN** an unauthenticated client posts `{"email": "dr@example.com", "password": "secret123", "role": "vet"}` to `/auth/register`
- **THEN** the API responds with HTTP 201 and a JSON body containing the new account `id`, the `email` `dr@example.com` and the `role` `vet`

#### Scenario: Registration response never exposes credentials
- **WHEN** a client registers an account successfully
- **THEN** the JSON body of the HTTP 201 response contains only `id`, `email` and `role`, with no `password` and no password hash

### Requirement: Passwords shorter than eight characters are rejected
The API SHALL reject a registration whose `password` has fewer than 8 characters with HTTP 422 and SHALL NOT create the account.

#### Scenario: Password below the minimum length
- **WHEN** an unauthenticated client posts `{"email": "ana@example.com", "password": "short7c", "role": "client"}` to `/auth/register`
- **THEN** the API responds with HTTP 422 and no account is created for that email

### Requirement: Roles outside client and vet are rejected
The API SHALL reject a registration whose `role` is neither `client` nor `vet` with HTTP 422 and SHALL NOT create the account.

#### Scenario: Unknown role value
- **WHEN** an unauthenticated client posts `{"email": "ana@example.com", "password": "secret123", "role": "admin"}` to `/auth/register`
- **THEN** the API responds with HTTP 422 and no account is created for that email

#### Scenario: Malformed email is rejected
- **WHEN** an unauthenticated client posts `{"email": "not-an-email", "password": "secret123", "role": "client"}` to `/auth/register`
- **THEN** the API responds with HTTP 422 and no account is created

### Requirement: Email addresses are unique per account
The API SHALL reject a registration whose email is already registered with HTTP 409 and SHALL NOT create a second account, comparing emails case-insensitively.

#### Scenario: Duplicate email registration
- **WHEN** an account with email `ana@example.com` already exists and a client posts `{"email": "ana@example.com", "password": "secret123", "role": "client"}` to `/auth/register`
- **THEN** the API responds with HTTP 409 and only one account exists for that email

#### Scenario: Duplicate email differing only in case
- **WHEN** an account with email `ana@example.com` already exists and a client posts `{"email": "ANA@example.com", "password": "secret123", "role": "client"}` to `/auth/register`
- **THEN** the API responds with HTTP 409 and no second account is created

### Requirement: Login returns a JWT bearer token
The API SHALL expose `POST /auth/login` accepting `email` and `password` and SHALL answer HTTP 200 with the JSON body `{"access_token": ..., "token_type": "bearer"}`, where `access_token` is a JSON Web Token identifying the account and its role.

#### Scenario: Login with valid credentials
- **WHEN** a client posts `{"email": "ana@example.com", "password": "secret123"}` to `/auth/login` for an existing account
- **THEN** the API responds with HTTP 200, `token_type` equal to `bearer` and an `access_token` that is a non-empty JSON Web Token

#### Scenario: Login accepts the email in a different case
- **WHEN** a client posts `{"email": "ANA@example.com", "password": "secret123"}` to `/auth/login` for an existing account registered as `ana@example.com`
- **THEN** the API responds with HTTP 200 and a valid `access_token`

### Requirement: Login rejects invalid credentials
The API SHALL answer HTTP 401 when `POST /auth/login` receives a wrong password or an email that is not registered, and SHALL NOT reveal which of the two cases occurred.

#### Scenario: Wrong password
- **WHEN** a client posts `{"email": "ana@example.com", "password": "wrong-password"}` to `/auth/login`
- **THEN** the API responds with HTTP 401 and no `access_token` is issued

#### Scenario: Unknown email
- **WHEN** a client posts `{"email": "ghost@example.com", "password": "secret123"}` to `/auth/login`
- **THEN** the API responds with HTTP 401 and no `access_token` is issued

### Requirement: Protected endpoints require a bearer token
Every endpoint except `GET /health`, `POST /auth/register` and `POST /auth/login` SHALL require an `Authorization: Bearer <token>` header and SHALL answer HTTP 401 when the header is absent, malformed, or carries a token that is invalid, expired, or signed with an unknown key. The protected paths are `GET /vets`, `POST /pets`, `GET /pets`, `POST /appointments`, `GET /appointments` and `POST /appointments/{id}/cancel`.

#### Scenario: Missing authorization header
- **WHEN** a client sends `GET /pets` without an `Authorization` header
- **THEN** the API responds with HTTP 401

#### Scenario: Invalid token on a protected endpoint
- **WHEN** a client sends `POST /pets` with the header `Authorization: Bearer not-a-valid-token`
- **THEN** the API responds with HTTP 401 and no pet is created

#### Scenario: Token signed with an unknown key
- **WHEN** a client sends `GET /vets` with a structurally valid JWT signed with an unknown secret key
- **THEN** the API responds with HTTP 401

#### Scenario: Malformed authorization header
- **WHEN** a client sends `GET /vets` with the header `Authorization: Basic dXNlcjpwYXNz`
- **THEN** the API responds with HTTP 401

### Requirement: Bearer tokens carry the account identity and role
The API SHALL derive the acting account and its role (`client` or `vet`) from the verified bearer token of every protected request, so that role-restricted resources can be enforced per caller.

#### Scenario: Token identifies the calling account
- **WHEN** a client logs in and calls `GET /pets` with the returned token
- **THEN** the API acts on behalf of the account that owns that token and not on behalf of any other account

#### Scenario: Role is taken from the token
- **WHEN** a user registered with the role `vet` calls `POST /pets` with their own valid token
- **THEN** the API treats the caller as a veterinarian and rejects the request with HTTP 403


<!-- specs/vet-directory/spec.md -->
# Spec Delta

## Purpose

Define the veterinarian directory that authenticated clients consult to know which veterinarian identifiers are available when booking an appointment.

## ADDED Requirements

### Requirement: The veterinarian directory lists every vet
The API SHALL expose `GET /vets` for authenticated callers and SHALL answer HTTP 200 with a JSON array containing one object per account registered with the role `vet`, each object holding exactly the fields `id` and `email`.

#### Scenario: Authenticated client lists the veterinarians
- **WHEN** a registered client sends `GET /vets` with a valid bearer token
- **THEN** the API responds with HTTP 200 and a JSON array whose elements each contain the fields `id` and `email`

#### Scenario: The directory only contains vets
- **WHEN** the accounts `dr@example.com` (role `vet`) and `ana@example.com` (role `client`) exist and a client calls `GET /vets`
- **THEN** the JSON array contains the account `dr@example.com` and does not contain the account `ana@example.com`

#### Scenario: Each element exposes only id and email
- **WHEN** a client inspects an element of the array returned by `GET /vets`
- **THEN** the element contains the keys `id` and `email` and no `password`, `password_hash`, `role` or other field

#### Scenario: Empty directory when no vet is registered
- **WHEN** only accounts with the role `client` exist and an authenticated client calls `GET /vets`
- **THEN** the API responds with HTTP 200 and the JSON array `[]`

### Requirement: The veterinarian directory requires authentication
The API SHALL answer HTTP 401 to `GET /vets` when the `Authorization: Bearer` header is absent or carries an invalid token.

#### Scenario: Anonymous access to the directory is rejected
- **WHEN** a client sends `GET /vets` without an `Authorization` header
- **THEN** the API responds with HTTP 401

#### Scenario: Invalid token on the directory is rejected
- **WHEN** a client sends `GET /vets` with the header `Authorization: Bearer not-a-valid-token`
- **THEN** the API responds with HTTP 401


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
