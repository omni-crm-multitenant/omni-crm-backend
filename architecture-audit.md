# Auditoría arquitectónica — omni-crm-backend

- **Repositorio:** `omni-crm-multitenant/omni-crm-backend`
- **Commit auditado:** `00b9efaeb4ffedb70b32cd9807f177686859826d`
- **Fecha de revisión:** 2026-09-13
- **Alcance:** repositorio completo, con foco en `app/`, `migrations/`, `tests/`, `compose.yaml`, CI y documentación.
- **Método:** revisión estática; inventario de archivos, métricas de tamaño, grafo de imports y lectura dirigida de límites API/core/services/repositories/workers/db.
- **No ejecutado:** código de aplicación ni pruebas del proyecto. La conclusión se basa en evidencia estática.

## Veredicto ejecutivo

**REVISAR antes de escalar el sistema o declararlo Clean Architecture.** El proyecto tiene una base razonable de monolito modular: PostgreSQL como fuente durable, Alembic, outbox, Celery, separación inicial entre API/servicios/repositorios y pruebas específicas de aislamiento. Sin embargo, los límites no están aplicados de forma consistente. La API accede directamente a modelos y sesiones en muchos routers, un servicio importa dependencias FastAPI, repositorios importan servicios, el contexto tenant global no se establece en producción y varios componentes operativos mantienen estado sólo en memoria.

La recomendación no es dividirlo ahora en microservicios. Es consolidar límites dentro del monolito, hacer explícita la unidad de trabajo y eliminar estado local de proceso antes de aumentar el número de réplicas.

## Contexto arquitectónico observado

- **Estilo actual:** monolito modular por capas, no Clean Architecture estricta.
- **Procesos:** FastAPI, Celery worker y Celery Beat; PostgreSQL y Redis compartidos (`README.md:53-55`, `compose.yaml:38-81`).
- **Tamaño:** 258 archivos Python; aproximadamente 9.231 líneas en `app/api/v1`, `app/services`, `app/repositories` y `app/workers` según el inventario estático.
- **Concentración:** `app/api/v1/auth.py` 480 líneas, `app/api/v1/contacts.py` 367, `app/services/meta_oauth.py` 360, `app/services/sessions.py` 230, `app/api/v1/custom_fields.py` 222.
- **Persistencia:** 50 migraciones Alembic hasta `0050_billing_usage_events.py`.
- **Dependencias declaradas:** FastAPI, SQLAlchemy async, PostgreSQL/asyncpg, Redis/Celery, Alembic y Pydantic (`pyproject.toml:10-24`).

## Fortalezas

1. **Elección de monolito adecuada para el estado actual.** El README documenta explícitamente que no se adoptan microservicios prematuros (`README.md:53-74`).
2. **Persistencia y evolución de esquema identificables.** Hay Alembic y una cadena de migraciones versionada, en lugar de depender sólo de `create_all()`.
3. **Aislamiento tenant presente en varios contratos.** `TenantContext` es inmutable y tipa roles (`app/core/tenant_context.py:10-15`); `require_tenant_context` valida membresía y tenant conjuntamente (`app/api/dependencies.py:68-90`); `create_contact` y `update_contact` filtran por `context.tenant_id` (`app/repositories/contacts.py:16-47`, `53-82`).
4. **Base de resiliencia asíncrona.** Existe outbox, Celery con `acks_late` y rechazo ante pérdida del worker (`app/workers/celery_app.py:7-16`), además de endpoints de readiness que comprueban PostgreSQL y Redis (`app/main.py:113-135`).
5. **Controles de producción iniciales.** La configuración rechaza secretos placeholder y billing mock en producción (`app/core/config.py:51-63`), y CI incluye lint, tipos, pruebas, escaneo de dependencias, secretos e imagen (`.github/workflows/ci.yml:7-117`).

## Rúbrica de arquitectura

| Dimensión | Estado | Evidencia resumida |
|---|---|---|
| Fidelidad a requisitos y atributos | 🟡 | Multi-tenancy, outbox y workers están documentados; faltan objetivos cuantificados de latencia, disponibilidad, volumen y crecimiento. |
| Calidad de límites y cohesión | 🔴 | Routers importan modelos directamente; `services/authorization.py` importa FastAPI; repositorios importan servicios. |
| Moderación de patrones | 🟡 | El monolito es una decisión contenida, pero la carpeta `services` acumula demasiados contextos y las fronteras son convencionales, no enforced. |
| Datos y estado | 🟡 | PostgreSQL/Alembic son buenas bases; el contexto tenant de `ContextVar` no se establece en el flujo productivo y existen estados operativos en memoria. |
| Tolerancia al cambio | 🔴 | La lógica de casos de uso está repartida entre routers, servicios y repositorios; cambiar transporte o ejecutar el mismo caso desde worker exige duplicación/adaptación. |
| Fallos y escala | 🔴 | Rate limiting, métricas, tracing y export store dependen del proceso; además no aparece un paso de migración en Compose/CI de despliegue. |
| Decisiones y legibilidad | 🟡 | README explica decisiones y límites, pero no hay directorio ADR visible ni objetivos operativos verificables. |

## Hallazgos priorizados

### A-01 — El límite de arquitectura está documentado, pero no se aplica

- **Severidad:** Mayor
- **Evidencia:** Los routers importan modelos o DB directamente en al menos 19 módulos, incluyendo `app/api/v1/auth.py:17`, `contacts.py:11-13`, `opportunities.py:52,76,93,109,133` y `tasks.py:47,56,70`. Además, hay `session.add(...)` en routers como `app/api/v1/auth.py:198,392`, `contacts.py:155,278,302`, `settings.py:98` y `opportunities.py:61`.
- **Impacto:** Las reglas de negocio y límites de persistencia quedan acoplados a FastAPI. Un worker, CLI o webhook que necesite el mismo caso de uso no puede reutilizar un flujo único; puede terminar duplicando autorización, validación y transacciones.
- **Dirección recomendada:** Definir comandos/consultas de aplicación por capacidad (`identity`, `contacts`, `conversations`, `billing`, etc.). Los routers deben traducir HTTP a esos casos de uso; el acceso a modelos y `AsyncSession` debe concentrarse en adaptadores de persistencia o servicios de aplicación explícitos. Migrar por flujo, no por una gran reescritura.

### A-02 — Dependencias invertidas en sentido contrario

- **Severidad:** Mayor
- **Evidencia:** `app/services/authorization.py:5-11` importa `Depends`, `HTTPException`, `get_session` y `require_tenant_context` desde la capa API. `app/repositories/contacts.py:7-9` importa `validate_custom_field_payload` desde `app.services`; el mismo patrón aparece en `repositories/messages.py` y `repositories/channel_assets.py`.
- **Impacto:** La lógica que debería poder ejecutarse desde workers o pruebas de aplicación requiere FastAPI o políticas de aplicación. También aumenta el riesgo de ciclos y hace que cambiar el transporte rompa capas inferiores.
- **Dirección recomendada:** Mover la autorización de dominio a funciones puras/protocolos sin FastAPI; crear adaptadores HTTP que conviertan excepciones de aplicación a respuestas HTTP. Los repositorios deben depender de modelos/contratos de persistencia, no de servicios; la validación de campos debe ser orquestada por el caso de uso.

### A-03 — `TenantContext` no se establece en el flujo productivo

- **Severidad:** Mayor de seguridad/operación
- **Evidencia:** `app/core/tenant_context.py:30-35` define `set_current_tenant_id`, pero el inventario estático sólo encuentra llamadas productivas a `get_current_tenant_id` en logging/tracing (`app/core/logging_config.py:8,16`, `app/core/tracing.py:11,36`). `app/api/dependencies.py:68-90` valida y devuelve `TenantContext`, pero no llama a `set_current_tenant_id`.
- **Impacto:** Los logs y trazas no reciben el tenant activo aunque la ruta haya autenticado correctamente. Más importante: el contexto implícito no puede servir como guardrail para código nuevo que dependa de `get_current_tenant_id`; el aislamiento queda basado en que cada query recuerde pasar explícitamente el contexto. Eso es frágil en un sistema multi-tenant.
- **Dirección recomendada:** Establecer el `ContextVar` al construir el contexto y resetearlo con un token en middleware/dependencia, incluyendo workers con contexto explícito. Mantener filtros explícitos en repositorios; el `ContextVar` debe ser telemetría y defensa adicional, no la única autorización. Añadir una prueba que verifique tenant en logs/traces y otra que falle cuando una operación de negocio se ejecuta sin contexto.

### A-04 — Estado operativo local impide escala horizontal consistente

- **Severidad:** Mayor
- **Evidencia:** `app/main.py:14,40,64-74` crea `InMemoryLimiter` por proceso. `app/core/metrics.py:8-13` mantiene contadores y latencias en diccionarios globales; `app/core/tracing.py:14` mantiene `spans` en una lista global; `app/services/export_store.py:8-18` mantiene exportaciones en un diccionario local.
- **Impacto:** Con dos réplicas, cada instancia aplica límites distintos y expone métricas parciales. Reiniciar un proceso elimina métricas y exportaciones. Enrutamiento no pegajoso puede hacer que un export o un contador no esté disponible en la siguiente petición.
- **Dirección recomendada:** Usar Redis o un componente de observabilidad real para rate limits y métricas; usar almacenamiento durable/objeto con TTL para exportaciones. El tracing debe salir por OpenTelemetry/collector o quedar claramente limitado a desarrollo. Definir qué estado puede perderse y qué estado debe sobrevivir reinicios.

### A-05 — Las fronteras transaccionales son inconsistentes

- **Severidad:** Mayor
- **Evidencia:** El proveedor FastAPI confirma la sesión completa en `app/db/session.py:14-25`; sin embargo, hay `session.commit()` internos en `app/services/meta_oauth.py:185,344` y en workers (`campaign_tasks.py:18,45`, `contact_privacy_tasks.py:21,32`, `outbox_tasks.py:15`). Al mismo tiempo, varios routers hacen `session.add(...)` directamente.
- **Impacto:** Un caso de uso que llama a una operación con commit interno no puede agruparla con otra escritura de forma atómica. El comportamiento cambia según se invoque desde HTTP o worker; los fallos parciales y la composición de operaciones son más difíciles de razonar.
- **Dirección recomendada:** Elegir una regla: el caso de uso/worker posee la unidad de trabajo y los servicios internos sólo hacen `flush`, o crear explícitamente transacciones anidadas cuando la semántica lo requiera. Documentar la política y añadir tests de rollback y composición para OAuth, outbox y privacidad.

### A-06 — El ciclo de migraciones no está conectado al despliegue

- **Severidad:** Mayor operativa
- **Evidencia:** `compose.yaml:38-81` arranca app, worker y beat, pero no contiene un servicio/comando `alembic upgrade head`. El workflow CI ejecuta pruebas y validaciones (`.github/workflows/ci.yml:19-80`), pero no muestra una etapa de migración contra una base de despliegue.
- **Impacto:** Una imagen nueva puede arrancar código que espera columnas o tablas ausentes. Si se añade la migración como side effect no controlado de cada réplica, se puede crear una carrera de despliegue; si no se ejecuta, el fallo aparece tarde en runtime.
- **Dirección recomendada:** Añadir una etapa de release explícita, única y observable para `alembic upgrade head`, con backup/rollback compatible y health gate posterior. Mantener migraciones backward-compatible durante despliegues rolling.

### A-07 — Cohesión insuficiente en módulos de alta concentración

- **Severidad:** Media
- **Evidencia:** `auth.py` tiene 480 líneas, `contacts.py` 367, `meta_oauth.py` 360 y `sessions.py` 230. El inventario registra más de 60 módulos bajo `app/services`, cubriendo identidad, CRM, IA, automatización, billing, Meta, privacidad y operaciones.
- **Impacto:** Los cambios de un mismo módulo pueden afectar varias razones de cambio. El tamaño no prueba por sí mismo un defecto, pero aquí coincide con acceso directo a persistencia desde routers y con servicios que mezclan políticas, integración y transacción.
- **Dirección recomendada:** Extraer por caso de uso y contexto de cambio, no por número de líneas solamente. Priorizar `auth`, `contacts` y `meta_oauth`; mantener un API público pequeño por módulo y dejar los detalles SQL/integración detrás de adaptadores.

## Riesgos de escalabilidad específicos

1. **Réplicas HTTP:** el rate limiter y métricas locales divergen entre procesos (`app/main.py:40`, `app/core/metrics.py:8-13`).
2. **Telemetría multi-tenant:** el tenant no se escribe en `ContextVar` durante la dependencia (`app/api/dependencies.py:68-90`), por lo que el diagnóstico de incidentes queda incompleto.
3. **Workers y reintentos:** Celery está configurado para reintentos/ack tardío, pero la consistencia depende de límites transaccionales diferentes entre tareas y servicios.
4. **Evolución de esquema:** 50 migraciones muestran velocidad de cambio; sin gate de migración en release aumenta el riesgo operativo.
5. **Datos de exportación:** el almacenamiento en memoria no es compatible con ejecución multi-réplica ni con reinicios.

## Plan incremental recomendado

### Fase 0 — Guardrails inmediatos

- Establecer/resetear `TenantContext` y agregar pruebas de telemetría.
- Documentar NFR mínimos: tenants, requests/s, tamaño máximo de conversaciones, disponibilidad, latencia p95 y retención.
- Definir y probar el contrato de migración de release.
- Marcar explícitamente qué endpoints son MVP, fundación o no implementados.

### Fase 1 — Consolidar una capacidad vertical

- Elegir `contacts` como piloto.
- Crear casos de uso `CreateContact`, `UpdateContact`, `ListContacts`.
- Retirar `session.add` y queries de `app/api/v1/contacts.py` gradualmente.
- Mover validación de custom fields a una dependencia de aplicación, no de repositorio.
- Mantener el esquema SQLAlchemy como detalle de infraestructura y probar aislamiento negativo entre dos tenants.

### Fase 2 — Normalizar transacciones y adaptadores

- Adoptar una política única de unidad de trabajo para HTTP y Celery.
- Separar excepciones de aplicación de `HTTPException`.
- Introducir protocolos sólo en seams reales: reloj, proveedor Meta, correo, billing, almacenamiento de exportaciones.
- Migrar `authorization.py` fuera de FastAPI y dejar un adaptador HTTP en API.

### Fase 3 — Preparar escala operativa

- Rate limiting distribuido en Redis.
- Métricas/tracing externos y con etiquetas controladas; evitar cardinalidad ilimitada por ruta, tenant o URL.
- Export store durable con TTL.
- Job de migración único en despliegue y health checks que distingan aplicación lista de esquema listo.

### Fase 4 — Revisión de límites de dominio

- Revisar límites `identity`, `crm/conversations`, `integrations/meta`, `automation`, `billing` y `ai` usando métricas de cambio y carga reales.
- Extraer un proceso independiente sólo si existe una presión demostrada de despliegue, aislamiento o escalabilidad; no antes.

## Validación recomendada para el siguiente cambio

- Prueba que `require_tenant_context` establece y limpia el tenant en `ContextVar`.
- Prueba negativa: tenant A no puede leer, actualizar, exportar ni borrar recursos de tenant B.
- Pruebas de rollback que compongan dos escrituras y fallen en la segunda.
- Prueba con dos procesos/réplicas para rate limit y exportaciones.
- Prueba de despliegue sobre una base en versión anterior ejecutando migraciones backward-compatible.
- Métricas: p95/p99 HTTP, profundidad/edad de outbox, reintentos, tasa de errores por dependencia, consultas por tenant y tamaño de tablas de eventos.

## Estado de implementación en `fix/architecture-corrections`

Aplicado y verificado:

- `TenantContext` se establece al validar la membresía HTTP.
- La aplicación usa `RedisSlidingWindowLimiter` en producción y memoria sólo en local/test.
- El cliente Redis del limitador se cierra mediante lifespan.
- Compose ejecuta un único servicio `migrate` con `alembic upgrade head` antes de API, worker y beat.
- Las dependencias HTTP `require_roles` viven en `app/api/dependencies.py`, no en `app/services/authorization.py`.
- El piloto de contactos tiene casos de uso para crear, listar, actualizar, consentir, revocar consentimiento, exportar y borrar lógicamente.
- Los routers de contactos no gestionan consultas, validación de dominio ni persistencia para esos casos.
- Los repositorios no importan servicios; los value objects compartidos viven en `app/domain`.
- Existen pruebas arquitectónicas de límites, aislamiento tenant y rollback de unidad de trabajo.
- Suite completa: 113 pruebas ejecutadas, 6 omitidas, 0 fallos.

Pendiente en iteraciones posteriores:

- Confirmar en CI remoto `alembic upgrade head` y `alembic check` sobre PostgreSQL real.
- Extraer casos de uso equivalentes de `identity`, `conversations`, `integrations/meta`, `automation`, `billing` y `ai`.
- Revisar los commits explícitos de OAuth y workers bajo la política de unidad de trabajo.
- Sustituir métricas, tracing y exportaciones locales por backends compartidos.
- Completar integración real, E2E, CD, observabilidad y pruebas de carga.


La arquitectura es viable como **monolito modular en etapa temprana**, y no justifica una migración inmediata a microservicios. No debe presentarse todavía como Clean Architecture aplicada: sus dependencias y límites son parcialmente convencionales y varias capas cruzan responsabilidades. Las prioridades son aislamiento/telemetría tenant, estado compartido para escala, unidad de trabajo consistente y extracción gradual de la lógica fuera de los routers.
