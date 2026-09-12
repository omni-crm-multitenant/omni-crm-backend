# AGENTS.md

Backend FastAPI del CRM multiinquilino conversacional (WhatsApp Cloud API, Instagram Direct, Messenger). Este directorio es el repositorio git real del proyecto (`omni-process/` en el nivel superior solo contiene la especificación y el backlog, no es un repo git).

## Especificación y backlog (fuente de verdad)

- `../.agent/prd/PRD.md` — contratos del sistema. `../.agent/prd/SUMMARY.md` — resumen. `CORRECTIONS.md`, `VALIDATION.md`, `PAYONEER-GATE.md` — estado de correcciones y de la habilitación de pagos (bloqueada, pendiente de evidencia comercial).
- `../.agent/tasks.json` + `../.agent/tasks/TASK-N.json` — backlog de tareas atómicas. Cada TASK trae `acceptanceCriteria`, `steps`, `dependencies` y `contractRef` a una sección del PRD. Antes de implementar algo que corresponda a un TASK-N, léelo y contrasta con el `contractRef` — no improvises alcance.
- El proyecto está en modo local/simulado: integraciones externas (Meta, IA, cloud, Payoneer) son opcionales o mock. `BILLING_MODE=mock` por defecto; no asumas cobro real activo.

## Arrancar en local

```
cp .env.example .env.local   # .env.local es privado y está excluido por Git
.\scripts\docker.ps1 compose up --build
```

- Docs OpenAPI: `http://localhost:8000/api/v1/docs`
- `scripts/docker.ps1` localiza Docker Desktop aunque no esté en el PATH (instalación fuera del PATH por defecto en esta máquina) — usar este wrapper en vez de `docker` directo.
- Python 3.12–3.13 (`requires-python = ">=3.12,<3.14"` en `pyproject.toml`); dependencias fijadas en `requirements.lock` (fuente editable: `requirements.in`).

## Tests

```
pytest
```

- Config en `pyproject.toml`: `testpaths = ["tests"]`, `asyncio_mode = "auto"` (no hace falta marcar `@pytest.mark.asyncio`).
- `tests/integration/` para pruebas de integración; el resto son unitarias por módulo (`test_registration.py`, `test_mfa_api.py`, `test_tenant_context.py`, etc.).
- Dependencias de test (`[project.optional-dependencies].test`): `httpx`, `pytest-asyncio`, `aiosqlite` — los tests corren contra SQLite async, no contra Postgres real.
- Entorno virtual ya presente en `.venv/`.

## Estructura de `app/`

- `app/main.py` — `create_app()` construye la app FastAPI y monta `api_router` bajo prefijo `/api/v1` (docs en `/api/v1/docs`, sin redoc).
- `app/api/v1/` — routers HTTP. `app/api/dependencies.py` — dependencias inyectadas (auth, contexto de tenant).
- `app/core/`:
  - `config.py` — `Settings` (pydantic-settings, lee `.env.local`). Valida en `reject_unsafe_production`: en `app_env=production` rechaza secretos placeholder (`JWT_SECRET`, `MFA_ENCRYPTION_KEY`) y `BILLING_MODE=mock`. Al añadir settings nuevos, seguir ese patrón de validación para producción.
  - `security.py` — hashing/crypto (Argon2, Fernet-style vía `cryptography`).
  - `tenant_context.py` — `TenantContext`/`IntegrationContext` vía `ContextVar`; roles válidos: `administrador`, `supervisor`, `agente_comercial`. Todo acceso a datos debe pasar por el tenant activo en este contexto — nunca cruzar tenants.
  - `tokens.py` — JWT/tokens de acceso, challenge (MFA) y refresh, TTLs configurables en `Settings`.
- `app/models/` — modelos SQLAlchemy async de identidad, CRM y operación.
- `app/repositories/` — acceso a datos para membresías y contactos.
- `app/services/` — lógica de identidad, correo, autorización, auditoría, credenciales, activos y campos personalizados.
- `app/workers/` — Celery: `celery_app.py`, `email_tasks.py`.
- `migrations/` — Alembic (`alembic.ini` en la raíz del backend).

## Convenciones e invariantes del dominio

- **Aislamiento multi-tenant**: cualquier query, servicio o endpoint nuevo debe resolver y respetar `tenant_context.py`. Nunca exponer ni tocar datos de otro tenant o de un recurso no asignado.
- **Secretos**: nunca hardcodear `JWT_SECRET`, `MFA_ENCRYPTION_KEY`, credenciales SMTP/Meta/AI — siempre vía `Settings`/`.env.local`.
- **Toma humana de conversación**: cuando una persona toma control, la versión de conversación debe invalidar respuestas de IA pendientes antes del despacho (contrato del PRD) — cualquier feature de agente/IA debe respetar esto.
- **Recepción de eventos Meta**: deben persistirse antes de confirmar recepción (at-least-once, recuperable por workers) — un envío de aceptación remota incierta queda `unknown`, sin reenvío automático ciego.
- Roles de membership están tipados como literal (`administrador`, `supervisor`, `agente_comercial`) — no introducir strings libres para roles.

## Skills de repo relevantes

Este entorno tiene skills invocables con `/` que aplican convenciones ya definidas para este equipo: `git-workflow` (ramas/commits), `pr-workflow` (plantilla y flujo de PR), `quality-gates` (lint/tipos/tests/build antes de commitear), `code-review`/`pr-review` (checklist de revisión). Úsalas en vez de improvisar convenciones de commit/PR.
