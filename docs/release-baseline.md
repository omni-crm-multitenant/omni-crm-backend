# Baseline de calidad — Fase 0

- **Fecha:** 2026-09-13
- **Rama:** `fix/architecture-corrections`
- **Commit de partida:** `0b52e88012b58666b47cfac72637f959989b9879`
- **Python:** 3.13.5
- **pytest:** 8.4.1
- **Ruff:** 0.12.11
- **mypy:** 1.17.1
- **PostgreSQL local/Compose:** 17
- **Redis local/Compose:** 7.4

## Resultado inicial

| Comando | Resultado | Observación |
|---|---:|---|
| `python -m pytest -q` | PASS | 113 pruebas, 6 skips, 0 fallos |
| `ruff check app tests` | FAIL | 57 errores existentes |
| `mypy app` | FAIL | 39 errores existentes |
| `PYTHONPATH=. python scripts/validate_openapi.py` | PASS | 71 rutas OpenAPI |
| `python -m compileall -q app tests` | PASS | Sin errores de compilación |
| `python scripts/validate_openapi.py` sin `PYTHONPATH` | FAIL | El script no resuelve `app` desde el directorio `scripts`; se corrigió el comando CI |

Docker está instalado en el runner local, pero el plugin `docker compose` no devolvió
versión durante esta captura; por eso no se ejecutó el stack Compose como parte de
este baseline.

## Cambios de esta fase

- Se fijaron Ruff y mypy en el extra `quality` de `pyproject.toml`.
- CI instala `.[test,quality]` en lugar de herramientas sin versión.
- CI usa PostgreSQL 17 y Redis 7.4, alineados con Compose.
- CI ejecuta OpenAPI con `PYTHONPATH=.`.
- README refleja que Compose ejecuta el servicio `migrate` antes de API/workers.
- Se añadió `CONTRIBUTING.md` con comandos oficiales y reglas de pruebas/migraciones.

## Deuda trasladada a Fase 1

Los 57 errores de Ruff y 39 de mypy no se han corregido en esta fase. Se mantienen
registrados para que Fase 1 los resuelva incrementalmente sin ocultar regresiones.
