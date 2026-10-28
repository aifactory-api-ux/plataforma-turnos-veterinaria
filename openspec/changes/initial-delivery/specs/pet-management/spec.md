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
