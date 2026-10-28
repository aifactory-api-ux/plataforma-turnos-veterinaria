# API Clínica Veterinaria

API REST interna de la clínica veterinaria: registro de cuentas de clientes y
veterinarios, alta y consulta de mascotas, y agenda de turnos de 30 minutos.

El servicio es de uso interno del equipo de la clínica: la API no expone datos
fuera de la red interna y no incluye CORS ni limitación de peticiones.

## Requisitos

- Python 3.12 para el arranque local.
- Docker con Compose v2.20 o superior, para el arranque containerizado y para la
  base de datos PostgreSQL 16 del entorno local.
- `curl` y `python3` para los ejemplos de la línea de órdenes.

## Arranque local

1. Levantar PostgreSQL 16 con el servicio `db` del compose:

   ```bash
   docker compose up -d db
   ```

2. Crear el entorno virtual e instalar las dependencias:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt -r requirements-dev.txt
   ```

3. Copiar la configuración de ejemplo:

   ```bash
   cp .env.example .env
   ```

4. Arrancar la API:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Comprobar que la API responde:

   ```bash
   curl -fsS http://localhost:8000/health
   ```

   ```
   {"status":"ok"}
   ```

La base de datos de desarrollo se detiene con `docker compose stop db`.

## Arranque con Docker

El `Dockerfile` de la raíz construye una imagen con la API y con la suite de
tests. El `docker-compose.yml` de la raíz la levanta junto con PostgreSQL 16:

```bash
docker compose up --build --wait
```

El comando construye las imágenes, levanta `db` y `api`, espera a que ambos
servicios estén en condiciones y termina con código de salida 0. La API queda
publicada en el puerto 8000:

```bash
curl -fsS http://localhost:8000/health
```

Para detener el stack:

```bash
docker compose down
```

Para borrar también el volumen con los datos de PostgreSQL:

```bash
docker compose down -v
```

El servicio `tests` lleva el perfil `test`, de modo que `docker compose up`
levanta únicamente `db` y `api`. La suite se ejecuta de forma explícita, como
se explica en [Ejecutar los tests](#ejecutar-los-tests).

Para inspeccionar la configuración completa del stack, incluido el servicio
`tests`, hay que habilitar el perfil:

```bash
docker compose --profile test config
```

Alternativa para CI, que termina con el código de salida de la propia suite:

```bash
docker compose --profile test up --build --abort-on-container-exit --exit-code-from tests
```

## Ejecutar los tests

La suite se ejecuta con pytest. En local usa un SQLite temporal y no necesita
ninguna infraestructura:

```bash
pytest -q
```

Dentro del contenedor, la misma suite corre contra PostgreSQL 16:

```bash
docker compose run --rm tests
```

Nombrar el servicio en la orden habilita su perfil, de modo que el comando
arranca la base de datos si hace falta y ejecuta la suite una sola vez.

La verificación de entrega levanta el stack, comprueba `/health`, ejecuta la
suite contra PostgreSQL y vuelve a bajar el stack:

```bash
./scripts/verify_stack.sh
```

## Variables de entorno

| Variable | Valor por defecto | Descripción |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://vetclinic:vetclinic@localhost:5432/vetclinic` | URL de conexión a PostgreSQL. |
| `JWT_SECRET_KEY` | `clave-de-desarrollo-no-usar-en-produccion` | Clave con la que se firman los tokens JWT. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Vigencia del token de acceso, en minutos. |
| `POSTGRES_USER` | `vetclinic` | Usuario creado en el servicio `db` del compose. |
| `POSTGRES_PASSWORD` | `vetclinic` | Contraseña del usuario del servicio `db`. |
| `POSTGRES_DB` | `vetclinic` | Base de datos del servicio `db`. |

La API lee las tres primeras variables; las tres últimas configuran el
servicio `db` del compose. El archivo `.env` de la raíz se carga al arrancar la
API y también lo usa Docker Compose para interpolar las variables del compose.
El archivo `.env.example` trae los mismos valores con una clave de firma que
hay que sustituir.

Al trabajar con Docker, `DATABASE_URL` debe apuntar al servicio `db`
(`postgresql+psycopg2://vetclinic:vetclinic@db:5432/vetclinic`), que es el
valor por defecto de `docker-compose.yml`. Si el archivo `.env` de la raíz
define otra `DATABASE_URL`, ese valor se usa también dentro de los
contenedores: ajústalo o quítalo antes de `docker compose up`. Lo mismo ocurre
con `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB`: si los cambias,
cambia también `DATABASE_URL`.

En un despliegue real, `JWT_SECRET_KEY` debe tomar un valor propio y secreto:
el valor por defecto solo sirve para desarrollo.

## Resumen de endpoints

| Método | Ruta | Acceso | Respuesta |
| --- | --- | --- | --- |
| `GET` | `/health` | público | `200 {"status": "ok"}` |
| `POST` | `/auth/register` | público | `201 {id, email, role}` |
| `POST` | `/auth/login` | público | `200 {access_token, token_type}` |
| `GET` | `/vets` | con token | `200 [{id, email}]` |
| `POST` | `/pets` | con token de cliente | `201 {id, name, species, birth_date, owner_id}` |
| `GET` | `/pets` | con token | `200 [{id, name, species, birth_date, owner_id}]` |
| `POST` | `/appointments` | con token de cliente | `201 {id, pet_id, vet_id, start_at, end_at, status}` |
| `GET` | `/appointments` | con token | `200 [{id, pet_id, vet_id, start_at, end_at, status}]` |
| `POST` | `/appointments/{id}/cancel` | con token del dueño o del veterinario | `200 {id, pet_id, vet_id, start_at, end_at, status}` |

Las rutas públicas son `/health`, `/auth/register` y `/auth/login`. Cualquier
otra ruta exige la cabecera `Authorization: Bearer <token>` y responde `401`
cuando falta, está mal formada o lleva un token inválido.

## Autenticación

Las cuentas se registran y se autentican con correo y contraseña. El token
devuelto por el login es un JWT firmado con HS256 que viaja en la cabecera
`Authorization: Bearer <token>`.

### `POST /auth/register`

Es público. El rol debe ser `client` o `vet` y la contraseña debe tener al
menos 8 caracteres. Responde `201` con el identificador, el correo y el rol;
nunca devuelve la contraseña.

```bash
curl -i -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email": "ana@example.com", "password": "secret123", "role": "client"}'
```

Respuesta:

```
HTTP/1.1 201 Created
content-type: application/json

{"id":1,"email":"ana@example.com","role":"client"}
```

Casos de error:

- `409` cuando el correo ya está registrado, también si solo difiere en
  mayúsculas y minúsculas.
- `422` con una contraseña de menos de 8 caracteres, con un rol distinto de
  `client`/`vet` o con un correo mal formado.

### `POST /auth/login`

Es público y responde `200` con el token de acceso. Una contraseña incorrecta y
un correo desconocido devuelven el mismo `401`.

```bash
curl -i -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "ana@example.com", "password": "secret123"}'
```

Respuesta:

```
HTTP/1.1 200 OK
content-type: application/json

{"access_token":"<token>","token_type":"bearer"}
```

Error de credenciales:

```
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Credenciales inválidas."}
```

### Uso del token

Los ejemplos de esta guía usan la variable `TOKEN`, que se obtiene con el
login anterior:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "ana@example.com", "password": "secret123"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

Las rutas de negocio (veterinarios, mascotas y turnos) exigen la cabecera
`Authorization: Bearer <token>`. Sin cabecera, con una cabecera mal formada o
con un token inválido, la respuesta es `401` con el cuerpo
`{"detail": "Credenciales inválidas o ausentes."}`.

```bash
curl -i http://localhost:8000/vets \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -i http://localhost:8000/vets
```

```
HTTP/1.1 401 Unauthorized
content-type: application/json
www-authenticate: Bearer

{"detail":"Credenciales inválidas o ausentes."}
```

La documentación interactiva (`/docs`, `/redoc`) y el esquema OpenAPI
(`/openapi.json`) también son accesibles sin token.

## Health

### `GET /health`

Endpoint público de comprobación de disponibilidad del servicio. No exige
cabecera `Authorization` y responde `200` con el cuerpo `{"status": "ok"}`.

```bash
curl -i http://localhost:8000/health
```

Respuesta:

```
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok"}
```

## Veterinarios

### `GET /vets`

Devuelve el directorio de veterinarios de la clínica: un arreglo JSON con un
objeto por cuenta registrada con el rol `vet`. Cada objeto expone únicamente
`id` y `email`; la contraseña y su hash no salen de la base de datos. La ruta
exige la cabecera `Authorization: Bearer <token>` y la pueden consultar tanto
clientes como veterinarios.

```bash
curl -i http://localhost:8000/vets \
  -H "Authorization: Bearer $TOKEN"
```

Respuesta:

```
HTTP/1.1 200 OK
content-type: application/json

[{"id":2,"email":"dr@example.com"}]
```

Si todavía no hay ninguna cuenta con el rol `vet`, el arreglo llega vacío:

```
HTTP/1.1 200 OK
content-type: application/json

[]
```

Sin cabecera `Authorization` o con un token inválido, la respuesta es `401`:

```
HTTP/1.1 401 Unauthorized
content-type: application/json
www-authenticate: Bearer

{"detail":"Credenciales inválidas o ausentes."}
```

## Mascotas

### `POST /pets`

Es exclusivo de los clientes: la mascota queda a nombre de la cuenta
autenticada y un veterinario recibe `403`. La especie admite `dog`, `cat` u
`other` y la fecha de nacimiento no puede ser posterior al día actual.

```bash
curl -i -X POST http://localhost:8000/pets \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Firulais", "species": "dog", "birth_date": "2020-05-04"}'
```

Respuesta:

```
HTTP/1.1 201 Created
content-type: application/json

{"id":1,"name":"Firulais","species":"dog","birth_date":"2020-05-04","owner_id":1}
```

`owner_id` es el identificador de la cuenta que crea la mascota. El cuerpo de
la respuesta devuelve siempre `id`, `name`, `species`, `birth_date` y
`owner_id`.

Casos de error:

- `403` cuando la cuenta autenticada tiene el rol `vet`.
- `422` con una especie distinta de `dog`/`cat`/`other`, sin especie, sin
  nombre o con una fecha de nacimiento futura.

### `GET /pets`

Devuelve únicamente las mascotas de la cuenta autenticada. Un cliente no ve las
mascotas de otro cliente y un veterinario recibe un arreglo vacío.

```bash
curl -i http://localhost:8000/pets \
  -H "Authorization: Bearer $TOKEN"
```

Respuesta:

```
HTTP/1.1 200 OK
content-type: application/json

[{"id":1,"name":"Firulais","species":"dog","birth_date":"2020-05-04","owner_id":1}]
```

Sin cabecera `Authorization` o con un token inválido, la respuesta es `401`:

```
HTTP/1.1 401 Unauthorized
content-type: application/json
www-authenticate: Bearer

{"detail":"Credenciales inválidas o ausentes."}
```

## Turnos

La agenda ofrece turnos de 30 minutos de lunes a sábado. El inicio cae siempre
en punto o en y media, entre las 09:00 y las 17:30, de modo que ningún turno
termina después de las 18:00. Las horas se piden y se devuelven en UTC con el
sufijo `Z`; una entrada con otro desplazamiento se convierte a su instante UTC
equivalente antes de validarse.

### `POST /appointments`

Es exclusivo de los clientes y solo admite mascotas propias. Responde `201` con
el turno creado.

Con la API en ejecución en el puerto 8000, un token de cliente, la mascota `1` y
el veterinario `2`:

```bash
curl -i -X POST http://localhost:8000/appointments \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"pet_id": 1, "vet_id": 2, "start_at": "2030-03-11T09:00:00Z"}'
```

Respuesta:

```
HTTP/1.1 201 Created
content-type: application/json

{"id":1,"pet_id":1,"vet_id":2,"start_at":"2030-03-11T09:00:00Z","end_at":"2030-03-11T09:30:00Z","status":"scheduled"}
```

El cuerpo devuelve siempre `id`, `pet_id`, `vet_id`, `start_at`, `end_at` y
`status`. `end_at` es `start_at` más 30 minutos.

Casos de error:

- `403` cuando la cuenta autenticada tiene el rol `vet` o cuando la mascota
  pertenece a otra cuenta.
- `404` cuando la mascota o el veterinario no existen.
- `422` cuando el inicio no cumple las reglas de la agenda: 09:15 (no cae en
  punto ni en y media), 08:30 (antes de la apertura), 18:00 (en el cierre),
  un domingo o un instante ya pasado.
- `409` cuando el veterinario ya tiene un turno activo en esa franja.

```
HTTP/1.1 409 Conflict
content-type: application/json

{"detail":"El veterinario ya tiene un turno en ese horario."}
```

```
HTTP/1.1 422 Unprocessable Entity
content-type: application/json

{"detail":"Los turnos comienzan en punto o y media."}
```

Los mensajes de las reglas de la agenda son:

| Inicio rechazado | Mensaje |
| --- | --- |
| 09:15 | `Los turnos comienzan en punto o y media.` |
| 08:30 o 18:00 | `Los turnos se agendan entre las 09:00 y las 17:30 y duran 30 minutos.` |
| domingo | `Los turnos se agendan de lunes a sábado.` |
| un instante ya pasado | `El turno no puede empezar en el pasado.` |

### `GET /appointments`

Devuelve los turnos de las mascotas del cliente o, si la cuenta es de un
veterinario, los turnos que atiende. Cada elemento lleva los mismos campos que
la reserva.

```bash
curl -i http://localhost:8000/appointments \
  -H "Authorization: Bearer $TOKEN"
```

Respuesta:

```
HTTP/1.1 200 OK
content-type: application/json

[{"id":1,"pet_id":1,"vet_id":2,"start_at":"2030-03-11T09:00:00Z","end_at":"2030-03-11T09:30:00Z","status":"scheduled"}]
```

Sin cabecera `Authorization` o con un token inválido, la respuesta es `401`:

```
HTTP/1.1 401 Unauthorized
content-type: application/json
www-authenticate: Bearer

{"detail":"Credenciales inválidas o ausentes."}
```

### `POST /appointments/{id}/cancel`

Libera la franja. Solo pueden cancelar el dueño de la mascota y el veterinario
que atiende el turno; el resto de cuentas recibe `403`.

```bash
curl -i -X POST http://localhost:8000/appointments/1/cancel \
  -H "Authorization: Bearer $TOKEN"
```

Respuesta:

```
HTTP/1.1 200 OK
content-type: application/json

{"id":1,"pet_id":1,"vet_id":2,"start_at":"2030-03-11T09:00:00Z","end_at":"2030-03-11T09:30:00Z","status":"cancelled"}
```

Casos de error:

- `403` cuando el turno es de otra cuenta.
- `404` cuando el turno no existe.
- `409` cuando el turno ya estaba cancelado.

```
HTTP/1.1 409 Conflict
content-type: application/json

{"detail":"El turno ya está cancelado."}
```

Una franja cancelada vuelve a estar libre y se puede reservar de nuevo:

```bash
curl -i -X POST http://localhost:8000/appointments \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"pet_id": 1, "vet_id": 2, "start_at": "2030-03-11T09:00:00Z"}'
```

Respuesta:

```
HTTP/1.1 201 Created
content-type: application/json

{"id":2,"pet_id":1,"vet_id":2,"start_at":"2030-03-11T09:00:00Z","end_at":"2030-03-11T09:30:00Z","status":"scheduled"}
```
