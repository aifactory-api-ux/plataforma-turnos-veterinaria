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
