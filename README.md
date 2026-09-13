# Omni Backend

Omni Backend es la interfaz de programación de aplicaciones (API) de un sistema
de gestión de relaciones con clientes (CRM) conversacional multiinquilino. Permite
gestionar empresas, usuarios, sesiones, configuración comercial y las bases de
futuras integraciones con Meta e inteligencia artificial (IA). Este README está
dirigido a desarrolladores backend y responsables técnicos que necesitan
ejecutar, entender, probar o extender el servicio.

El repositorio contiene una base funcional de identidad, seguridad y datos. No
contiene todavía la integración operativa con Meta, agentes de IA con LangGraph,
automatizaciones comerciales, oportunidades de venta ni cobros reales. Consulta
[Estado funcional](#estado-funcional) antes de integrar un cliente.

Usa este mapa para localizar la información principal:

- [Arquitectura](#arquitectura): estilo, decisiones, capas, dependencias y flujos.
- [Ejecución con Docker](#ejecuta-el-proyecto-con-docker): arranque local verificable.
- [Autenticación y sesiones](#autenticación-y-sesiones): identidad, MFA y multiempresa.
- [Modelo de datos](#modelo-de-datos): tablas, responsabilidades y estados.
- [Referencia de API](#referencia-de-api): rutas y nivel de acceso.
- [Estructura del repositorio](#estructura-del-repositorio): archivos y ubicación de código nuevo.
- [Limitaciones conocidas](#limitaciones-conocidas): brechas antes de producción.

## Estado funcional

La siguiente tabla separa las capacidades ejecutables de las fundaciones de
dominio y del trabajo que todavía no está implementado:

| Área | Estado | Alcance disponible |
|---|---|---|
| API y persistencia | Implementado | FastAPI, SQLAlchemy asíncrono, PostgreSQL y Alembic hasta `0015_tenant_settings` |
| Registro empresarial | Implementado | Crea empresa, administrador, membresía e intención de correo en una transacción |
| Autenticación | Implementado | JSON Web Token (JWT), sesiones persistentes, token de renovación rotatorio, logout y recuperación |
| Multiempresa | Implementado | Lista membresías y exige selección cuando una identidad pertenece a varias empresas |
| Autenticación multifactor (MFA) | Implementado | Contraseñas de un solo uso basadas en tiempo (TOTP), 10 códigos de recuperación y desactivación verificada |
| Equipo | Implementado | Invitaciones para supervisores y agentes comerciales, aceptación y revocación |
| Configuración empresarial | Implementado | Zona horaria, idioma, horarios, política fuera de horario, contacto e interruptores |
| Campos personalizados | Implementado | Definiciones tipadas por empresa; CRUD administrativo y validación |
| Contactos | Fundación | Modelo y repositorio; no existe router HTTP de contactos |
| Conversaciones y mensajes | Fundación | Modelos e invariantes; no existen routers HTTP ni despacho externo |
| Correo | Parcial | Outbox, protocolo simple de transferencia de correo (SMTP), Celery y Mailpit; falta despacho automático |
| Activos Meta | Fundación | Modelo, propiedad única, resolución y revalidación; faltan OAuth y webhooks |
| IA | Configuración y esquema | Variables, interruptor, `ai_mode` y `control_version`; no hay LangChain ni LangGraph |
| Automatizaciones | No implementado | Existe el interruptor; no existen reglas, temporizadores ni ejecución |
| Oportunidades | No implementado | Se aceptan definiciones para `opportunity`, pero no existe la tabla `opportunities` |
| Pagos | No implementado | `BILLING_MODE` valida configuración; no existen planes, checkout ni adaptador Payoneer |

## Arquitectura

### Estilo arquitectónico

El backend es un **monolito modular por capas**. Se despliega como una API y dos
procesos Celery que comparten el mismo código y la misma base PostgreSQL. No es un
conjunto de microservicios ni una implementación estricta de Clean Architecture.

Esta estructura se eligió por estas razones:

- El dominio aún está creciendo. Un monolito permite cambiar límites entre
  contactos, conversaciones, automatizaciones e IA sin coordinar despliegues ni
  contratos de red entre servicios prematuros.
- Registro, sesiones, configuración y auditoría necesitan transacciones que
  abarcan varias tablas. Una única base reduce fallos parciales y mantiene esas
  operaciones atómicas.
- Los canales externos, el correo y la futura IA son operaciones de entrada y
  salida. Celery las separa del tiempo de respuesta HTTP sin fragmentar el núcleo
  transaccional.
- La separación por responsabilidades mantiene reemplazables FastAPI, SMTP,
  Meta y los futuros proveedores de modelos sin organizar el dominio alrededor
  de una marca externa.
- Docker Compose ofrece el mismo conjunto mínimo de procesos en desarrollo:
  API, PostgreSQL, Redis, worker, scheduler y SMTP local.

La modularidad actual es una decisión de costo y evolución: mantiene el despliegue
sencillo, pero conserva fronteras internas para extraer un componente solo cuando
su carga, ciclo de cambios o aislamiento operacional lo justifique.

### Mapa de componentes

El siguiente diagrama muestra procesos y almacenes. PostgreSQL conserva el estado
de negocio; Redis transporta trabajo y resultados de Celery:

```mermaid
flowchart LR
    Client[Cliente HTTP] --> API[FastAPI /api/v1]
    API --> Auth[Autenticación y contexto tenant]
    API --> Services[Servicios de aplicación]
    Services --> Repositories[Repositorios]
    Services --> Outbox[Email outbox]
    Repositories --> PostgreSQL[(PostgreSQL)]
    Services --> PostgreSQL
    Outbox --> Worker[Celery worker]
    Worker --> SMTP[SMTP / Mailpit]
    Worker <--> Redis[(Redis)]
    Beat[Celery Beat] --> Redis
```

El código sigue este sentido general de dependencias:

```text
main
└── api
    ├── dependencies ──> core + db + models + services
    └── v1 routers ────> services + repositories + models

workers ───────────────> services + db
services ──────────────> core + models
repositories ──────────> core + models
models ────────────────> db.base
core ──────────────────> configuración y primitivas sin dominio HTTP
```

La dirección evita que un modelo SQLAlchemy conozca FastAPI o Celery. También
permite probar servicios y repositorios con una sesión asíncrona sin iniciar un
servidor HTTP.

### Responsabilidad de cada capa

Cada capa responde una pregunta distinta:

| Capa | Pregunta | Responsabilidad | No debe contener |
|---|---|---|---|
| `api` | ¿Cómo entra y sale una solicitud HTTP? | Rutas, esquemas Pydantic, códigos HTTP y dependencias | Integraciones remotas extensas o reglas transaccionales duplicadas |
| `core` | ¿Qué primitivas usa todo el proceso? | Configuración, criptografía, tokens, sanitización y contexto | Casos de uso de contactos, ventas o proveedores |
| `db` | ¿Cómo se abre y cierra una unidad de trabajo? | Engine, sesiones, commit, rollback y metadata | Reglas de negocio |
| `models` | ¿Qué invariantes persiste PostgreSQL? | Tablas, relaciones, índices, checks y estados | Validación HTTP o llamadas externas |
| `repositories` | ¿Cómo se consulta o persiste un agregado? | Consultas tenant-aware reutilizables | Códigos HTTP o coordinación de workers |
| `services` | ¿Qué operación de negocio debe ejecutarse? | Transacciones, autorización, tokens, outbox y políticas | Presentación HTTP |
| `workers` | ¿Qué trabajo continúa fuera de la solicitud? | Adaptación Celery y llamada a servicios reintentables | Reglas duplicadas respecto a `services` |
| `migrations` | ¿Cómo evoluciona un esquema existente? | DDL versionado, índices, constraints y triggers | Datos secretos o lógica de aplicación |

### Por qué se eligió cada componente

Las decisiones del stack responden a las características del CRM:

| Decisión | Motivo | Consecuencia operativa |
|---|---|---|
| FastAPI + Pydantic | El producto nace como API REST con OpenAPI y recibe muchas operaciones de entrada/salida | Los contratos y errores de validación se generan desde tipos Python |
| SQLAlchemy asíncrono | API, PostgreSQL y futuros proveedores son intensivos en espera de red | La ruta no bloquea el proceso mientras espera persistencia; el código debe evitar operaciones síncronas largas |
| PostgreSQL compartido | Se necesitan transacciones, relaciones fuertes, JSONB, locks y auditoría durable | Toda tabla de negocio debe preservar `tenant_id`; escalar exige medir antes de particionar |
| Redis + Celery | Correo, webhooks, sincronización e IA requieren reintentos y ejecución fuera de HTTP | Redis coordina entrega; no es la fuente de verdad del negocio |
| Celery Beat único | Los temporizadores y escaneos necesitan un único emisor de tareas periódicas | PostgreSQL debe conservar vencimientos y versiones; Beat no debe ser el único registro del tiempo pendiente |
| Patrón outbox | Un cambio de negocio y su intención externa deben confirmarse juntos | Un relay puede reintentar después de una caída sin perder la intención persistida |
| Alembic | El esquema incluye constraints y triggers que `create_all()` no reproduce como historial | Todo cambio persistente requiere una revisión versionada y reversible |
| Docker Compose | El desarrollo necesita servicios reproducibles sin depender de infraestructura cloud | Los adaptadores externos pueden permanecer simulados mientras se validan contratos locales |
| Base multiinquilino compartida | El producto debe soportar muchas empresas con operación inicial sencilla | El aislamiento depende de contexto, filtros, claves compuestas y pruebas negativas |
| UUID | Las entidades se crean en varios flujos y no deben depender de secuencias públicas | Los identificadores son transportables, pero no sustituyen controles de acceso |

### Estado durable y estado efímero

La arquitectura separa dos tipos de estado:

- PostgreSQL guarda identidades, membresías, sesiones, contactos, conversaciones,
  mensajes, outbox, configuración y auditoría. Una caída del worker no debe borrar
  este estado.
- Redis guarda mensajes de Celery y resultados operativos. El diseño no debe usar
  Redis como único registro de un webhook aceptado, un temporizador o un efecto de
  negocio.

Esta separación prepara los contratos de recuperación definidos en el PRD. La
implementación del inbox de webhooks, leases y temporizadores durables sigue
pendiente.

### Flujos entre capas

El registro empresarial recorre estas piezas:

```text
POST /auth/register
  -> api/v1/auth.py
  -> services/registration.py
  -> models Tenant + User + Membership
  -> EmailOutbox
  -> commit de una sola transacción
```

La actualización de configuración usa otro flujo:

```text
PUT /tenants/{tenant_id}/settings
  -> require_tenant_context + require_roles
  -> Tenant + TenantSettings
  -> services/audit.write_audit_event
  -> commit conjunto de configuración y auditoría
```

La entrega de correo se divide en dos unidades:

```text
caso de uso -> EmailOutbox(queued) -> commit
relay pendiente -> Celery email.deliver -> SMTP -> estado final del outbox
```

El hueco `relay pendiente` es intencionalmente visible: crear el outbox y ejecutar
la tarea ya están implementados, pero todavía no existe el proceso que los une.

### Límites actuales de la separación

La dirección de dependencias es una guía, no una propiedad completamente aplicada.
El código tiene estas excepciones conocidas:

- `services/authorization.py` importa dependencias FastAPI. La autorización de
  dominio y la adaptación HTTP deben separarse antes de reutilizar ese módulo
  desde workers.
- `repositories/contacts.py` invoca `services/custom_fields.py`. Esta dependencia
  funciona, pero mezcla acceso a datos con una política de aplicación; conviene
  mover la operación completa a un servicio de contactos cuando exista su API.
- Los esquemas Pydantic viven junto a cada router. Esta ubicación reduce archivos
  en el MVP; un esquema debe extraerse si lo comparten varios transportes.
- Algunos routers orquestan servicios y modelos directamente. No debe duplicarse
  esa lógica cuando se agreguen comandos desde workers o integraciones.

Estas excepciones explican por qué el repositorio se describe como monolito modular
por capas y no como Clean Architecture estricta.

### Flujo de una solicitud protegida

Una solicitud protegida atraviesa estas validaciones:

1. FastAPI extrae `Authorization: Bearer ACCESS_TOKEN`.
2. El backend valida firma, propósito, emisor, audiencia y vencimiento del JWT.
3. El backend comprueba que sesión, usuario y membresía sigan activos.
4. Para rutas de negocio, el backend exige un correo verificado.
5. El backend construye `TenantContext` con empresa, membresía, usuario y rol.
6. La ruta filtra sus consultas por `tenant_id` y aplica el rol requerido.
7. La sesión confirma la transacción al terminar; ante una excepción, la revierte.

## Tecnologías

`requirements.lock` fija las versiones instaladas:

| Componente | Tecnología | Versión |
|---|---|---|
| API | FastAPI | `0.116.1` |
| Servidor de interfaz asíncrona (ASGI) | Uvicorn | `0.35.0` |
| Mapeo objeto-relacional (ORM) | SQLAlchemy | `2.0.43` |
| Base de datos | PostgreSQL | imagen `17-alpine` |
| Driver | asyncpg | `0.30.0` |
| Migraciones | Alembic | `1.16.5` |
| Cola | Celery | `5.5.3` |
| Broker | Redis | imagen `7.4-alpine` |
| Validación | Pydantic | `2.11.7` |
| Contraseñas | Argon2 | `argon2-cffi 25.1.0` |
| MFA | PyOTP y Fernet | `2.9.0` y `cryptography 45.0.7` |
| Correo local | Mailpit | imagen `v1.27` |
| Pruebas | pytest | `8.4.1` |

Python debe ser `3.12` o `3.13`, según `requires-python = ">=3.12,<3.14"`.

## Ejecuta el proyecto con Docker

### Antes de comenzar

Necesitas:

- Docker Desktop con Docker Compose.
- PowerShell en Windows.
- Puertos `8000`, `8025` y `1025` libres.
- Python 3.12 o 3.13 solo para pruebas fuera de Docker.

`scripts/docker.ps1` localiza Docker Desktop aunque `docker.exe` no esté en
`PATH`.

### Inicia los servicios

1. Entra en el backend:

   ```powershell
   Set-Location "BACKEND_DIRECTORY"
   ```

   Sustituye `BACKEND_DIRECTORY` por la ruta completa de `omni-backend`.

2. Crea la configuración local:

   ```powershell
   if (-not (Test-Path .env.local)) {
     Copy-Item .env.example .env.local
   }
   ```

   Si `.env.local` ya existe, conserva sus valores. Git excluye todos los
   archivos `.env*` excepto `.env.example`.

3. Construye e inicia los servicios:

   ```powershell
   .\scripts\docker.ps1 compose up -d --build
   ```

4. Las migraciones se ejecutan automáticamente mediante el servicio `migrate` antes de que arranquen la API y los workers. Para ejecutarlas manualmente en un entorno ya iniciado:

   ```powershell
   .\scripts\docker.ps1 compose run --rm migrate
   ```

5. Comprueba los contenedores:

   ```powershell
   .\scripts\docker.ps1 compose ps
   ```

6. Comprueba la API:

   ```powershell
   Invoke-RestMethod http://localhost:8000/api/v1/health
   ```

   La respuesta contiene `status: ok`.

Los servicios quedan disponibles en estas direcciones:

| Servicio | Dirección desde el host | Uso |
|---|---|---|
| API | `http://localhost:8000` | Backend HTTP |
| Swagger UI | `http://localhost:8000/api/v1/docs` | Ejecutar endpoints |
| OpenAPI | `http://localhost:8000/api/v1/openapi.json` | Generar clientes |
| Mailpit | `http://localhost:8025` | Inspeccionar correo local |
| SMTP | `localhost:1025` | Entrada de Mailpit |
| PostgreSQL | Solo red interna, `postgres:5432` | Persistencia |
| Redis | Solo red interna, `redis:6379` | Celery |

Para detener los contenedores sin borrar los volúmenes, ejecuta:

```powershell
.\scripts\docker.ps1 compose down
```

## Configura el entorno

Pydantic carga `.env.local` sin distinguir mayúsculas y minúsculas. Los campos
desconocidos se ignoran. El backend acepta estas variables:

| Variable | Predeterminado | Descripción |
|---|---|---|
| `APP_ENV` | `local` | `local`, `test` o `production` |
| `APP_NAME` | `Omni CRM API` | Título OpenAPI |
| `APP_VERSION` | `0.1.0` | Versión OpenAPI |
| `DATABASE_URL` | PostgreSQL local | URL SQLAlchemy asíncrona |
| `REDIS_URL` | `redis://localhost:6379/0` | Broker y resultados Celery |
| `JWT_SECRET` | Secreto local | Firma SHA-256 con clave para tokens y recuperación MFA |
| `MFA_ENCRYPTION_KEY` | Clave local | Clave Fernet para secretos TOTP |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | Vigencia de acceso: 60–86.400 segundos |
| `CHALLENGE_TOKEN_TTL_SECONDS` | `300` | Vigencia MFA/selección: 60–1.800 segundos |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | Vigencia de sesión: 1–365 días |
| `BILLING_MODE` | `mock` | `mock` o `live`; no implementa un proveedor |
| `SMTP_HOST` | `localhost` | Host SMTP |
| `SMTP_PORT` | `1025` | Puerto SMTP |
| `SMTP_USERNAME` | vacío | Usuario; se configura junto con la contraseña |
| `SMTP_PASSWORD` | vacío | Contraseña; se configura junto con el usuario |
| `SMTP_TLS_MODE` | `none` | `none`, `starttls` o `tls` |
| `MAIL_FROM` | `no-reply@omni.local` | Remitente transaccional |
| `AUTH_PUBLIC_BASE_URL` | `http://localhost:3000` | Base de enlaces de autenticación |
| `META_APP_ID` | vacío | Reservado para la aplicación Meta |
| `META_APP_SECRET` | vacío | Reservado para Meta |
| `OPENAI_API_KEY` | vacío | Reservado; no hay cliente OpenAI conectado |
| `ANTHROPIC_API_KEY` | vacío | Reservado; no hay cliente Anthropic conectado |

No publiques `.env.local` ni copies secretos en logs, trazas, errores o auditoría.

### Controles de producción

Con `APP_ENV=production`, el proceso rechaza:

- `JWT_SECRET` vacío o reconocido como placeholder.
- La clave MFA local de ejemplo.
- `BILLING_MODE=mock`.
- Una sola de `SMTP_USERNAME` o `SMTP_PASSWORD` configurada.

`BILLING_MODE=live` supera la validación, pero no activa cobros: todavía no existe
un adaptador. Producción también requiere decidir AWS o Google Cloud, verificar
Meta/IA y resolver el bloqueo comercial de Payoneer.

## Autenticación y sesiones

### Registro empresarial

`POST /api/v1/auth/register` crea en una transacción:

- Empresa activa con zona `America/Bogota` e idioma `es-CO`.
- Usuario con contraseña Argon2 y correo normalizado.
- Membresía `administrador` activa.
- Fila `verify_email` en `email_outbox`.

La contraseña admite de 12 a 256 caracteres. El correo es único sin distinguir
mayúsculas. Una colisión devuelve `EMAIL_ALREADY_REGISTERED` sin datos parciales.

Para registrar una empresa, ejecuta:

```powershell
$registration = @{
  admin_name = "Ana Pérez"
  email = "ana@example.test"
  password = "correct horse battery staple"
  company_name = "Empresa Demo"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/auth/register `
  -ContentType application/json `
  -Body $registration
```

### Inicio de sesión

`POST /api/v1/auth/login` devuelve uno de estos valores en `next_step`:

| Estado | Condición | Siguiente acción |
|---|---|---|
| `authenticated` | MFA desactivado y una membresía activa | Usa acceso y conserva refresh |
| `mfa_required` | MFA activado | Envía código y desafío a `/auth/mfa/verify` |
| `tenant_selection` | Varias membresías activas | Lista membresías y selecciona empresa |

Usuario inexistente y contraseña incorrecta devuelven `INVALID_CREDENTIALS` para
reducir la enumeración de cuentas.

### Selección multiempresa

El desafío `tenant_selection` no autoriza rutas de negocio. Solo permite listar
membresías activas y elegir una empresa. `/auth/select-tenant` crea una sesión
vinculada a `user_id`, `membership_id` y `tenant_id`.

### Tokens y revocación

Los JWT usan `HS256`, emisor `omni-backend`, audiencia `omni-api`, identificador
único y propósito explícito. El acceso incluye sesión, empresa y membresía.

Los refresh tokens son secretos opacos con prefijo `rt.`; PostgreSQL conserva solo
su hash SHA-256. Cada uso consume el token y crea otro en la misma familia. Una
reutilización revoca la sesión y la familia con `REFRESH_REPLAY_DETECTED`.

Logout revoca la sesión y sus refresh tokens. Restablecer la contraseña revoca
todas las sesiones del usuario.

### Autenticación multifactor

El flujo TOTP es:

1. `/auth/mfa/enroll` devuelve secreto y URI de aprovisionamiento.
2. `/auth/mfa/confirm` verifica el primer código y entrega 10 códigos de recuperación.
3. `/auth/mfa/verify` acepta TOTP o recuperación no utilizada.
4. `/auth/mfa/disable` exige contraseña y segundo factor.

El secreto se cifra con Fernet. Los códigos de recuperación se guardan mediante
SHA-256 con clave y se consumen una vez.

## Aislamiento multiinquilino y autorización

`tenant_id` es una frontera de seguridad. Las rutas obtienen la empresa desde una
sesión validada; no confían en un identificador enviado libremente.

Las invariantes son:

- Sesión, usuario y membresía deben coincidir y estar activos.
- Una ruta con `{tenant_id}` rechaza otro identificador.
- Las consultas de negocio filtran por empresa.
- Conversaciones, contactos y activos usan claves compuestas con `tenant_id`.
- Un activo conectado tiene un único propietario por app Meta, canal e ID externo.
- Un worker revalida activo, estado y empresa antes de producir efectos.
- Administradores y supervisores pueden operar recursos asignables de su empresa.
- Un agente solo puede operar recursos asignados a su membresía. Este control aún
  no tiene routers de conversaciones que lo consuman.

La API implementada distribuye los permisos así:

| Operación | Administrador | Supervisor | Agente comercial |
|---|---|---|---|
| Leer configuración | Sí | Sí | Sí |
| Actualizar configuración | Sí | No | No |
| Leer campos personalizados | Sí | Sí | Sí |
| Escribir campos personalizados | Sí | No | No |
| Gestionar invitaciones | Sí | No | No |
| Crear otra empresa propia | Sí | Sí | Sí |

La tabla anterior describe solamente los endpoints que ya existen. La asignación
de conversaciones aún no está expuesta por HTTP.

## Correo transaccional

Registro, recuperación e invitaciones insertan una fila durable en
`email_outbox`. La tarea `email.deliver`:

- Usa confirmación tardía y rechaza el mensaje si el worker se pierde.
- Reintenta hasta cinco veces con backoff, limitado a 300 segundos.
- Bloquea la fila antes de cambiarla.
- No repite filas `sent`, `processing` o `unknown`.
- Genera el token de verificación al procesar `verify_email`.
- Marca `unknown` si hubo conexión SMTP y el resultado remoto no es seguro.

Los estados son `queued`, `processing`, `sent`, `failed` y `unknown`. No existe un
productor automático que publique todas las filas `queued` en Celery. El worker y
la entrega existen; ese enlace permanece pendiente.

Mailpit recibe mensajes en `localhost:1025` y los muestra en
`http://localhost:8025`.

## Campos personalizados

Una definición pertenece a una empresa y a `contact` u `opportunity`. El nombre
debe comenzar con letra y solo acepta letras, números y guion bajo.

| Tipo | Valor válido |
|---|---|
| `text` | Cadena |
| `number` | Entero o decimal, excepto booleanos |
| `boolean` | `true` o `false` |
| `date` | Fecha ISO `YYYY-MM-DD` |
| `select` | Una opción permitida |
| `multiselect` | Lista sin duplicados de opciones permitidas |

`select` y `multiselect` exigen opciones únicas. Los demás tipos las rechazan. El
servicio valida campos desconocidos, requeridos, tipos y opciones con definiciones
de la empresa activa.

Cambiar el tipo con valores existentes devuelve
`CUSTOM_FIELD_VALUE_MIGRATION_REQUIRED`. Eliminar esa definición exige
`?confirm_values=true` y genera auditoría.

## Configuración empresarial

`GET` y `PUT /api/v1/tenants/{tenant_id}/settings` gestionan:

- Nombre, zona horaria IANA e idioma.
- Apertura y cierre por día.
- Política `queue` o `auto_reply` fuera del horario.
- Correo, teléfono y dirección.
- `ai_enabled` y `automations_enabled`.

Los intervalos deben cerrar después de abrir y no pueden solaparse. `auto_reply`
exige mensaje. Todos los roles leen; solo administrador actualiza. Cada cambio
confirmado crea un `AuditEvent` con antes/después sanitizado.

## Auditoría y datos sensibles

`audit_events` es append-only por empresa. Guarda actor, acción, recurso, fecha y
metadatos sanitizados dentro de la transacción del caso de uso.

SQLAlchemy rechaza mutaciones del modelo. PostgreSQL añade el trigger
`audit_events_append_only`, que rechaza `UPDATE` y `DELETE` fuera del ORM.

El sanitizador recorre estructuras anidadas y redacta claves de contraseña,
token, secreto, credencial, autorización, cookie y API key. También reconoce JWT,
Bearer/Basic, patrones de credenciales, correos y teléfonos.

Eventos entrantes sin empresa resuelta usan `ingress_diagnostics`; no inventan un
tenant dentro de `audit_events`.

## Fundaciones de Meta e IA

### Activos Meta

`channel_assets` representa `whatsapp`, `messenger`, `instagram` y `ad_account`.
Guarda una referencia opaca a la credencial. La resolución usa app Meta, canal e
ID externo: desconocido o ambiguo se pone en cuarentena; único produce un
`IntegrationContext` que el worker revalida.

Esta capa no valida todavía firmas HTTP ni expone OAuth o webhooks.
`InMemoryCredentialStore` es volátil y solo sirve para desarrollo y pruebas.

### Inteligencia artificial

El modelo de conversaciones reserva:

- `ai_mode`: `active`, `handoff_pending` o `human`.
- `control_version`: versión para invalidar trabajo pendiente.
- `author_type=ai`: autor generado.
- `ai_enabled`: interruptor por empresa.

No existe un grafo LangGraph, cadena LangChain, cliente de modelos, memoria,
herramientas, recuperación de contexto ni despacho IA. Configurar una clave no
activa IA.

La futura capa debe comprobar `ai_mode` y `control_version` justo antes del
despacho. Así, una toma humana invalida una respuesta aún no enviada. Un mensaje
ya aceptado por el proveedor no puede retirarse.

## Modelo de datos

El esquema contiene:

| Tabla | Responsabilidad |
|---|---|
| `tenants` | Empresa, slug, zona, idioma, estado y plan |
| `users` | Identidad, contraseña, estado, verificación y MFA |
| `memberships` | Usuario-empresa con rol y estado |
| `auth_sessions` | Sesión vinculada a usuario, membresía y empresa |
| `refresh_tokens` | Rotación, consumo, revocación y hash |
| `email_verification_tokens` | Verificación hasheada, vencimiento y uso |
| `password_reset_tokens` | Recuperación hasheada, vencimiento y uso |
| `mfa_recovery_codes` | Recuperación MFA hasheada y de un uso |
| `invitations` | Invitación, rol, estado y vencimiento |
| `email_outbox` | Intención y estado de correo |
| `channel_assets` | Activos y referencias de credenciales |
| `custom_field_definitions` | Campos por empresa y entidad |
| `contacts` | Contacto, origen, responsable, etiquetas y campos |
| `conversations` | Contacto, activo, asignación y control humano/IA |
| `messages` | Dirección, autor, contenido, estado y cronología |
| `tenant_settings` | Horarios, políticas, contacto e interruptores |
| `audit_events` | Auditoría inmutable por empresa |
| `ingress_diagnostics` | Diagnóstico previo a resolver empresa |

Las restricciones de base de datos aceptan estos estados:

| Entidad | Estados válidos |
|---|---|
| Empresa | `active`, `suspended`, `cancelled` |
| Usuario | `active`, `inactive`, `blocked` |
| Membresía | `invited`, `active`, `inactive` |
| Sesión | `active`, `revoked` |
| Invitación | `pending`, `accepted`, `revoked`, `expired` |
| Activo | `connected`, `disconnected`, `error` |
| Contacto | `active`, `archived`, `deleted` |
| Conversación | `open`, `pending`, `closed` |
| Modo IA | `active`, `handoff_pending`, `human` |
| Mensaje | `queued`, `dispatching`, `sent`, `delivered`, `read`, `failed`, `unknown`, `cancelled` |
| Outbox | `queued`, `processing`, `sent`, `failed`, `unknown` |

## Referencia de API

Todas las rutas usan `/api/v1`. En esta tabla, Tenant significa identidad
verificada y membresía activa; Administrador añade ese rol.

| Método | Ruta | Acceso | Resultado |
|---|---|---|---|
| `GET` | `/health` | Público | Salud de la API |
| `POST` | `/auth/register` | Público | Registra empresa y administrador |
| `GET` | `/auth/verify-email?token=...` | Público | Consume verificación |
| `POST` | `/auth/login` | Público | Autentica o inicia desafío |
| `GET` | `/auth/memberships` | Desafío o sesión | Lista empresas activas |
| `POST` | `/auth/select-tenant` | Desafío o sesión | Crea sesión para una empresa |
| `POST` | `/auth/refresh` | Refresh token | Rota refresh y acceso |
| `POST` | `/auth/logout` | Sesión | Revoca sesión |
| `POST` | `/auth/forgot-password` | Público | Encola recuperación neutral |
| `POST` | `/auth/reset-password` | Token de recuperación | Cambia contraseña |
| `POST` | `/auth/mfa/enroll` | Sesión | Genera secreto TOTP |
| `POST` | `/auth/mfa/confirm` | Sesión | Activa MFA |
| `POST` | `/auth/mfa/disable` | Sesión | Desactiva MFA |
| `POST` | `/auth/mfa/verify` | Desafío MFA | Continúa login |
| `POST` | `/tenants` | Identidad verificada | Crea otra empresa |
| `POST` | `/tenants/{tenant_id}/invitations` | Administrador | Invita miembro |
| `GET` | `/invitations/{token}` | Público | Lee invitación pendiente |
| `POST` | `/invitations/{token}/accept` | Público | Acepta invitación |
| `DELETE` | `/tenants/{tenant_id}/invitations/{invitation_id}` | Administrador | Revoca invitación |
| `GET` | `/tenants/{tenant_id}/settings` | Tenant | Lee configuración |
| `PUT` | `/tenants/{tenant_id}/settings` | Administrador | Reemplaza y audita configuración |
| `GET` | `/custom-fields` | Tenant | Lista; acepta `entity_type` |
| `POST` | `/custom-fields` | Administrador | Crea definición |
| `GET` | `/custom-fields/{definition_id}` | Tenant | Lee definición propia |
| `PATCH` | `/custom-fields/{definition_id}` | Administrador | Modifica definición |
| `DELETE` | `/custom-fields/{definition_id}` | Administrador | Elimina definición |

Swagger y OpenAPI documentan esquemas y respuestas `422`. Este README explica los
contratos de seguridad y dominio que no aparecen en el esquema.

Los errores de dominio usan esta forma:

```json
{
  "detail": {
    "code": "ERROR_CODE"
  }
}
```

## Ejecuta migraciones

Alembic obtiene `DATABASE_URL` de la aplicación. Para inspeccionar y aplicar el
historial, ejecuta:

```powershell
.\scripts\docker.ps1 compose exec -T app alembic current
.\scripts\docker.ps1 compose exec -T app alembic history
.\scripts\docker.ps1 compose exec -T app alembic upgrade head
```

La cadena va de `0001_baseline` a `0015_tenant_settings`. No sustituyas Alembic
con `Base.metadata.create_all()` en persistencia: los triggers se crean por
migración.

## Ejecuta las pruebas

Para preparar Python local, ejecuta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
```

La suite predeterminada usa SQLite asíncrono:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Dos pruebas PostgreSQL se omiten sin `TEST_DATABASE_URL`. Validan registro y
rotación de refresh concurrentes.

**Precaución:** Las pruebas de integración eliminan y recrean todas las tablas de
`TEST_DATABASE_URL`. Usa una base exclusiva, nunca desarrollo o producción.

1. Crea una base desechable:

   ```powershell
   .\scripts\docker.ps1 compose exec -T postgres `
     createdb -U omni omni_test
   ```

2. Ejecuta la integración en `app`:

   ```powershell
   $testDatabaseUrl = `
     "postgresql+asyncpg://omni:omni@postgres:5432/omni_test"

   .\scripts\docker.ps1 compose exec -T `
     -e "TEST_DATABASE_URL=$testDatabaseUrl" `
     app pytest tests/integration
   ```

El resultado esperado son dos pruebas aprobadas.

## Diagnostica el entorno

Para seguir logs, ejecuta:

```powershell
.\scripts\docker.ps1 compose logs -f app worker beat
```

| Síntoma | Causa probable | Corrección |
|---|---|---|
| `docker` no aparece en `PATH` | Se usó Docker directamente | Usa `scripts/docker.ps1` |
| La API responde, pero fallan consultas | Alembic no está en `head` | Ejecuta `alembic upgrade head` |
| El puerto `8000` está ocupado | Otro proceso lo publica | Libera o cambia el mapeo |
| No aparece correo en Mailpit | Outbox queda `queued` | Comprueba outbox; falta despacho automático |
| `EMAIL_NOT_VERIFIED` | El correo no se verificó | Consume la verificación |
| `MEMBERSHIP_INACTIVE` | La membresía fue desactivada | Usa una membresía activa |
| `REFRESH_REPLAY_DETECTED` | El refresh ya fue consumido | Inicia sesión de nuevo |

## Estructura del repositorio

El árbol siguiente muestra los módulos ejecutables y la responsabilidad concreta
de cada archivo, no solo sus carpetas:

```text
omni-backend/
├── app/
│   ├── main.py                         # Fábrica FastAPI y montaje /api/v1
│   ├── api/
│   │   ├── dependencies.py             # Bearer, identidad y TenantContext
│   │   └── v1/
│   │       ├── router.py               # Composición de routers y /health
│   │       ├── auth.py                 # Registro, login, sesiones, reset y MFA
│   │       ├── tenants.py              # Creación de empresas adicionales
│   │       ├── invitations.py          # Invitación, aceptación y revocación
│   │       ├── settings.py             # Configuración de la empresa
│   │       └── custom_fields.py        # CRUD de definiciones personalizadas
│   ├── core/
│   │   ├── config.py                   # Settings y controles de producción
│   │   ├── route_policy.py             # Inventario explícito de rutas públicas
│   │   ├── sanitization.py             # Redacción recursiva de secretos y PII
│   │   ├── security.py                 # Hash y verificación Argon2
│   │   ├── tenant_context.py           # Contextos humano e integración
│   │   └── tokens.py                   # Emisión y validación JWT
│   ├── db/
│   │   ├── base.py                     # Base, convenciones y mixins SQLAlchemy
│   │   └── session.py                  # Engine, factory y ciclo transaccional
│   ├── models/
│   │   ├── identity.py                 # Tenant, User, sesiones, correo y activos
│   │   ├── crm.py                      # Campos, contactos, conversaciones, mensajes
│   │   └── operations.py               # Auditoría, diagnóstico y configuración
│   ├── repositories/
│   │   ├── memberships.py              # Consultas de membresías
│   │   └── contacts.py                 # Escrituras tenant-aware de contactos
│   ├── services/
│   │   ├── registration.py             # Alta atómica de empresa e identidad
│   │   ├── sessions.py                 # Sesiones y rotación de refresh
│   │   ├── password_reset.py           # Recuperación y revocación de sesiones
│   │   ├── mfa.py                      # TOTP, cifrado y recuperación
│   │   ├── invitations.py              # Ciclo de invitaciones
│   │   ├── email_verification.py       # Tokens de verificación de correo
│   │   ├── email.py                    # Adaptador SMTP
│   │   ├── email_outbox.py             # Estado y entrega del outbox
│   │   ├── authorization.py            # Roles y recursos asignados
│   │   ├── custom_fields.py            # Validación tipada de valores
│   │   ├── credentials.py              # Puerto y store volátil de secretos
│   │   ├── asset_routing.py            # Resolución de activos receptores
│   │   ├── integration_context.py      # Contexto y envelope de workers
│   │   └── audit.py                    # Escritor append-only transaccional
│   └── workers/
│       ├── celery_app.py                # Broker, resultados y política de ACK
│       └── email_tasks.py               # Adaptador Celery para email.deliver
├── migrations/
│   ├── env.py                           # Alembic asíncrono y metadata
│   └── versions/                        # Revisiones 0001–0015
├── tests/
│   ├── integration/                     # Carreras reales en PostgreSQL
│   ├── support/                         # Fixtures de aislamiento tenant
│   └── test_*.py                        # Pruebas por capacidad
├── docs/readiness.md                    # Evidencia del entorno local
├── scripts/docker.ps1                   # Resolución local de Docker Desktop
├── compose.yaml                         # Seis servicios locales
├── Dockerfile                           # Imagen Python con usuario no-root
├── alembic.ini                          # Configuración de migraciones
├── pyproject.toml                       # Paquete y configuración pytest
├── requirements.in                      # Dependencias directas editables
├── requirements.lock                    # Dependencias reproducibles
├── .env.example                         # Contrato de configuración local
└── AGENTS.md                            # Reglas para agentes de desarrollo
```

El directorio padre contiene especificación y backlog. `omni-backend/` es el
repositorio de implementación.

### Criterio para ubicar código nuevo

Usa esta guía antes de crear un módulo:

| Si el cambio... | Ubícalo en... | Porque... |
|---|---|---|
| Expone una operación HTTP | `app/api/v1/` | El transporte y sus esquemas permanecen en el borde |
| Define una regla o coordina una transacción | `app/services/` | El caso de uso puede reutilizarse desde API o worker |
| Encapsula una consulta repetida | `app/repositories/` | El filtro tenant y la forma de persistencia quedan centralizados |
| Agrega una tabla o invariant persistente | `app/models/` + `migrations/` | Modelo y evolución de una base existente avanzan juntos |
| Integra un proveedor remoto | Un adaptador detrás de un protocolo en `services/` | El dominio no queda acoplado al SDK del proveedor |
| Ejecuta trabajo en segundo plano | Adaptador en `app/workers/` y lógica en `services/` | Los reintentos de Celery no duplican reglas de negocio |
| Agrega una primitiva transversal | `app/core/` | Configuración, seguridad y contexto quedan fuera de un dominio concreto |

No crees una carpeta por proveedor que mezcle rutas, reglas, persistencia y
workers. Separa el puerto del adaptador: por ejemplo, la futura integración Meta
necesita contratos de credenciales y mensajería, un adaptador Meta y casos de uso
de canales que no conozcan detalles HTTP del proveedor.

### Relación entre código y pruebas

Las pruebas se organizan por capacidad, no como una copia exacta de carpetas:

- `test_*_api.py` verifica contratos HTTP, autenticación y códigos de error.
- Las pruebas de servicios validan reglas sin levantar un servidor.
- `test_tenant_isolation_support.py` y `tests/support/` ofrecen escenarios de dos
  empresas para negar acceso cruzado y acceso sin asignación.
- `tests/integration/` usa PostgreSQL para carreras que SQLite no representa,
  como unicidad y consumo concurrente de refresh tokens.

Esta distribución prioriza el comportamiento observable. Cuando una capacidad
atraviesa router, servicio y modelo, su prueba permanece junto al nombre de la
capacidad en vez de fragmentarse por capa.

## Limitaciones conocidas

Estas limitaciones se derivan del código y deben resolverse antes de considerar
el backend listo para producción:

- `/health` solo confirma que el proceso HTTP responde; no consulta PostgreSQL,
  Redis, SMTP ni workers.
- La validación de sesión comprueba sesión, usuario y membresía, pero todavía no
  rechaza una empresa con estado `suspended` o `cancelled`.
- La autorización de recursos asignables usa `assignee_membership_id`, mientras
  `Conversation` persiste `assigned_user_id`; no conectes el helper a ese modelo
  hasta unificar el identificador.
- Celery Beat se ejecuta sin una agenda configurada.
- El outbox no publica automáticamente tareas `email.deliver`.
- La auditoría está conectada a configuración empresarial y campos
  personalizados, no a todos los casos de uso de identidad.
- No hay limitación de tráfico, intercambio de recursos de origen cruzado
  explícito, métricas, tracing distribuido ni endpoint de readiness profundo.
- No existen routers HTTP para contactos, activos, conversaciones o mensajes.
- La lista de campos personalizados no implementa paginación.
- Las credenciales Meta/IA no se validan al iniciar producción.
- No existe almacén durable de secretos; `InMemoryCredentialStore` pierde datos al
  reiniciar el proceso.

## Extiende el backend

Antes de implementar una tarea:

1. Lee `../.agent/tasks/TASK-N.json`.
2. Revisa `acceptanceCriteria`, `dependencies` y `contractRef`.
3. Contrasta el comportamiento con el PRD.
4. Conserva `tenant_id` en consultas, relaciones, eventos y workers.
5. Separa idempotencia local, ejecución y aceptación del proveedor.
6. Audita efectos sensibles en la misma transacción.
7. Sanitiza metadatos antes de logs, trazas, auditoría o IA.
8. Añade pruebas de permisos, aislamiento, errores y concurrencia.
9. Ejecuta pruebas y migraciones antes de cerrar la tarea.

Define contratos y adaptadores antes de integrar proveedores. Conserva estado
durable en PostgreSQL y ejecuta trabajo recuperable con Celery.

## Documentación relacionada

- [PRD](../.agent/prd/PRD.md): alcance y contratos.
- [Resumen](../.agent/prd/SUMMARY.md): decisiones principales.
- [Correcciones](../.agent/prd/CORRECTIONS.md): hallazgos resueltos.
- [Validación](../.agent/prd/VALIDATION.md): trazabilidad.
- [Bloqueo de Payoneer](../.agent/prd/PAYONEER-GATE.md): condición de pagos.
- [Preparación local](docs/readiness.md): herramientas verificadas.
- [Instrucciones para agentes](AGENTS.md): invariantes del repositorio.

## Trabajo pendiente

El backlog incluye:

- OAuth y administración de activos Meta.
- Verificación, persistencia, deduplicación y recuperación de webhooks.
- APIs de contactos, conversaciones, mensajes, campañas y oportunidades.
- Toma humana e invalidación de respuestas IA.
- LangChain, LangGraph, herramientas seguras y trazabilidad IA.
- Automatizaciones `customer_unanswered` y `team_unanswered`.
- Planes, cuotas, suscripciones y pagos simulados.
- Pruebas de carga y objetivos operativos del PRD.

Estas capacidades no forman parte de la API ejecutable documentada aquí.
