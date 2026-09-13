# Fase 2 — Límites de aplicación: piloto de contactos

Fecha: 2026-09-13
Rama: `fix/architecture-corrections`

## Alcance

Se extrajeron los casos de uso de creación, listado y actualización de contactos desde `app/api/v1/contacts.py` hacia `app/application/contacts.py`.

El módulo de aplicación posee:

- `CreateContactCommand`;
- `ContactListQuery`;
- `UpdateContactCommand`;
- casos de uso con tenant explícito;
- validación de custom fields;
- normalización de email/teléfono;
- persistencia mediante `flush`, sin commits internos;
- auditoría de creación y actualización.

El router conserva únicamente:

- adaptación de payloads HTTP;
- dependencias de autenticación/autorización;
- traducción de errores de dominio a `HTTPException`;
- serialización de respuestas.

## Guardrails

`tests/test_contact_architecture.py` verifica que los tres endpoints no ejecuten directamente consultas, paginación, normalización, validación de campos ni operaciones de persistencia.

## Validación

- Prueba arquitectónica y pruebas de contactos: pasan.
- Suite completa: 113 pasadas, 6 omitidas.
- Ruff: pasa.
- Mypy: pasa.
- OpenAPI: 71 rutas válidas.
- Compilación Python: pasa.
- `git diff --check`: pasa.

## Pendiente

Replicar el mismo patrón por capacidad, empezando por `identity` o `conversations`, sin crear capas abstractas adicionales hasta que exista un segundo caso de uso que justifique compartirlas.
