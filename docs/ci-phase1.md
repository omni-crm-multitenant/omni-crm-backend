# Fase 1 — CI verde y migraciones verificables

Fecha: 2026-09-13
Rama: `fix/architecture-corrections`

## Cambios

- Ruff quedó sin errores en `app` y `tests`.
- Mypy quedó sin errores en los 167 archivos de `app`.
- El workflow instala las dependencias declaradas en `pyproject.toml`.
- El job de PostgreSQL ejecuta `alembic upgrade head` antes de las pruebas.
- El job de PostgreSQL ejecuta `alembic check` para detectar divergencia entre modelos y migraciones.
- CI mantiene PostgreSQL 17 y Redis 7.4, alineados con Compose.

## Gate local verificado

- Ruff: pasa.
- Mypy: pasa.
- Pytest: 113 pruebas pasadas, 6 omitidas.
- OpenAPI: 71 rutas válidas.
- Compilación Python: pasa.
- YAML del workflow: válido.
- `git diff --check`: pasa.

## Limitación del entorno local

`alembic check` no pudo conectarse porque este entorno no tiene un servidor PostgreSQL activo y el plugin `docker compose` no está instalado. El workflow de CI sí ejecuta `upgrade head` y `check` contra el servicio PostgreSQL declarado en GitHub Actions.

La fase no se considera promotora a E2E/CD hasta que CI remoto confirme ambos comandos de Alembic sobre PostgreSQL real.
