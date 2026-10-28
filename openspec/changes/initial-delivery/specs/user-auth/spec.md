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
