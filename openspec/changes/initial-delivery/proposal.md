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
