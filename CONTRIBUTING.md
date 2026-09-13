# Contribuir al backend

## Requisitos

- Python 3.12 o 3.13.
- `uv` para crear el entorno virtual.
- Docker Compose para PostgreSQL, Redis, Mailpit y migraciones.

## Preparar el entorno

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[test,quality]"
cp .env.example .env.local
```

En Windows, usa `scripts/docker.ps1` para ejecutar Docker Compose.

## Comandos oficiales

Ejecutar desde la raíz del repositorio:

```bash
# Unit/component tests
.venv/bin/python -m pytest -q

# Formatting/lint gate
.venv/bin/ruff check app tests

# Type gate
.venv/bin/mypy app

# OpenAPI contract
PYTHONPATH=. .venv/bin/python scripts/validate_openapi.py

# Syntax/import compilation
.venv/bin/python -m compileall -q app tests

# Local integration services
./scripts/docker.ps1 compose up -d --build
./scripts/docker.ps1 compose run --rm migrate
```

En PowerShell, sustituye `.venv/bin/python` por `.venv/Scripts/python.exe` y
`./scripts/docker.ps1` por `./scripts/docker.ps1`.

## Tipos de pruebas

- `tests/`: pruebas unitarias y de API in-process.
- `tests/integration/`: integraciones con servicios reales; se ampliará para PostgreSQL, Redis y Celery.
- `tests/e2e/`: reservado para flujos HTTP contra el sistema desplegado.

No llames E2E a una prueba que use sólo `TestClient` dentro del mismo proceso.

## Flujo de ramas

- `master`: rama estable.
- `fix/*`: correcciones.
- `feat/*`: funcionalidades.
- `chore/*`: mantenimiento.

Cada cambio debe incluir pruebas cuando modifique comportamiento. Antes de abrir
un PR ejecuta los comandos oficiales y registra cualquier limitación del entorno.

## Migraciones

Toda modificación persistente requiere una migración Alembic revisada. Las
migraciones deben ser compatibles con despliegues rolling: primero añadir lo nuevo,
luego desplegar código compatible y finalmente retirar lo antiguo en otra entrega.

## Seguridad

- No subas `.env.local`, tokens, claves privadas ni credenciales.
- No incluyas secretos en logs, fixtures o mensajes de error.
- Los cambios de CI/CD deben usar permisos mínimos y secretos de GitHub Environments.
