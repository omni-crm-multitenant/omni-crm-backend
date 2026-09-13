# Fase 3 — Primera rebanada de integración real

Fecha: 2026-09-13
Rama: `fix/architecture-corrections`

## Implementado

- Nuevo job `integration` en `.github/workflows/ci.yml`.
- Servicios efímeros del job:
  - PostgreSQL 17;
  - Redis 7.4;
  - Mailpit 1.27.
- El job ejecuta `alembic upgrade head` antes de las pruebas.
- Las variables de integración separan explícitamente:
  - `TEST_DATABASE_URL`;
  - `TEST_REDIS_URL`;
  - `TEST_MAILPIT_URL`.

## Pruebas añadidas

`tests/integration/test_real_services.py` verifica:

- existencia del esquema PostgreSQL y revisión Alembic después de migrar;
- rate limiter Redis real y comportamiento compartido/atómico;
- entrega SMTP real a Mailpit y lectura posterior por su API.

Las pruebas se omiten fuera del entorno de integración cuando faltan las variables de servicio. En CI no se omiten porque el job declara los tres servicios y sus variables.

Las pruebas de concurrencia existentes ya no ejecutan `create_all()` ni `drop_all()`; dependen del esquema generado por Alembic y fallan si se omiten migraciones.

## Validación local

- Ruff: pasa.
- Mypy: pasa.
- Suite completa: 122 pasadas, 10 omitidas.
- YAML de CI y Compose: válido.
- `git diff --check`: pasa.
- Integración real local: no ejecutada porque Docker Compose no está disponible en este entorno.

## Pendiente de esta fase

- Ejecutar el job remoto para validar PostgreSQL, Redis y Mailpit reales.
- Añadir worker Celery real y pruebas de outbox/reintento/idempotencia en el siguiente corte de Fase 3.
- Añadir escenarios de aislamiento tenant y readiness con dependencia caída.
