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
