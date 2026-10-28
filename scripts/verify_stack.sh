#!/usr/bin/env bash
#
# Verificación de entrega del stack de la clínica veterinaria.
#
# Pasos:
#   1. Construir las imágenes y levantar el stack con `docker compose up
#      --build --wait`, que termina con código de salida 0 cuando `db` y `api`
#      están en condiciones.
#   2. Comprobar que `GET /health` responde 200 con el cuerpo {"status":"ok"}.
#   3. Ejecutar la suite de pytest contra PostgreSQL con `docker compose run
#      --rm tests`, que devuelve el código de salida de la propia suite.
#   4. Terminar siempre con `docker compose down`, pase lo que pase.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HEALTH_URL="http://localhost:8000/health"
EXPECTED_STATUS="200"
EXPECTED_BODY='{"status":"ok"}'

cd "${REPO_ROOT}"

stop_stack() {
  echo "==> Bajando el stack (docker compose down)"
  docker compose down
}

trap stop_stack EXIT

echo "==> Levantando el stack (docker compose up --build --wait)"
docker compose up --build --wait

echo "==> Comprobando ${HEALTH_URL}"
health_response="$(curl -fsS -w '|%{http_code}' "${HEALTH_URL}")"
health_status="${health_response##*|}"
health_body="${health_response%|*}"

if [ "${health_status}" != "${EXPECTED_STATUS}" ]; then
  echo "El health check respondió ${health_status} en lugar de ${EXPECTED_STATUS}." >&2
  exit 1
fi

if [ "$(printf '%s' "${health_body}" | tr -d '[:space:]')" != "${EXPECTED_BODY}" ]; then
  echo "El cuerpo del health check no es el esperado: ${health_body}" >&2
  exit 1
fi

echo "==> Ejecutando la suite de tests contra PostgreSQL"
if ! docker compose run --rm tests; then
  echo "La suite de tests ha fallado." >&2
  exit 1
fi

echo "==> Verificación de entrega correcta"
