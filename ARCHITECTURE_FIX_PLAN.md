# Plan de corrección arquitectónica

## Objetivo

Convertir `omni-crm-backend` en un monolito modular con límites aplicados, aislamiento multi-tenant verificable, unidades de trabajo consistentes y estado operativo compatible con réplicas.

## Alcance de esta rama

Rama: `fix/architecture-corrections`

### P0 — Guardrails de seguridad y contexto

- Establecer y limpiar `TenantContext` de forma segura en dependencias HTTP.
- Propagar tenant explícito a workers y preservar telemetría.
- Añadir pruebas de contexto y aislamiento negativo.

### P1 — Unidad de trabajo

- El commit pertenece al caso de uso o worker de nivel superior.
- Servicios internos hacen `flush`, no `commit`, salvo operaciones explícitamente aisladas.
- Añadir pruebas de rollback y composición.

### P1 — Estado distribuible

- Implementar rate limiting distribuido con Redis, manteniendo fallback explícito sólo para local/test.
- Sustituir métricas/tracing globales por una interfaz de observabilidad con backend apropiado; no usar estado global como fuente operacional.
- Preparar almacenamiento de exportaciones con TTL y backend intercambiable.

### P1 — Migraciones de despliegue

- Añadir un job/servicio de migración único y documentar el orden de release.
- Validar que aplicación y workers no arranquen contra un esquema incompatible.

### P2 — Límites de aplicación

- Pilotar `contacts`: casos de uso para crear, actualizar y listar; el router sólo adapta HTTP.
- Separar autorización de FastAPI.
- Evitar que repositorios importen servicios; la orquestación de custom fields pertenece al caso de uso.

### P2 — Refactorización por capacidades

Migrar gradualmente `identity`, `conversations`, `integrations/meta`, `automation`, `billing` y `ai`. Cada capacidad debe tener:

- contratos de aplicación;
- adaptadores HTTP y worker;
- persistencia encapsulada;
- autorización y tenant explícitos;
- pruebas de comportamiento y aislamiento.

## Criterios de aceptación

- `pytest` completo sin regresiones.
- `ruff check app tests` sin nuevos errores.
- `mypy app` sin nuevos errores.
- Pruebas específicas de tenant, rollback, rate limiting y migraciones.
- Ningún secreto nuevo ni credencial en el diff.
- El informe de arquitectura queda actualizado con hallazgos resueltos y pendientes.

## Orden de implementación

1. Tests RED para contexto tenant y política transaccional.
2. Implementación mínima y tests GREEN.
3. Migración del piloto `contacts`.
4. Sustitución del rate limiter local y estado operativo.
5. Gate de migraciones.
6. Revisión independiente del diff y suite completa.

## Riesgos y límites

- No se dividirá el sistema en microservicios sin métricas de carga o presión operativa que lo justifique.
- No se cambiará el esquema de negocio sin migración Alembic reversible/compatible.
- No se eliminarán filtros tenant explícitos aunque exista un contexto implícito: el contexto es un guardrail, no el único control de autorización.
