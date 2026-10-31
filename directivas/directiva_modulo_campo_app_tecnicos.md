# SOP — Módulo Campo + App de Técnicos

> **Procedimiento Operativo Estándar y Arquitectura de Dominio**  
> Dominio operativo `campo` en Django SaaS + Aplicación móvil Flutter independiente en `apps/tecnicos-mobile/`.

---

## 1. Objetivo y Alcance

Construir el dominio operativo **Campo** dentro del backend Django SaaS existente y una aplicación móvil independiente para técnicos (`apps/tecnicos-mobile/`).

La plataforma es **SaaS Multi-tenant**:
- **Cero acoplamiento**: La app móvil no contiene lógica cableada (*hardcoded*) de FTTH, WispHub, SmartOLT ni Rapilink.
- **Esquema dinámico**: El backend declara el tipo de trabajo, la versión inmutable de la plantilla, los pasos, campos y evidencias exigidas. La app móvil renderiza dinámicamente según `schema_version`.
- **Canal seguro**: La app móvil solo habla con la API REST de Django con autenticación JWT de la organización; nunca accede a Postgres directamente ni a APIs de terceros.

---

## 2. Entidades Centrales del Dominio (`campo/models.py`)

### 2.1 Tipos de Trabajo y Versionado Inmutable
1. `WorkType`: Catálogo por organización (`org`, `codigo`, `nombre`, `activo`).
2. `WorkTypeVersion`:
   - Campos: `work_type`, `version`, `schema_version` (ej. 1), `estado` (`BORRADOR`, `PUBLICADA`, `RETIRADA`), `esquema` (JSON), `schema_hash` (SHA256 del esquema al publicar), `publicada_en`, `creado_en`.
   - **Regla Inamovible**:
     - `BORRADOR` -> se puede editar.
     - `PUBLICADA` -> inmutable. Únicamente puede cambiar de estado a `RETIRADA`. Cualquier intento de alterar campos de esquema lanza `ValidationError`.
     - **Inmutabilidad de Dominio y ORM**: Inmutabilidad garantizada por dominio, `clean()`, `save()` y `WorkTypeVersionQuerySet.update()`. Escrituras directas por ORM quedan interceptadas y prohibidas.
     - Para modificar una plantilla, se crea la versión $N+1$.
   - **Vocabulario de Esquema (`schema_version=1`)**:
     - Tipos de campo: `texto`, `entero`, `decimal`, `booleano`, `seleccion`, `fecha`, `foto`, `documento`.
     - Reglas soportadas: `required`, `min`, `max`, `regex`, `options`.

### 2.2 Orden de Trabajo (`OrdenTrabajo`)
Abstracción unificada para cualquier tarea de campo (Instalación, Correctivo, Mantenimiento, Retiro).
- `org`: Organización tenant (`ForeignKey` a `common.Org`).
- `numero`: Consecutivo entero por organización.
- `tipo_trabajo_version`: `ForeignKey` a `WorkTypeVersion`.
- **Origen Inequívoco Desacoplado**:
  - `origen_sistema`: `wisphub` | `solicitudes` | `crm` | `manual`.
  - `origen_tipo`: `ticket` | `solicitud` | `case` | `orden_manual`.
  - `origen_ref`: Identificador externo (ej. `91288`, UUID).
  - **Restricción de No-Duplicación**: `UniqueConstraint(fields=['org', 'origen_sistema', 'origen_tipo', 'origen_ref'], condition=~Q(origen_sistema='manual'))` para evitar órdenes duplicadas del mismo ticket o solicitud.
- **Asignación y Cuadrilla (Única Fuente de Verdad)**:
  - Sin duplicación de FK: `tecnico_principal` es una propiedad calculada desde `AsignacionTrabajo`.
  - Tabla `AsignacionTrabajo(orden, profile, rol, es_principal, asignado_en)`:
    - Restricción: `UniqueConstraint(fields=['orden'], condition=Q(es_principal=True), name='unique_tecnico_principal_por_orden')`.
- **Datos del Cliente y Ubicación**:
  - `cliente_nombre`, `cliente_telefono`, `cliente_direccion`, `gps_lat`, `gps_lng`.
- **Contexto Operativo y Datos Técnicos**:
  - `diagnostico_previo`: JSON con el diagnóstico técnico previo de IA en WhatsApp (si vino de ticket).
  - `datos`: `JSONField(default=dict)` donde se persisten los valores técnicos (`serial_ont`, `potencia_rx`, `nap`, `puerto`).
  - `revision`: `PositiveIntegerField(default=1)` para control de concurrencia optimista offline.
- **Separación Estricta de Estados**:
  - `estado_operativo`: `asignada` | `en_camino` | `en_sitio` | `completada_campo` | `cerrada` | `cancelada`.
  - `estado_validacion`: `sin_evaluar` | `pendiente` | `aprobable` | `requiere_correccion` | `requiere_revision` | `aprobado`.
- `iniciada_en`, `completada_campo_en`, `cerrada_en`.

### 2.3 Historial Operativo Append-Only (`EventoTrabajo`)
Bitácora inmutable de eventos para auditoría de campo:
- `org`, `orden`, `tipo`, `profile`, `datos` (JSON), `creado_en`.
- Tipos de eventos: `orden_creada`, `tecnico_asignado`, `trabajo_iniciado`, `llegada_registrada`, `datos_actualizados`, `evidencia_agregada`, `trabajo_completado`, `trabajo_cancelado`.

### 2.4 Evidencias de Campo (`EvidenciaTrabajo`)
Almacenamiento durable independiente de `asistente.media`:
- `org`, `orden_trabajo`, `requisito_id`.
- **Regla dura**: `requisito_id` DEBE existir en los requisitos declarados por el `tipo_trabajo_version` de esa orden.
- `storage_key`, `nombre_original`, `mime_type`, `bytes`, `sha256`.
- `estado_archivo`: `pendiente` | `subiendo` | `recibido` | `verificado` | `fallido`.
- `capturada_en_cliente`: Timestamp del reloj del teléfono móvil (metadato).
- `recibida_en_servidor`: Timestamp del servidor.
- `metadatos_captura`: JSON (GPS capturado, modelo dispositivo, etc.).
- Abstracción `CampoStorage` desacoplada para emisión de URLs de subida y lectura.

### 2.5 Idempotencia Robusta con Control de Concurrencia (`MutacionIdempotente`)
- `org`, `idempotency_key` (UUID/string).
- `http_method`, `endpoint`, `request_hash` (SHA256 sobre JSON canónico ordenado).
- `status_code`, `respuesta_json`.
- `estado`: `PROCESANDO` | `COMPLETADA`.
- **Reglas de Guarda**:
  - `UNIQUE(org, idempotency_key)` en BD.
  - Si llega otra request con la misma key y está `PROCESANDO` -> Retorna `409 Conflict` (`OPERACION_EN_CURSO`).
  - Si está `COMPLETADA` y el `request_hash` coincide -> Devuelve respuesta cacheada con cabecera `Idempotent-Replay: true`.
  - Misma `idempotency_key` + distinto `request_hash` -> Retorna `409 Conflict` (`IDEMPOTENCY_KEY_REUSED`).
  - Todo bajo `transaction.atomic()`. Si la mutación lanza excepción, se hace rollback y no se guarda falso éxito.

---

## 3. Máquina de Estados y Separación de Puertas de Cierre (`campo/services/transiciones.py`)

```text
asignada ──► en_camino ──► en_sitio ──► completada_campo ──► cerrada
    │            │             │
    └────────────┴─────────────┴──────► cancelada
```

- **Endpoint `/acciones/`**: Sólo transiciones operativas de progreso (`iniciar`, `marcar_en_camino`, `marcar_llegada`, `cancelar`).
- **Endpoint `/completar/`**: Única puerta de cierre de campo (`completada_campo`). Ejecuta validación estricta de:
  1. Todos los campos obligatorios presentes y válidos en `orden.datos`.
  2. Todas las evidencias obligatorias recibidas y verificadas en `EvidenciaTrabajo`.
- **Fase 1**: `completada_campo` finaliza la orden en campo pero **NO cierra WispHub ni CRM automáticamente**.

---

## 4. Matriz de Permisos (`campo/permissions.py`)

Dentro de la misma organización:
- **Técnico**: Solo puede listar y mutar órdenes donde esté asignado en `AsignacionTrabajo`.
- **Supervisor**: Puede ver todas las órdenes de la organización, asignar/reasignar cuadrillas y cancelar/cerrar.
- **Administrador**: Gestión de plantillas `WorkType` y `WorkTypeVersion`.
- **Multi-Tenant**: Acceso a recursos de otra organización devuelve **404 Not Found** estricto.

---

## 5. Batería de Pruebas Automatizadas Obligatorias

1. `test_modelos_e_inmutabilidad.py`: Inmutabilidad (save + update), origen externo único, cuadrilla con `es_principal=True` único y eventos append-only.
2. `test_transiciones_y_checklist.py`: Máquina de estados, transiciones operativas, validador de datos y requisitos de checklist.
3. `test_idempotencia_api.py`: Replay exacto, hash canónico JSON, detección de reuso 409 y colisión en curso.
4. `test_concurrencia_idempotencia_real.py`: 5 requests concurrentes simultáneos con misma Idempotency-Key -> 1 sola ejecución en BD, cero duplicados.
5. `test_revision_concurrente_offline.py`: Conflicto offline 409 STALE_WORK_ORDER ante mismo campo modificado y merge no destructivo ante campos disjuntos.
6. `test_storage_ciclo_completo.py`: Ciclo de evidencias: crear intención -> upload firmado -> rechazo si archivo no existe -> confirmación tras subida física -> 404 para tenant ajeno -> 200 download URL para propio.
7. `test_aislamiento_tenant_404.py`: Aislamiento multi-tenant 404 estricto y matriz de permisos técnicos vs supervisores.
8. `test_vertical_slice_api.py`: Flujo end-to-end de la jornada del técnico por API REST.

---

## 6. Especificación de la Aplicación Móvil (`apps/tecnicos-mobile/`)

### 6.1 Principios de Diseño Móvil
1. **Contrato Dinámico Inamovible**: La app móvil NUNCA codifica tipos de trabajo, nombres de campos o reglas fijas en código Dart. Renderiza dinámicamente según el esquema recibido en `schema_version=1`.
2. **Offline-First Radical**: Toda interacción del técnico (iniciar camino, llegar, guardar campo, tomar foto, completar) se persiste.

### Trampas Conocidas y Reglas Inamovibles de Contrato (Verificadas en Código)
1. **Contrato de PATCH `/api/campo/trabajos/<id>/datos/`**:
   - `revision_base` viaja OBLIGATORIAMENTE adentro del JSON en el payload: `{"revision_base": N, "valores": {...}}`.
   - **Prohibido usar encabezado `X-Revision-Base`**; el serializer `GuardarDatosSerializer` no lo lee.
2. **Propósito de `GET /api/campo/evidencias/<id>/url/`**:
   - Este endpoint está implementado en `ObtenerUrlEvidenciaView` y devuelve una **URL segura de DESCARGA / visualización** (`download_url`).
   - **No usar para renovar upload**.
3. **Renovación de Signed URL para Upload**:
   - Si la URL de subida expira o se pierde la respuesta inicial, el cliente reintenta `POST /api/campo/trabajos/<id>/evidencias/` con el mismo `requisito_id` y `sha256`.
   - Físicamente, el modelo `EvidenciaTrabajo` posee `UniqueConstraint(fields=["orden_trabajo", "requisito_id", "sha256"], name="unique_evidencia_requisito_sha")` y la vista ejecuta `update_or_create`. Esto garantiza que una reconexión jamás cree un registro duplicado (ej. evidencia #42).
4. **Idempotencia en Confirmación de Evidencias**:
   - `ConfirmarEvidenciaView` verifica si la evidencia ya fue recibida (`RECIBIDO` o `VERIFICADO`) y devuelve inmediatamente `200 OK` sin duplicar filas en `EventoTrabajo`.
5. **Nombre Comercial del Producto**:
   - Se denomina **Dexter IA** tanto en la UI móvil como en el ecosistema de campo. Identificador de paquete móvil: `com.dexter.campo`.
6. **Aislamiento de Claves de Idempotencia por Endpoint (`IDEMPOTENCY_KEY_REUSED`)**:
   - El servicio de idempotencia en backend (`campo/services/idempotencia.py`) valida estrictamente que si una `Idempotency-Key` ya existe en la organización, el `endpoint` y el hash de la petición deben coincidir exactamente.
   - Si el cliente envía la misma `Idempotency-Key` (por ejemplo, el UUID local de la evidencia) tanto para el registro inicial `POST /api/campo/trabajos/<id>/evidencias/` como para la confirmación posterior `POST /api/campo/evidencias/<id>/confirmar/`, el backend responde inmediatamente con `409 Conflict: IDEMPOTENCY_KEY_REUSED` ("La misma Idempotency-Key fue reutilizada con un payload o método diferente").
   - Solución inamovible: Toda operación HTTP distinta debe generar un token de idempotencia diferenciado por propósito (ej. `$id` para registro y `${id}_confirm` para confirmación).

### 6.2 Alcance del Primer Vertical Slice Móvil (4 Pantallas)
1. **Pantalla 1 — Login**:
   - Autenticación real contra `POST /api/token/`.
   - Almacenamiento seguro de `access_token`, `refresh_token`, tenant y perfil en `flutter_secure_storage`.
   - Interceptor HTTP que adjunta `Bearer token` y recupera sesión automáticamente ante 401.
2. **Pantalla 2 — Mi Jornada**:
   - Consume `GET /api/campo/trabajos/`.
   - Agrupación operacional del día (Asignadas, En camino, En sitio, Completadas).
   - Indicadores claros de sincronización local vs remota.
3. **Pantalla 3 — Detalle de Orden**:
   - Consume `GET /api/campo/trabajos/<id>/`.
   - Ficha del cliente, dirección, contacto, diagnóstico técnico previo de IA.
   - Botón principal de transición operacional (*"Iniciar desplazamiento"* / *"Marcar llegada"*).
4. **Pantalla 4 — Ejecución Dinámica (Formulario y Evidencias)**:
   - Renderiza dinámicamente los campos declarados en `esquema.campos` (ej. texto, decimal con validación min/max).
   - Renderiza los requisitos de fotos declarados en `esquema.evidencias`.
   - Subida y almacenamiento local de capturas con confirmación diferida.
   - Botón *"Completar trabajo"* validando checklist local antes de mutar estado a `completada_campo`.

---

## 7. Panel de Administración Web (`campo/admin.py`)

Las órdenes de trabajo y plantillas de campo quedan expuestas en el panel de administración web de Django (`/admin/`):
- **`OrdenTrabajoAdmin`**:
  - Visualización con badges de colores para `estado_operativo` y `estado_validacion`.
  - Muestra el técnico principal calculado desde `AsignacionTrabajo`.
  - Inlines tabulares: técnicos asignados (`AsignacionTrabajoInline`), evidencias fotográficas (`EvidenciaTrabajoInline`) y bitácora inmutable de eventos (`EventoTrabajoInline`).
  - Filtros por estado, organización, origen y tipo de trabajo.
- **`WorkTypeAdmin`** y **`WorkTypeVersionAdmin`**: Catálogo de tipos de trabajo y versiones inmutables.
- **`EvidenciaTrabajoAdmin`**: Lista de evidencias recibidas con estados de archivo y peso en bytes.
