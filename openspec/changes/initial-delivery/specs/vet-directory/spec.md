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
