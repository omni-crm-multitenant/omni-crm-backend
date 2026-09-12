# Local readiness

Checked on 2026-09-05 without exposing configuration values.

## Verified

- Git 2.55.0 is available.
- Bundled Python 3.12.14 can run local verification commands.
- Backlog validation passes before backend work starts.
- Docker Desktop 29.7.2 runs through its installed local executable.
- Compose starts healthy API, PostgreSQL 17, Redis 7.4, Celery worker, one Celery Beat scheduler, and Mailpit.
- PostgreSQL migrations 0001 through 0015 apply successfully.
- API health check returns 200.
- A registration request persists tenant, user, membership, and email outbox in PostgreSQL.
- Celery delivers the outbox email through SMTP; Mailpit captures it and the outbox reaches sent with one attempt.

## Local note

System Python is not on PATH. The project virtual environment uses bundled Python 3.12.14. Containers use Python 3.12.

## External activation gates

- Meta access is owner-declared, not technically verified.
- AI provider access is owner-declared, not technically verified.
- AWS or GCP remains undecided.
- Payoneer automatic USD collection remains blocked pending commercial and API evidence for the Colombian company.

Local work uses fake external providers. Missing external credentials do not block local contracts or tests.
