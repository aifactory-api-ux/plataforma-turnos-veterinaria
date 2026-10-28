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
