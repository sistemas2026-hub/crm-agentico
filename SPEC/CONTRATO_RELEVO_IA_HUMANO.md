# Contrato del relevo IA ↔ humano

**Versión:** 2.5 (16/09/2026): v2.4 + B3.3b (la compuerta del modelo lee `control_efectivo` de la base en cada turno, falla cerrado; T8 Intervenir) y G1/G9 en verde en producción. **Estado: CERRADO como arquitectura** después de dos rondas de auditoría. Autoriza preparar la implementación por fases (§15) en `feature/bandeja-relevo`, **sin push a producción**. Cada fase vuelve a auditoría antes de integrarse.
**Commit base:** `92ebe78` (`origin/fix/integracion-wisphub`, verificado con `git fetch` el 16/09/2026).
**Alcance:** la bandeja de conversaciones (PRD §8.11) y lo que el motor hace con una conversación mientras la atiende la IA, una persona o nadie.

### Cómo leer las marcas
- **[VERIFICADO]**: leído directamente en el código base.
- **[MAPEO]**: reportado con `archivo:línea` por una lectura automatizada, sin releer a mano. Se confirma antes de implementar lo que dependa de eso.
- **[DECISIÓN]**: elección de diseño de este contrato.
- **[AUDITORÍA]**: decisión tomada o corregida en la auditoría de Dexter.
- **[ABIERTA]**: sin decidir (en la v2.1 no queda ninguna de arquitectura, §14.3).
- **[PRODUCCIÓN]**: restricción o medición del área de producción y despliegue (§16.1b).

### Cambios desde la versión 1
| # | Corrección de auditoría | Dónde quedó |
|---|---|---|
| 1 | `origen NULL` no puede cambiar el `rol` de un mensaje histórico | §10, §11.1, I13, S16, S26 |
| 2 | T15 no permitía cerrar después de devolver a la IA | T15a / T15b. **Matiz:** con control `ia`, el cierre no exige `atendida_manual`; así funciona hoy (`api.py:1938-1950`) [VERIFICADO] |
| 3 | La reserva antes de escalar se mantiene. Si fallan las integraciones, el control **no** vuelve a la IA; se agrega una cola de sincronización con reintento | T1, §3.6, §9.4, X15, S23 |
| 4 | "Responder y devolver" solo devuelve cuando la entrega fue aceptada | T6 en dos fases, §9.5, X14, S22 |
| 5 | Cada herramienta aprobable revalida sus propias precondiciones o no se aprueba | §3.7, T13, X17, S25 |
| 6 | Tomar o soltar no resuelve `NO_DETERMINADO` | T19, §4.2 regla 3 |
| 7 | Un cierre externo no le quita la conversación a un operador activo | T11, X16, S24 |
| 8 | P2: la reasignación forzada queda solo para `ADMIN` | T4 |
| 9 | P5: los fallos al cerrar sistemas externos quedan como sincronización pendiente | T17, §3.6, S27 |
| 10 | P6: el bloqueo por aprobación pendiente llega al modelo como dato estructurado; no hay propuestas equivalentes duplicadas | §3.4, T12, X18, S28 |
| 11 | `relevo_eventos.datos` lleva versión y no admite datos crudos ni PII | §3.3, X19, I18 |
| 12 | Cada desenlace propio de un tenant se mapea a una categoría base | §3.5, I16 |
| 13 | S22–S28 | §12 |
| 14 | Antes del deploy, verificar que `MOTOR_SERVICE_TOKEN` protege el motor | §16 |

### Cambios desde la versión 2 (segunda ronda de auditoría + restricciones de producción)
| # | Ajuste | Dónde quedó |
|---|---|---|
| 1 | Q1 aprobada: T15b no exige `atendida_manual` | §14.1 |
| 2 | T6 en **4 pasos**: el `wamid` se guarda en su propia transacción antes de completar la devolución | T6, §9.5, S29 |
| 3 | Las sincronizaciones guardan su **intención** (esquema cerrado por tipo, versionado) y distinguen "falló" de "no se sabe si ocurrió" (`desconocida`); `clave_idempotencia` con UNIQUE | §3.6, §9.6, I17, S33 |
| 4 | Q2: `crear_ticket` **no se reintenta solo** hasta demostrar deduplicación en WispHub | §3.6, §14.1 |
| 5 | Q3: **no se quita la aprobación humana** para proteger la medición; la nueva config de las 4 herramientas se activa al cerrar la medición | §3.7, §14.1 |
| 6 | Q4: taxonomía de errores (transitorio, permanente, incierto) junto con los tiempos por defecto | §9.6, §14.1 |
| 7 | G2 corregido: producción **ya** corre el reloj (medido en producción), pero cada hora; T20 necesita cadencia propia | §3.6, §16, G7 |
| 8 | Guardas explícitas en T16 (pendiente interno, aviso, devolución incompleta) y en T18 (acciones, verificaciones, devolución incompleta), idénticas a X7 | T16, T18, X7 |
| 9 | Nunca comunicar como hecho un efecto externo no confirmado | T1, I19, X22 |
| 10 | Q5 aprobada: fail-closed al escalar; casos dorados en el mismo commit funcional | §14.1 |
| 11 | Restricciones de producción: transacciones cortas (`idle_in_transaction_session_timeout = 60s`), DDL con `lock_timeout = 1s` y preflight, backfill en lotes con volumen medido, referencias por servicio y no por línea | §11.5, §16.1 |
| 12 | Gates G6 (preflight de DDL y backfill) y G7 (reconciliador) | §16 |
| 13 | Construcción en fases B1–B7 | §15 |

### Cambios desde la versión 2.3 (auditoría durante B2 y B3.2)
| # | Decisión | Dónde |
|---|---|---|
| C1 | **Escalar escribe el control nuevo Y las banderas de legado que deciden la pausa, en la misma transacción**, antes del ticket y del CRM. Si fallan, la conversación sigue pausada (base y memoria). Adelanta a B3.2 la parte de conducta de Q5; la cola de reintentos sigue en B4. | T1, §15 |
| C2 | Con la reserva hecha, al cliente se le dice el anuncio de atención humana (promete una persona, no un número de caso). "No quedó registrado, escribime de nuevo" queda solo para cuando ni la reserva se pudo guardar. | T1 |
| C3 | **Un caso cerrado en el CRM nunca devuelve la conversación a la IA**, haya o no alguien a cargo: aviso + evento. El único camino de vuelta es `devolver_a_ia` (T7). En runtime, una conversación gobernada sigue en pausa; el legado retoma como siempre hasta G8. | T11, X16, I14 |
| C4 | `control_efectivo()` (`nucleo/relevo/control.py`): regla única para las guardas mientras dure la transición. `relevo_version > 0` → la columna `control`; `= 0` → humano si `escalada_a_humano` y `necesita_atencion_humana`. | §4.7, B3.3 |
| C5 | Una vez `relevo_version > 0` la conversación nunca vuelve a modo legado. G8 adopta las de legado con una transición explícita, con evento, no con un UPDATE anónimo. | I21, §11.2 |
| C6 | D21 (memoria ≠ lo que leyó el cliente) resuelto en B2.3; D22 ("Soltar" no llegaba al motor) resuelto en B3.2. | §13 |
| C7 | **B3.3b. `control_efectivo()` es la única compuerta que decide si corre el modelo**, leída de la base en cada turno (`control_de_conversacion_abierta`). Si la base no responde, falla cerrado: el modelo no corre y no se responde nada. La memoria del proceso solo refleja lo leído; nunca decide. | §4.7, X3, I3 |
| C8 | **T8 Intervenir** (`POST /conversaciones/<id>/intervenir`): actor solo de la sesión autenticada, clave de operación idempotente, precondición por `control_efectivo = 'ia'` bajo lock de la fila (dos operadores a la vez: uno gana, el otro 409 sin reasignar; una conversación de legado escalada también 409). No envía nada a Meta y no toca las banderas de escalada. Con `control_motivo = intervencion` el turno del cliente se guarda y no recibe acuse de escalada. La pantalla muestra "Intervenir" y el compositor, adjuntos y plantillas siguen bloqueados hasta que el motor confirma; la nota interna sigue disponible. | T8, X25 |
| C9 | **G1 y G9 en verde en producción.** G9 deja de ser un gate pendiente: `wamid` persistido (G9-A) y acuse de entregado correlacionado (G9-B). | §16.1 |

### Cambios desde la versión 2.1 (mediciones de producción)
No reabre la arquitectura: corrige supuestos con datos y agrega dos gates. Afecta B2 en adelante; B1 no cambia.

| # | Medición | Consecuencia | Dónde |
|---|---|---|---|
| A1 | **0 `wamid` y 0 `estado_entrega`/`error_entrega` guardados en 2584 mensajes**; el camino humano está implementado pero no se usó realmente desde el 06/09 | No se asume que el recibo del envío humano funciona hoy. Gate **G9**: envío controlado → `wamid` en base → webhook correlaciona, **sin reinicio provocado**; T6 no se activa sin G9. Aceptación del proveedor ≠ entregado ≠ leído. Si G9 destapa un defecto, se corrige dentro de este mismo plan. | T6, §2, §16 |
| A2 | Las reglas de backfill de `origen` de §11.1 (v2.1) identifican **0 filas** (G4) | No se inventa procedencia: **todo el histórico queda `origen = NULL`**. Desde el corte de B2, `origen` es obligatorio en filas nuevas. | §11.1 |
| A3 | — | Legado `rol = assistant` / `origen NULL`: **un único bloque de contexto por conversación** avisa que la procedencia de esos mensajes no está garantizada; los mensajes entran intactos, sin marca individual. | §10, S16 |
| A4 | Existe **1 fila con `rol = 'humano'`** | Se corrige "nadie lo escribe": ningún código lo escribe **hoy**, pero hay legado. Entra al modelo como `assistant` con el contenido intacto, cubierta por el bloque de legado de su conversación. | D6, §4.6, §10, S34 |
| A5 | **36 acciones `pendiente` de legado** | Nada de vencerlas en 24 h para que desaparezcan. **G3 bloquea B5**: revisión humana de las 36. Ninguna acción de legado sin `conversation_id` se ejecuta automáticamente. | §11.4, §14.2 Q4, X24 |
| A6 | **46 candidatas al backfill de `control`: 30 son de canales de prueba** | El modelo es el mismo para la simulación, pero la cola **operativa** muestra solo canales reales; hace falta una política para los hilos de prueba de legado. | §4.5, §11.2 |
| A7 | **16 conversaciones reales de WhatsApp** quedarían con `control = humano` y **sin `atendida_manual`** | Gate **G8**: revisión operativa una por una antes del corte de control. No se ocultan ni se resuelven solas. | §11.2, §16 |
| A8 | Volumen: **2584 mensajes (1,3 MB), 298 conversaciones** | No hace falta partir el backfill por rendimiento. Se mantiene el despliegue escalonado por seguridad de conducta, y el preflight de locks. La ejecución la decide el área de producción y despliegue. | §11.5, P-C |

---

## 1. Objetivo y límites

### Objetivo
Definir con un solo modelo:
- **quién controla** una conversación (la IA o una persona);
- **quién la tiene asignada**;
- **a quién le toca actuar**;
- **qué hechos se guardan y qué se calcula**;
- **qué transiciones existen**, cuáles están prohibidas y qué invariantes se sostienen ante concurrencia, reinicios, integraciones caídas y datos históricos.

Los defectos D1–D16 (§13) se implementan **contra este modelo**, no como arreglos sueltos.

### Dentro del alcance
- Pausa y reanudación de la IA.
- Escalada, toma, soltura, reasignación, intervención y devolución.
- Respuestas de personas (texto, plantilla, media, notas) y su entrega.
- Origen y autoría de cada mensaje, y reconstrucción del historial del modelo.
- Acciones de la IA que esperan aprobación (`asistente.acciones_propuestas`) en lo que tocan a la conversación, incluida su revalidación.
- Sincronización con sistemas externos (caso CRM, ticket operativo) que el relevo dispara.
- Cierre de la conversación y su **desenlace**.

### Fuera del alcance
- Aprobaciones de cierre de casos del CRM (`/tickets/approvals`, tabla `approval`). Es otro sistema [MAPEO].
- La lógica del evaluador que decide **si** escalar.
- Paginación y búsqueda de la lista.
- Frontend multi-tenant (hoy una instalación = un tenant).
- Macros, citas y comodidades de redacción.

---

## 2. Terminología

| Término | Definición exacta |
|---|---|
| **Conversación** | Fila de `asistente.conversations`: un hilo con un cliente por un canal, `abierta` o `cerrada`. |
| **Canal real** | `canal = 'whatsapp'`. Los mensajes del cliente entran solo por el webhook de Meta, con firma. |
| **Canal simulado** | `canal = 'whatsapp-simulado'` o `'api'`. Los mensajes del lado cliente los escribe un colaborador para probar. |
| **Operador** | Usuario autenticado del CRM. Roles existentes: `ADMIN` y `USER` [MAPEO]. **No existe "supervisor".** |
| **Control** | Quién responde al cliente: `ia` o `humano`. |
| **Escalada** | Decisión del evaluador de ceder el control a personas. **Se guarda al decidirse**, no cuando las integraciones terminan. |
| **Intervención** | Un operador toma el control sin que la IA haya escalado. No es escalada ni cuenta en la tasa de escalamiento. |
| **Asignación** | Qué operador tiene la conversación a cargo. Solo existe con control `humano`. |
| **Devolución** | Un operador devuelve el control a la IA. **No cierra el caso CRM.** |
| **Entrega aceptada** | El canal confirmó que recibió el mensaje para entregarlo (Meta respondió con `wamid`). **Aceptado ≠ entregado ≠ leído**: son tres hechos distintos, y el relevo solo usa el primero. En canal simulado se considera aceptada al guardarse. El recibo se guarda y se correlaciona en producción desde G9 (verde, 16/09/2026); antes había 0 `wamid` en 2584 mensajes. |
| **Necesita acción de** | Proyección calculada: `humano`, `cliente`, `aprobacion`, `ia` o `nadie`. Nunca se guarda. |
| **Pendiente interno** | Hecho explícito que marca un operador: quedó algo por hacer de nuestro lado ("voy a revisar la OLT y te aviso"). |
| **Revisión de evaluación** | Decisión explícita de un operador sobre una conversación `NO_DETERMINADO` (el evaluador falló). |
| **Acción propuesta** | Escritura externa que la IA dejó esperando aprobación humana. |
| **Revalidación** | Comprobación, **al aprobar**, de que las precondiciones de la acción siguen siendo ciertas. Cada herramienta aprobable la declara. |
| **Verificación de acción** | Medición posterior del efecto técnico (`asistente.verificaciones_accion`). `ACCION_CONFIRMADA` ≠ problema resuelto. |
| **Sincronización externa** | Efecto sobre un sistema externo que el relevo necesita (crear caso o ticket, cerrarlos). Se guarda como pendiente y se reintenta hasta quedar hecho o fallido de forma visible. |
| **Desenlace** | Código del catálogo que dice cómo terminó una conversación que tuvo relevo. |
| **Origen de un mensaje** | Qué lado lo produjo: `cliente` (el lado cliente; en canal simulado es un colaborador que lo representa), `ia`, `humano` o `sistema`. `NULL` = legado sin evidencia. |
| **Rol de un mensaje** | Protocolo del modelo y del canal: `user`, `assistant` o `nota`. **No dice quién lo escribió**, y el origen **nunca lo reemplaza**. |

---

## 3. Fuentes de verdad (se guardan)

**Regla [DECISIÓN + AUDITORÍA]:** se guarda lo que es una decisión o un hecho que no se puede reconstruir sin ambigüedad; se calcula lo que se deriva sin ambigüedad de lo guardado. "El código calcula" habla del modelo de lenguaje frente al código; no prohíbe guardar estados de workflow.

### 3.1 En `asistente.conversations`

| Dato | Hoy | Contrato |
|---|---|---|
| `estado` | `abierta` / `cerrada` [VERIFICADO] | Sin cambios. |
| **`control`** | No existe. Sale de `escalada_a_humano && necesita_atencion_humana` (`api.py:626`) **más** `_sesiones[...]["escalada"]` en memoria, que puede divergir (D9, D10) | **Nuevo.** `ia` o `humano`, not null, default `ia`. **Única fuente para decidir si la IA responde.** |
| **`control_motivo`** | — | **Nuevo.** `escalada` o `intervencion`. Not null si `control = 'humano'`. |
| **`asignada_a_usuario_id`**, **`asignada_a_nombre`**, `asignada_en` | `tomada_por` (texto: nombre o email), `tomada_en` [VERIFICADO] | **Nuevos.** `tomada_por` pasa a legado (§11). |
| **`pendiente_interno_desde`**, `pendiente_interno_nota` | — | **Nuevos.** |
| **`aviso_relevo`** | — | **Nuevo**, nullable: un aviso para el operador que no cambia el control. Hoy su único valor es `caso_externo_cerrado` (T11). Se limpia cuando el operador decide. |
| **`relevo_version`** | — | **Nuevo.** Entero que sube con cada transición. Concurrencia optimista (§9). |
| `caso_id`, `ticket_operativo` | [VERIFICADO] | Mismo significado. Pueden estar nulos con una sincronización pendiente (§3.6). |
| `atendida_manual`, `atendida_por` | Pasan a true al responder o resolver y nunca vuelven a false [VERIFICADO] | **Hecho histórico**: alguna persona actuó. Habilita los cierres de T15a y T16. **No decide la cola.** |
| `escalada_a_humano`, `necesita_atencion_humana` | Deciden la pausa y la cola | **Legado.** Se escriben en paralelo (§11.3) y dejan de decidir. |
| `estado_escalada` (`NO_DETERMINADO`, …) | [MAPEO] | Sin cambios. Entra a la proyección. |
| **`desenlace_codigo`**, `desenlace_nota`, **`cerrada_por_tipo`** (`cliente`, `ia_cliente`, `plazo`, `inactividad`, `operador`), `cerrada_por_usuario_id` | — | **Nuevos.** |

### 3.2 En `asistente.messages`

| Dato | Contrato |
|---|---|
| `rol` | **Sin cambios y sin reemplazo:** `user`, `assistant` o `nota`. Lo siguen usando la ventana de 24 h, el protocolo del modelo y la reconstrucción del legado. |
| **`origen`** | **Nuevo.** `cliente`, `ia`, `humano`, `sistema` o `NULL` (legado). Agrega procedencia; nunca contradice `rol`. |
| **`autor_usuario_id`**, **`autor_nombre`** | **Nuevos.** Obligatorios si `origen = 'humano'`. |
| **`clave_idempotencia`** | **Nuevo.** Único por conversación cuando no es nulo (§9.2). |

Correspondencia obligatoria para filas nuevas:

| Quién escribe | `rol` | `origen` |
|---|---|---|
| Webhook de Meta | `user` | `cliente` |
| Simulador / `api` | `user` | `cliente` (representa al lado cliente; el canal dice que es simulado) |
| IA | `assistant` | `ia` |
| Textos automáticos del motor (espera, cierre, tope de gasto) | `assistant` | `sistema` |
| Operador: texto, plantilla, media | `assistant` | `humano` |
| Nota interna | `nota` | `humano` |

### 3.3 Tabla nueva `asistente.relevo_eventos` (solo inserción)
`id, organization_id, conversation_id, tipo, datos_version smallint, actor_tipo (ia|operador|sistema|cliente), actor_usuario_id, actor_nombre, datos jsonb, clave_idempotencia, creado_en`.

**Tipos:**
- **Control:** `escalada`, `intervencion`, `devolucion_solicitada`, `devuelta_a_ia`, `devolucion_fallida`, `caso_externo_cerrado`.
- **Asignación y trabajo:** `tomada`, `soltada`, `reasignada`, `pendiente_interno_abierto`, `pendiente_interno_cerrado`, `evaluacion_revisada`.
- **Acciones:** `accion_propuesta_duplicada`, `accion_aprobada`, `accion_rechazada`, `accion_vencida`, `accion_cancelada`, `accion_desconocida`.
- **Cierre:** `cerrada`.

**Reglas sobre `datos`** [AUDITORÍA]:
- Cada `tipo` tiene un esquema **declarado en código**, con versión (`datos_version`). Escribir un evento valida contra ese esquema y rechaza campos desconocidos. Cambiar la forma de un tipo sube la versión; los lectores aceptan todas las versiones publicadas.
- **Solo** ids, códigos, estados, marcas de tiempo y los textos del operador en campos declarados (`motivo`, `nota`, hasta 500 caracteres).
- **Nunca** respuestas de APIs externas (WispHub, SmartOLT, CRM), argumentos completos de herramientas, datos del cliente (cédula, dirección, teléfono, GPS, contraseñas) ni secretos. Hereda la regla global: no se persisten respuestas crudas.

Es el expediente del relevo. La intervención queda aquí, no en el CRM.

### 3.4 En `asistente.acciones_propuestas`

| Dato | Hoy | Contrato |
|---|---|---|
| **`conversation_id`** | No existe [MAPEO] | **Nuevo.** Nullable solo para legado. |
| `estado` | `pendiente`, `aprobada` o `rechazada`, sin CHECK, UPDATE sin condición (`db.py:2235-2241`) [VERIFICADO] | CHECK con `pendiente`, `ejecutando`, `ejecutada_ok`, `ejecutada_fallo`, `rechazada`, `vencida`, `cancelada`, `desconocida`. **Solo transiciones condicionadas.** |
| **`vence_en`** | — | **Nuevo.** `creado_en + vigencia` que declara la herramienta (§3.7). |
| **`clave_equivalencia`** | — | **Nuevo.** Hash de (`conversation_id`, `herramienta`, argumentos en forma canónica). Índice único parcial `WHERE estado IN ('pendiente','ejecutando')`: dos propuestas equivalentes no pueden estar vivas a la vez. |
| `revisado_por` | Sale del cuerpo del request (`api.py:4894`) [VERIFICADO] | Sale del usuario autenticado que resuelve el proxy. **Nunca del cuerpo que arma el navegador.** |
| Argumentos | `argumentos jsonb` | Quedan **congelados**: el operador aprueba o rechaza, no edita. Corregir = rechazar y que la IA proponga de nuevo. |

### 3.5 Catálogo de desenlaces [DECISIÓN + AUDITORÍA]
- **Base de plataforma**, en código, igual para todo ISP. Cada código es también su propia categoría base: `equipo_cliente`, `fibra_acometida`, `red_distribucion`, `red_central`, `wifi_cliente`, `facturacion`, `configuracion`, `solicitud_comercial`, `resuelto_por_cliente`, `falso_positivo_ia`, `sin_respuesta_cliente`, `otro`.
- **Extensión por tenant** en `tenant_config`, editable desde la interfaz: `{codigo, nombre, categoria_base}`. **`categoria_base` es obligatoria** y debe ser un código base. Ejemplo: `fibra_poste_17 → red_distribucion`. Un tenant puede ocultar códigos base, pero no redefinirlos.
- Las métricas de plataforma agrupan por `categoria_base`; las de cada empresa pueden abrir por código propio.
- La base funciona **sin escribir config**, así que no contamina la medición ON vs OFF.
- El cierre manual exige código. El cierre por plazo usa `sin_respuesta_cliente`. Los cierres por el cliente y por inactividad dejan `NULL`, y se completan después si una persona revisa.

### 3.6 Tabla nueva `asistente.sincronizaciones_externas` (cola de efectos externos) [AUDITORÍA]
`id, organization_id, conversation_id, tipo (crear_caso|crear_ticket|cerrar_caso|cerrar_ticket), estado (pendiente|en_curso|hecha|fallida_definitiva|desconocida), datos_version smallint, datos_intencion jsonb, intentos, proximo_intento_en, ultimo_error_clase (transitorio|permanente|incierto), ultimo_error_codigo, referencia_externa, clave_idempotencia, creado_en, actualizado_en`.

- **`UNIQUE (organization_id, clave_idempotencia)`**. La clave se deriva de (conversación, tipo, evento que la originó), así que la misma transición no puede encolar dos veces el mismo efecto.
- **`datos_intencion`** [AUDITORÍA]: **exactamente** lo que había que hacer cuando se decidió, con esquema cerrado por `tipo` y `datos_version`. El reconciliador **no** reconstruye el efecto con la config actual, que pudo cambiar. Solo datos mínimos y sanitizados, por ejemplo `crear_ticket: {servicio_id, tipo_ticket_codigo, motivo_codigo, referencia_conversation_id, asunto_codigo}`. Nunca payloads crudos, argumentos completos ni datos del cliente.
- **`desconocida`** [AUDITORÍA]: el pedido pudo llegar al sistema externo y no se sabe si produjo el efecto (timeout después de enviar, conexión cortada, crash con el pedido en vuelo). **No es `fallida_definitiva` y no se reintenta a ciegas**: primero se consulta si el efecto existe; si no se puede demostrar, queda para revisión humana, visible en la conversación.

- **Se inserta en la misma transacción que la transición que la necesita** (T1, T17). El primer intento corre en línea, fuera de la transacción. Si falla o el proceso muere, queda `pendiente`.
- **El reconciliador** (T20) reintenta con espera creciente. Pasados N intentos, `fallida_definitiva` → **visible en la conversación**, nunca silenciosa.
- **`ultimo_error_codigo`**: solo el código y el estado HTTP. Nunca el cuerpo de la respuesta.
- **Idempotencia hacia afuera:**
  - `crear_caso`: el nombre del caso en el CRM incluye el `conversation_id` y debe ser único por organización; uno repetido responde 400 (`escalamiento.py:746-751`) [VERIFICADO]. Ante un reintento, primero se busca el caso por ese nombre y, si existe, se adopta su id.
  - `crear_ticket` (WispHub) [AUDITORÍA Q2]: **no se reintenta automáticamente** hasta demostrar, con la skill `wisphub-api` y el método del valor imposible, una de estas tres cosas en orden: (1) WispHub acepta una clave de idempotencia o referencia externa; (2) se puede buscar un ticket por esa referencia; (3) se puede buscar sin ambigüedad por el `conversation_id` embebido en el asunto. Con alguna demostrada: consultar → si existe, adoptar; si no, crear. Sin ninguna: un fallo con resultado incierto queda `desconocida` y **no se crea otro**. Es preferible un ticket pendiente de revisión a dos visitas técnicas duplicadas.
- **Dependencia (corregido):** el `default 0` de `RELOJ_HABILITADO` en el compose **no** describe producción. Medido en el runtime de producción: `RELOJ_HABILITADO=1`, `motor-reloj` activo, con un ciclo de ~60 min para las tareas actuales. Ese ciclo **no alcanza** para los plazos de §14.1 Q4 (10 y 15 min). **T20 necesita cadencia propia, de 1 a 5 min**, o un despertador guiado por `proximo_intento_en`. Gate G7.

### 3.7 Revalidación de acciones aprobables [AUDITORÍA]
**Regla:** una herramienta con `aprobacion_humana: true` debe declarar en el catálogo:
- `aprobacion.vigencia_minutos` (**obligatorio**): pasado ese plazo, la propuesta vence y no se ejecuta.
- `aprobacion.revalidar` (**obligatorio**): comprobación declarativa que se corre **al aprobar**, antes de ejecutar. Forma: una herramienta de **lectura** del mismo catálogo, con los argumentos tomados de la propuesta, más condiciones sobre el resultado (igualdad, pertenencia o comparación contra un valor de la propuesta).

**Si falta cualquiera de los dos, la carga de la config falla**: la herramienta no puede quedar aprobable (falla cerrado en la validación de `TenantConfig`, igual que hoy con otros errores de catálogo).

Al aprobar, la ejecución solo corre si se cumple todo:
1. Acción en `pendiente` y `now() < vence_en`.
2. Conversación abierta.
3. Herramienta todavía en catálogo, con `aprobacion_humana` activa.
4. `revalidar` corre sin error **y** sus condiciones se cumplen.

Si la revalidación **no puede correr** (API caída, timeout) → **no se ejecuta**, la acción sigue `pendiente` y el operador ve "no se pudo comprobar, reintentar". Si **corre y no se cumple** → `vencida` con el código de la condición fallida.

Revalidaciones propuestas para las cuatro herramientas aprobables de hoy (`tenants/rapilink.config.yaml:3883, 3971, 4017, 4171`) [MAPEO]. Cada una se confirma con la skill `wisphub-api` antes de escribirse:

| Herramienta | Qué se revalida |
|---|---|
| `crear_ticket` | El servicio del cliente existe y sigue activo; no hay otro ticket abierto con el mismo asunto para ese servicio |
| `responder_ticket` | El ticket existe y no está cerrado |
| `actualizar_estado_ticket` | El estado actual del ticket es **el mismo que se vio al proponer** (comparar y cambiar) |
| `agregar_promesa_pago` | La factura sigue pendiente y no tiene una promesa vigente |

**Activación y medición [AUDITORÍA Q3]:** agregar estos bloques es escribir `tenant_config` de Rapilink, y eso parte la medición de razonamiento ON vs OFF (en curso desde el 07/09/2026). Se resuelve así:
- **No se quita ni se relaja `aprobacion_humana`** en ninguna herramienta para proteger la medición. La medición nunca justifica bajar un control que falla cerrado.
- Mientras la medición siga, se construye **todo lo que no escribe config**: esquema, validador, motor de revalidación, tests y UI.
- La **config de Rapilink con vigencia y revalidación se activa después de cerrar la medición**.
- **Transición del validador:** mientras esa config no esté activa, la regla "sin `revalidar` la carga falla" no puede encenderse, porque rompería la config vigente. El validador se despliega en modo **advertencia**, y las herramientas aprobables sin revalidación declarada siguen con el flujo de aprobación actual **más** las guardas que no dependen de config (transición condicionada, conversación abierta, operador autenticado; §9.3). El paso a **error** va en el mismo cambio que activa la config nueva.

---

## 4. Datos calculados (proyecciones)

Todas son funciones puras de §3, implementadas **una sola vez en el backend**. El frontend las recibe calculadas. Esto corrige la duplicación que ya costó el 07/09/2026.

### 4.1 `ia_responde`
`estado = 'abierta' AND control = 'ia'`. El motor lo lee **de la base en cada turno**. La memoria nunca decide la pausa.

### 4.2 `necesita_accion_de`
Reglas en orden; gana la primera que se cumple:

| # | Condición | Resultado |
|---|---|---|
| 1 | `estado = 'cerrada'` | `nadie` |
| 2 | Hay una acción propuesta de esta conversación en `pendiente` o `desconocida` | `aprobacion` |
| 3 | `control = 'ia'` y `estado_escalada = 'NO_DETERMINADO'` **sin evento `evaluacion_revisada` posterior** | `humano` |
| 4 | `control = 'ia'` | `ia` |
| 5 | `control = 'humano'` y (`aviso_relevo` no nulo **o** último evento de devolución = `devolucion_fallida`) | `humano` |
| 6 | `control = 'humano'` y `pendiente_interno_desde` no nulo | `humano` |
| 7 | `control = 'humano'` y ningún mensaje `origen = 'humano'` con entrega aceptada posterior al evento que abrió el control | `humano` |
| 8 | `control = 'humano'` y el último mensaje que cuenta es del lado cliente | `humano` |
| 9 | `control = 'humano'` y el último mensaje que cuenta es de `humano` con entrega aceptada | `cliente` |
| 10 | Cualquier otro caso | `humano` |

- **"Mensaje que cuenta"** = no es nota, no es `origen = 'sistema'`, y es `origen IN ('cliente','humano')` o legado (`origen NULL`). Un legado con `rol = 'user'` cuenta como lado cliente; con `rol = 'assistant'` se desconoce el autor → regla 10.
- **Un mensaje humano con entrega fallida no cuenta como contestado**: el cliente no lo recibió.
- La regla 10 falla hacia lo visible: esconder a un cliente que espera es peor que mostrar uno de más.

### 4.3 `esperando_desde`
Momento del hecho que decidió la regla ganadora. Ordena la cola.

### 4.4 `sincronizacion`
Por conversación: la peor situación entre sus sincronizaciones (`hecha` < `pendiente` < `fallida_definitiva`). Es una marca **aparte** de `necesita_accion_de`: la conversación ya está en la bandeja, y lo que falta es el efecto externo.

### 4.5 Vistas de la bandeja
Las vistas **operativas** muestran solo canales reales (`canales.REALES`); las conversaciones de canales simulados siguen el mismo modelo pero se ven en una vista de simulación aparte, para que las pruebas no contaminen la cola de trabajo (A6).

- **Por atender:** `necesita_accion_de IN ('humano','aprobacion')` y sin asignación.
- **Mías:** asignada a mí, con marca si `necesita_accion_de = 'humano'` (el cliente respondió, pendiente interno, entrega fallida, caso externo cerrado).
- **En atención (equipo):** asignadas a cualquiera.
- **Esperando al cliente:** `necesita_accion_de = 'cliente'`.
- **Resueltas:** `estado = 'cerrada'`, con marca si `sincronizacion` no es `hecha`.

### 4.7 `control_efectivo` (transición) [AUDITORÍA C4, C7]
Mientras existan conversaciones de legado sin reconciliar, **todas** las guardas usan una única función (`nucleo/relevo/control.py`) — las de envío humano (B3.3) y la compuerta del modelo en cada turno (B3.3b, leída de la base; si no se puede leer, el modelo no corre):
- `relevo_version > 0` → la columna `control`.
- `relevo_version = 0` → `humano` si `escalada_a_humano` y `necesita_atencion_humana`; si no, `ia` (la misma regla que hoy decide la pausa al reconstruir una sesión).
Sin esto, una guarda que leyera solo `control` bloquearía a los operadores en las conversaciones escaladas antes del corte (B3.1 las dejó en `ia` por default, sin backfill). Se retira cuando G8 deje sin filas la rama de legado.

### 4.6 `atendida` (legado)
`atendida_manual`. Se elimina la rama `exists(rol = 'humano')`: ningún código la escribe hoy. La **única fila de legado** con `rol = 'humano'` se trata como un mensaje humano de autor desconocido (§10); su conversación se revisa en la migración para confirmar que `atendida_manual` ya la cubre.

---

## 5. Estados válidos

Estado = (`estado`, `control`, asignación). La sincronización, el aviso y las proyecciones son ortogonales.

| Id | `estado` | `control` | Asignación | Significado |
|---|---|---|---|---|
| **E0** | abierta | ia | ninguna | La IA atiende. Incluye "agendada sola" y `NO_DETERMINADO`. |
| **E1** | abierta | humano | ninguna | En manos de personas, sin dueño. |
| **E2** | abierta | humano | operador X | X la tiene a cargo. |
| **E3** | cerrada | (cualquiera) | ninguna | Terminada. |

**Inválidas:** `abierta / ia / asignada` y `cerrada / * / asignada`.

---

## 6. Transiciones válidas

Cada transición es **un UPDATE condicionado + su evento (+ sus sincronizaciones), en la misma transacción**, y sube `relevo_version`. Los efectos externos van **después** y **fuera** de esa transacción.

| Id | Desde → hasta | Disparo | Precondición | Efecto guardado | Qué recibe el cliente |
|---|---|---|---|---|---|
| **T1** | E0 → E1 | Escalar (IA) | `control = 'ia'` y el evaluador decide `necesita_humano` | **Transacción 1:** `control = humano`, `control_motivo = escalada`, evento `escalada`, filas `crear_caso` / `crear_ticket` según el catálogo del tenant, legado en paralelo. **Después:** primer intento de cada sincronización. **Si fallan, el control sigue humano** [AUDITORÍA]: la conversación ya está en la bandeja y el reconciliador sigue intentando. | Anuncio según el motivo, que promete **atención humana** ("nuestro equipo ya está revisando tu caso"): eso es cierto aunque el CRM falle, porque la conversación ya está en la cola de personas. **Nunca** afirma un efecto externo no confirmado ("ya creamos el ticket #123") mientras su sincronización no esté `hecha` (I19). |
| **T1b** | E0 → E0 | Agendar sola (IA) | `necesita_humano = false` | Ticket (vía sincronización), `escalada_a_humano` legado. **Sin cambio de control.** | Texto de agenda. |
| **T2** | E1 → E2 | Tomar (operador) | Sin asignación, **o** ya mía (idempotente) | Asignación = yo, evento `tomada`. **No** resuelve `NO_DETERMINADO`. | Nada. |
| **T3** | E2 → E1 | Soltar (operador) | Asignada a mí, **o** actor `ADMIN` | Asignación = ninguna, evento `soltada`. **No** resuelve `NO_DETERMINADO`. | Nada. |
| **T4** | E2(otro) → E2(yo) | Reasignar (operador) | **Actor `ADMIN`** [AUDITORÍA]; `motivo` obligatorio; confirmación explícita. Habilitarlo entre pares por tenant queda para cuando una empresa lo pida. | Asignación = yo, evento `reasignada` {anterior, nuevo, motivo}. | Nada. |
| **T5** | E1/E2 → E2 | Responder y seguir atendiendo | Asignada a mí o sin asignar (si es de otro → 409, usar T4); canal apto (§9.5) | Mensaje `origen = humano` + autor + clave; `atendida_manual = true`; si no tenía dueño, asignación = yo + evento `tomada`. Opcional: pendiente interno. Sin la marca: cierra el pendiente interno previo. Entrega según §9.5. **El control no cambia, falle o no la entrega.** | El mensaje, si la entrega se acepta. |
| **T6** | E1/E2 → E0 **solo con entrega aceptada** | Responder y devolver a la IA | Igual que T5 **+ G9 aprobado**: hasta demostrar el recibo punta a punta, "Responder y devolver" no se habilita para canal real (en simulado sí) | Cuatro pasos (§9.5) [AUDITORÍA]. **Paso 1** (transacción): mensaje como T5 + evento `devolucion_solicitada` {mensaje_id}; control y asignación sin cambios. **Paso 2:** envío, fuera de transacción. **Paso 3** (transacción corta): si el canal aceptó, guardar `wamid` + `estado_entrega = enviado`; si rechazó, mensaje en error + evento `devolucion_fallida`, y **control y asignación humanos se conservan**. **Paso 4** (transacción corta, solo si el paso 3 guardó la aceptación): `control = ia`, asignación = ninguna, pendiente interno cerrado, evento `devuelta_a_ia`. Caso CRM y ticket sin tocar. | El mensaje, si se acepta. |
| **T7** | E1/E2 → E0 | Devolver sin responder | Asignada a mí o sin asignar, o `ADMIN` | `control = ia`, asignación = ninguna, evento `devuelta_a_ia`. | Nada. |
| **T8** | E0 → E2 | Intervenir | `control_efectivo = 'ia'` (C7), abierta | `control = humano`, `control_motivo = intervencion`, asignación = yo, evento `intervencion` {motivo opcional}. Sin caso CRM y sin contar en la tasa de escalamiento. | Nada. |
| **T9** | E0 → E0 | Cliente escribe | — | Mensaje `cliente`; responde la IA. Si hay una acción pendiente de la conversación, el modelo recibe el bloqueo estructurado (§9.7). | Respuesta de la IA. |
| **T10** | E1/E2 → igual | Cliente escribe | — | Mensaje `cliente`. Si ninguna persona escribió con entrega aceptada desde que se abrió el control: texto `mensaje_ya_escalada` (`sistema`). Si ya escribió: **silencio**, como hoy (`api.py:977-984`) [VERIFICADO]. | Texto de espera o nada. |
| **T11** | E1/E2 → igual (control intacto) | Caso CRM observado cerrado (motor o reconciliador) | `control = humano`, `control_motivo = escalada`, caso en `Closed/Rejected/Duplicate` | **Solo** `aviso_relevo = caso_externo_cerrado` + evento `caso_externo_cerrado` {aplicado: false}, **haya o no asignación** [AUDITORÍA C3]. El CRM es un sistema relacionado, no la autoridad sobre quién atiende. La persona decide devolver (T7) o resolver (T17). | Nada: la pausa sigue. |
| **T12** | cualquiera abierta | IA propone una acción | Controles actuales + la herramienta cumple §3.7 | Si existe una equivalente viva (misma `clave_equivalencia`): **no se crea otra**, evento `accion_propuesta_duplicada` y el modelo recibe la existente. Si no: fila `pendiente` con `conversation_id` y `vence_en`. | "Todavía no se ejecutó". |
| **T13** | acción `pendiente` → `ejecutando` → `ejecutada_ok` / `ejecutada_fallo` (o → `vencida`) | Aprobar (operador) | Operador autenticado + las cuatro condiciones de §3.7 | Reserva condicionada → revalidación → ejecución → resultado; evento `accion_aprobada` o `accion_vencida`. | Nada automático [AUDITORÍA P4]. |
| **T14** | acción `pendiente` → `rechazada` | Rechazar (operador) | Acción `pendiente` | Evento `accion_rechazada` {motivo}. | Nada automático. |
| **T15a** | E1/E2 → E3 | El cliente confirma el cierre, con control humano | `atendida_manual`; veredicto `resuelta`/`confirma_cierre`; ninguna verificación pendiente; ninguna acción `pendiente`/`ejecutando` | Conversación cerrada, `cerrada_por_tipo = cliente`, filas `cerrar_caso`/`cerrar_ticket`, evento `cerrada`. | Mensaje de cierre. |
| **T15b** | E0 → E3 | El cliente confirma el cierre, con la IA atendiendo (incluye después de T6) | Veredicto `resuelta`/`confirma_cierre`; ninguna verificación pendiente; ninguna acción `pendiente`/`ejecutando`. **No exige `atendida_manual`**: así funciona hoy este camino (`api.py:1938-1950`) [VERIFICADO], y una conversación que la IA resolvió sola nunca tuvo persona. | Igual que T15a con `cerrada_por_tipo = ia_cliente`; sincronizaciones solo si hay caso o ticket. | Mensaje de cierre. |
| **T16** | E1/E2 → E3 | Barrido por plazo (reloj) | Lo de hoy (`escalada`, atendida, sin mensaje del cliente en N horas) **+** ninguna verificación pendiente (D14) **+** ninguna acción `pendiente`/`ejecutando`/`desconocida` **+** `pendiente_interno_desde IS NULL` **+** `aviso_relevo IS NULL` **+** ninguna `devolucion_solicitada` sin `devuelta_a_ia`/`devolucion_fallida` [AUDITORÍA] | Como T15a, con `cerrada_por_tipo = plazo` y `desenlace = sin_respuesta_cliente`. | Nada. |
| **T17** | E0/E1/E2 → E3 | Resolver a mano (operador) | `desenlace_codigo` obligatorio | Conversación cerrada **de inmediato**, `cerrada_por_tipo = operador`, acciones vivas → `cancelada`, evento `cerrada`. Si "cerrar también caso y ticket" está marcado (por defecto sí [AUDITORÍA P5]): filas `cerrar_caso`/`cerrar_ticket`. **Un fallo externo no reabre la conversación**; queda como sincronización pendiente, visible y reintentable. | Nada. |
| **T18** | E0 → E3 | Inactividad (motor, al llegar un mensaje nuevo) | `control = 'ia'` **+** ninguna acción `pendiente`/`ejecutando`/`desconocida` **+** ninguna verificación pendiente **+** ninguna `devolucion_solicitada` incompleta [AUDITORÍA] | Resumen **sin notas** (D12), `cerrada_por_tipo = inactividad`. | Lo que responda la IA en la conversación nueva. |
| **T19** | E0/E1/E2 → igual | Revisar evaluación `NO_DETERMINADO` (operador) [AUDITORÍA] | `estado_escalada = 'NO_DETERMINADO'` sin revisión | Evento `evaluacion_revisada` {decision: `no_requiere_persona` \| `requiere_persona`}. `requiere_persona` con control `ia` equivale a T8 en la misma transacción. **También resuelven la revisión:** T7, T8 y T17. **No la resuelven:** T2 y T3. | Nada. |
| **T20** | — | Reconciliador (reloj) | — | (a) Reintenta sincronizaciones `pendiente`. (b) Completa el paso 4 de T6 cuando el paso 3 guardó la aceptación; marca el mensaje `desconocido` + `devolucion_fallida` si no quedó `wamid` guardado pasados N min (§9.5). Reintenta o marca `desconocida` las sincronizaciones según la clase de error (§9.6). (c) `ejecutando` viejas → `desconocida` + evento. (d) `pendiente` vencidas → `vencida` + evento. (e) Observa casos CRM cerrados de conversaciones con `control = humano` (T11). **Nunca reejecuta una acción ni reenvía un mensaje por su cuenta.** | Nada. |

**Sobre T18** [VERIFICADO]: hoy el cierre por inactividad no mira la escalada (`db.py:2338-2345`, `api.py:739-750`). Con control humano, el mensaje del cliente sigue en el mismo hilo.

---

## 7. Transiciones prohibidas

| Id | Prohibición | Dónde se hace cumplir |
|---|---|---|
| **X25** | Que un operador le envíe **cualquier cosa** al cliente — texto, imagen, documento, nota de voz o plantilla — mientras `control = 'ia'`, sin haber intervenido (T8) [AUDITORÍA]. Solo la nota interna queda disponible. | **UI (B1, hecho):** el compositor, las herramientas de adjunto y voz, y las plantillas se deshabilitan en hilos reales que atiende la IA. **Backend (B3):** `/conversaciones/<id>/mensajes`, `/humano/media` y `/plantilla` exigen `control = 'humano'` con 409; no se aplica antes porque sin `control` guardado solo habría banderas de legado y memoria para decidirlo (I3). Test S36. |
| **X1** | Que un texto de operador quede con `rol = 'user'` / `origen = 'cliente'` en **canal real** (D3). | **Backend:** `/chat` rechaza `canal = 'whatsapp'` con 403 (el webhook no pasa por `/chat`, y `/chat` nunca envía a Meta [MAPEO]). **UI:** sin compositor de lado cliente en canal real. La UI bloquea por UX; el backend, por integridad. |
| **X2** | Que una conversación simulada y una real compartan sesión en memoria. Hoy la clave es `(tenant, identificador)`, sin canal (`api.py:4043`) [VERIFICADO]. | Clave de sesión con canal. |
| **X3** | Pausar la IA sin guardarlo en base (D9). | T1 y T8 escriben `control` antes de responder. |
| **X4** | Levantar la pausa solo en memoria (D10). | T11 escribe en base. |
| **X5** | Dos asignaciones, o una toma que pisa a otra sin `reasignada`. | UPDATE condicionado. |
| **X6** | Ejecutar dos veces, aprobar una acción no `pendiente`, rechazar una aprobada, o aprobar con la conversación cerrada. | Transiciones condicionadas. |
| **X7** | Cerrar por plazo, por inactividad o por el cliente con una verificación pendiente, una acción `pendiente`/`ejecutando`/`desconocida` o una devolución incompleta; y cerrar por plazo con un pendiente interno o un aviso de relevo abiertos. | Precondiciones de T15a, T15b, T16 y T18, que dicen exactamente lo mismo. |
| **X8** | Que una nota entre al historial del modelo o al texto del que se redacta un resumen (D12). | Filtro en la reconstrucción y en `conversacion_vencida`. |
| **X9** | Que devolver a la IA cierre el caso CRM o el ticket. | T6 y T7 no los tocan. |
| **X10** | Marcar un mensaje histórico como `origen = 'ia'` sin evidencia. | §11.1. |
| **X11** | Que reintentar el envío cree una fila nueva (D15). | `clave_idempotencia`. |
| **X12** | Guardar un mensaje antes de validar que ese canal lo puede enviar (D16). | Validar antes de insertar. |
| **X13** | Mensaje de persona sin autor (D2). | El proxy toma el autor de la sesión; el motor rechaza `origen = humano` sin autor. |
| **X14** | Completar una devolución sin entrega aceptada del mensaje que la acompaña [AUDITORÍA]. | T6 en fases. |
| **X15** | Que la IA recupere el control porque fallaron integraciones, después de que el evaluador decidió que hace falta una persona [AUDITORÍA]. | T1: el fallo solo deja una sincronización pendiente. |
| **X16** | Que un cierre externo del caso cambie el control o la asignación de una conversación, con o sin alguien a cargo [AUDITORÍA C3]. | T11 solo avisa. |
| **X17** | Ejecutar una acción aprobada sin su revalidación específica, con la revalidación fallida o sin poder correrla, o después de `vence_en` [AUDITORÍA]. | §3.7 y T13. |
| **X18** | Dos propuestas equivalentes vivas a la vez [AUDITORÍA]. | Índice único parcial sobre `clave_equivalencia`. |
| **X19** | Respuestas crudas de APIs, argumentos completos, datos del cliente o secretos en `relevo_eventos.datos` o en `sincronizaciones_externas` [AUDITORÍA]. | Validación de esquema por tipo; solo el código de error. |
| **X20** | Que la reconstrucción cambie el `rol` de un mensaje de legado [AUDITORÍA]. | §10. |
| **X21** | Que el reconciliador reejecute una acción o reenvíe un mensaje por su cuenta, o reintente una sincronización `desconocida` sin haber demostrado antes que el efecto no existe. | T20, §9.6. |
| **X22** | Decirle al cliente que un efecto externo ocurrió (ticket creado, caso cerrado, visita agendada) mientras su sincronización no esté `hecha` [AUDITORÍA]. | I19; los textos y el contexto del modelo solo reciben referencias externas de sincronizaciones `hecha`. |
| **X24** | Ejecutar, aprobar o vencer automáticamente una acción de legado sin `conversation_id` [PRODUCCIÓN A5]. | §11.4; G3 antes de B5. |
| **X23** | Mantener una transacción de base abierta mientras se espera una operación externa (HTTP, Meta, WispHub, SmartOLT, CRM, modelo, archivo, `sleep`) [PRODUCCIÓN]. | Patrón transacción corta → efecto → transacción corta en T1, T6, T13, T17 y T20; revisión de código de cada fase. |

---

## 8. Invariantes

| Id | Invariante |
|---|---|
| **I1** | `control = 'humano'` ⇔ `control_motivo IS NOT NULL`, y el último evento de control es `escalada` o `intervencion` (o `devolucion_solicitada`/`devolucion_fallida` sobre uno de esos). |
| **I2** | Asignación no nula ⇒ `control = 'humano'` ∧ `estado = 'abierta'`. |
| **I3** | La pausa se decide leyendo `control` de la base. Ningún camino la decide solo con `_sesiones`. |
| **I4** | Toda fila de `messages` creada después del despliegue tiene `origen`. `origen = 'humano'` ⇒ autor no nulo. Para filas nuevas, `rol = 'user'` ⇔ `origen = 'cliente'`. |
| **I5** | Ninguna fila `rol = 'nota'` llega al historial del modelo ni al insumo de un resumen. |
| **I6** | Una acción se ejecuta a lo sumo una vez. `estado` solo avanza: `pendiente → ejecutando → ejecutada_*`; `pendiente → rechazada / vencida / cancelada`; `ejecutando → desconocida`. |
| **I7** | `estado = 'cerrada'` ⇒ ninguna acción de la conversación en `pendiente` o `ejecutando`. |
| **I8** | La ventana de 24 h se calcula solo con mensajes del lado cliente (`rol = 'user'`). |
| **I9** | `atendida_manual` nunca pasa de true a false. |
| **I10** | T6, T7 y T11 no cambian el estado del caso CRM ni del ticket. |
| **I11** | A lo sumo una escalada abierta por conversación. Se decide con `relevo_eventos`, no con `ya_escalada` en memoria. |
| **I12** | Toda transición inserta su evento en la misma transacción que el cambio de estado. No hay cambio sin evento ni evento sin cambio. |
| **I13** | El historial reconstruido desde la base es igual al armado en vivo para las mismas filas. Para legado se conserva `rol`. |
| **I14** | `control` pasa de `humano` a `ia` solo por T6 (paso 4, tras aceptación guardada en el paso 3), T7 o T19→T7 — todas por `devolver_a_ia`. Nunca por un fallo de integración ni por un cierre externo. |
| **I21** | `relevo_version` nunca baja. Una conversación con `relevo_version > 0` nunca vuelve a modo legado; las de legado entran al modelo solo por una transición explícita (escalar, intervenir o la adopción de G8), con evento. |
| **I15** | A lo sumo una acción viva (`pendiente`/`ejecutando`) por `clave_equivalencia`. |
| **I16** | Todo código de desenlace propio de un tenant tiene una `categoria_base` válida. |
| **I17** | Toda sincronización termina en `hecha`, `fallida_definitiva` o `desconocida`; las dos últimas, visibles en la conversación. Ninguna queda `en_curso` más de N minutos sin que el reconciliador la retome. |
| **I18** | Todo `relevo_eventos.datos` y todo `sincronizaciones_externas.datos_intencion` valida contra el esquema de su `tipo` y `datos_version`. |
| **I19** | Ningún mensaje al cliente ni contexto del modelo presenta como realizado un efecto externo cuya sincronización esté `pendiente`, `en_curso`, `desconocida` o `fallida_definitiva` [AUDITORÍA]. |
| **I20** | Ninguna transacción de base queda abierta mientras se espera una operación externa [PRODUCCIÓN]. |

---

## 9. Concurrencia e idempotencia

### 9.1 Transiciones de la conversación
```sql
UPDATE asistente.conversations
   SET <efecto>, relevo_version = relevo_version + 1
 WHERE organization_id = :org AND id = :id
   AND <precondición de §6>
   AND relevo_version = :version_vista     -- solo acciones de operador
RETURNING relevo_version, control, asignada_a_nombre, ...;
```
- 0 filas → **409** con el estado actual. La UI recarga y lo muestra; no reintenta a ciegas.
- T2 con asignación ya mía → 200 sin evento nuevo.
- El motor (T1, T11) no usa `relevo_version`: su precondición sobre `control` alcanza.

### 9.2 Mensajes de operador
- El frontend genera `clave_idempotencia` por **mensaje compuesto**. Reintentar reutiliza la clave.
- Si la clave ya existe, no se inserta: se reintenta la entrega de esa fila si está en error.
- Índice único `(conversation_id, clave_idempotencia)`.

### 9.3 Aprobación de acciones
1. `UPDATE ... SET estado = 'ejecutando' WHERE id = :id AND estado = 'pendiente' AND vence_en > now() AND <conversación abierta> RETURNING` → 0 filas = 409 (o `vencida` si el motivo es el plazo).
2. Revalidación (§3.7), fuera de transacción. Si no puede correr → `UPDATE ... SET estado = 'pendiente' WHERE estado = 'ejecutando'` y se informa. Si falla la condición → `vencida`.
3. Ejecución externa, fuera de transacción. No se mantiene una transacción abierta mientras se espera una API, porque eso deja sesiones `idle in transaction` detrás del pooler, un problema ya medido.
4. `UPDATE ... SET estado = 'ejecutada_ok' | 'ejecutada_fallo' WHERE estado = 'ejecutando'`.
5. Si el proceso muere entre 1 y 4: T20 la pasa a `desconocida`. **Nunca se reejecuta sola.**

### 9.4 Escalada y turnos concurrentes
Hoy corren 8 hilos sin locks sobre `_sesiones` [MAPEO].
- T1 reserva primero: `UPDATE ... SET control = 'humano', control_motivo = 'escalada' WHERE control = 'ia' RETURNING`, con el evento y las filas de sincronización **en la misma transacción**. Solo el turno que obtiene la fila sigue. El otro ve `control = humano` y va por T10.
- **Crash después de la reserva** [AUDITORÍA]: la conversación queda en E1, visible en la bandeja, con las sincronizaciones `pendiente`. T20 las completa. La IA no retoma sola.
- **Sin compensación hacia la IA.** Esto reemplaza el comportamiento actual `ESCALAMIENTO_NO_CONFIRMADO` → la IA sigue [MAPEO]. Es un **cambio de conducta visible** y afecta casos dorados existentes; aprobado en Q5 (§14.2), con los casos actualizados en el mismo commit funcional.
- Sin advisory locks durante llamadas HTTP.

### 9.5 Entrega de mensajes humanos y devolución en fases [AUDITORÍA]
| Canal | "Entrega aceptada" |
|---|---|
| `whatsapp` | Meta respondió con `wamid` → `estado_entrega = 'enviado'` |
| `whatsapp` fuera de la ventana de 24 h | **Nunca** con texto libre: la UI exige plantilla, y la plantilla aceptada cuenta como entrega |
| Simulado | Al guardarse |

Pasos de T6 [AUDITORÍA: 4 pasos, para que el `wamid` nunca viva solo en memoria]:
1. **Transacción corta:** insertar el mensaje (`estado_entrega = 'pendiente'`, clave) + evento `devolucion_solicitada`. COMMIT.
2. **Envío a Meta**, fuera de transacción.
3. **Transacción corta:** con aceptación → guardar `wamid` + `estado_entrega = 'enviado'`. COMMIT. Con rechazo → mensaje en error + evento `devolucion_fallida`. COMMIT. Fin: control y asignación humanos.
4. **Transacción corta** (solo tras aceptación guardada): `control = ia` + asignación = ninguna + evento `devuelta_a_ia`, condicionado a `control = 'humano'` y a que no exista `devuelta_a_ia`/`devolucion_fallida` para ese `devolucion_solicitada`. COMMIT.

Crash en cada punto:
| Muere después de | Estado que queda | Qué hace T20 |
|---|---|---|
| 1, antes de enviar | Mensaje `pendiente` sin `wamid` | Pasados N min no se puede distinguir de "se envió y murió antes del paso 3" → mensaje `desconocido` + `devolucion_fallida`. **No reenvía.** El operador ve "no sabemos si llegó" y decide. |
| 2 (Meta aceptó), antes del paso 3 | Igual que la fila anterior: el `wamid` se perdió | Igual: `desconocido`, **sin reenvío**. |
| 3 | Mensaje `enviado` con `wamid`, sin `devuelta_a_ia` | Completa el paso 4 una sola vez. |
| 4 | Estado final | Nada. |

### 9.6 Sincronizaciones externas
- Se toman con `UPDATE ... SET estado = 'en_curso', actualizado_en = now() WHERE id = :id AND estado = 'pendiente' AND proximo_intento_en <= now() RETURNING`. COMMIT antes de llamar afuera (I20).
- **Clasificación del resultado** [AUDITORÍA Q4]:

| Clase | Ejemplos | Qué se hace |
|---|---|---|
| **Transitorio** | timeout **antes** de enviar el pedido, fallo de conexión al abrir, HTTP 429, HTTP 5xx con respuesta recibida | `pendiente` con espera creciente y *jitter*, hasta el máximo de intentos → `fallida_definitiva` |
| **Permanente** | HTTP 401/403, error de validación, argumentos inválidos, 404 irrecuperable | `fallida_definitiva` **de inmediato**, sin reintentos inútiles |
| **Incierto** | timeout **después** de enviar, conexión cortada sin respuesta, crash con la fila `en_curso` | `desconocida`. Antes de cualquier reintento se **consulta** si el efecto existe (§3.6). Si se puede demostrar que no existe → `pendiente`. Si no se puede → queda `desconocida` para una persona. |

- Una fila `en_curso` sin avance en N minutos se trata como **incierta**, no como transitoria.

### 9.7 Bloqueo estructurado para el modelo [AUDITORÍA P6]
Mientras exista una acción viva de la conversación, cada turno le entrega al modelo un bloque de sistema **armado por código**, no redactado:
```
ACCION_PENDIENTE id=<id> herramienta=<nombre> estado=<pendiente|ejecutando|desconocida> propuesta_hace=<N min>
- NO afirmes que se ejecuto.
- NO la vuelvas a proponer.
```
La garantía no está en el prompt: una segunda propuesta equivalente la frena X18 en código.

---

## 10. Reinicio y reconstrucción desde la base

**Regla:** PostgreSQL es la verdad; la memoria acelera pero nunca decide. Producción corre `--workers 1 --threads 8` a propósito, justamente por `_sesiones` (`docker-compose.prod.yml`, servicio `motor`, comentario "UN SOLO worker") [VERIFICADO], y el autodeploy reinicia el motor varias veces por día. Las referencias `archivo:línea` de este contrato son ayudas de auditoría sobre `92ebe78`; lo que identifica el lugar es el servicio, la función o el comentario.

| Dato | Tras un reinicio sale de | Hoy |
|---|---|---|
| Si la IA responde | `conversations.control` | Dos columnas; las pausas que vivían solo en RAM se pierden (D9) |
| Si ya hubo escalada | `relevo_eventos` | `escalada_a_humano OR caso_id` (`api.py:652`) [MAPEO] |
| Asignación, pendiente interno, aviso | Columnas | — |
| Efectos externos pendientes | `sincronizaciones_externas` | Se pierden |
| Historial del modelo | `messages` (tabla de abajo), últimos 20 | `rol in ('user','assistant')`, sin autor (D8) |

### Reconstrucción del historial [DECISIÓN + AUDITORÍA]
**El `rol` decide la forma y el `origen` solo agrega el prefijo.**

| `rol` | `origen` | Entra al modelo como |
|---|---|---|
| `user` | `cliente` o `NULL` | `user`: contenido |
| `assistant` | `ia` o `sistema` | `assistant`: contenido |
| `assistant` | `humano` | `assistant`: `({autor_nombre}, del equipo) {contenido}` |
| `assistant` | `NULL` (legado) | `assistant`: contenido **intacto**, sin prefijo |
| `humano` (1 fila de legado) | — | `assistant`: contenido **intacto**, sin prefijo |
| `nota` | cualquiera | **nunca** |

- El formato de `humano` es **el mismo** que usa hoy el camino en vivo (`({quien}) {contenido}`, `api.py:4046-4050`) [VERIFICADO], con la etiqueta "del equipo". El camino en vivo y la reconstrucción usan **la misma función**; I13 se prueba comparándolos.
- **Legado sin procedencia: un solo bloque por conversación, nunca una marca por mensaje** [AUDITORÍA A3]. Casi todos los `assistant` históricos son de la IA; prefijar cada uno ensuciaría cientos de mensajes para cubrir unos pocos. Si la reconstrucción incluye **al menos un** mensaje `assistant` con `origen = NULL` (o la fila `rol = 'humano'`), antes del historial entra **un único** bloque de sistema armado por código:
  ```
  CONTEXTO HISTORICO LEGADO
  Parte del historial anterior al corte no tiene procedencia registrada.
  Los mensajes del lado del asistente sin procedencia pueden haber sido
  escritos por la IA o por una persona del equipo.
  No atribuyas su autoria con certeza.
  ```
  Los mensajes históricos entran después **sin tocar su contenido**. Si no hay ninguno sin procedencia, el bloque no aparece. Afecta solo a conversaciones abiertas al momento del corte (a lo sumo sus últimos 20 mensajes).
- Hoy las plantillas y la media de personas no entran a la memoria [MAPEO]. Con la función única entran igual por los dos caminos.

---

## 11. Compatibilidad con datos históricos

### 11.1 `messages.origen`
Principio de la auditoría: no se asigna `origen` sin evidencia, y **nunca se toca `rol`**.

**Resultado de G4 (medido en producción):** las dos reglas de evidencia propuestas en la v2.1 (`rol = 'nota'` con prefijo de autor; `rol = 'assistant'` con `estado_entrega` no nulo) identifican **0 filas** en producción. Por lo tanto:
- **Todo el histórico queda `origen = NULL`.** No hay backfill de procedencia. Las reglas de la v2.1 quedan descartadas, no pendientes.
- **Desde el corte de B2, `origen` es obligatorio** en toda fila nueva (I4). Una inserción sin `origen` falla.
- La 1 fila con `rol = 'humano'` (A4) conserva `origen = NULL`; lo que la distingue es su `rol`, y se lee según §10.

**Lectores ante `NULL`:**
- **Cola:** `rol = 'user'` cuenta como lado cliente; `rol = 'assistant'` o `'humano'` → regla 10 de §4.2 (humano, visible).
- **Modelo:** §10: mensajes intactos + un único bloque de legado por conversación.
- **UI:** "autoría no registrada".

### 11.2 `conversations.control`
- **Backfill:** `control = 'humano'`, `control_motivo = 'escalada'` donde `estado = 'abierta' AND escalada_a_humano AND necesita_atencion_humana`, la misma regla que hoy decide la pausa al reconstruir (`api.py:626`). El resto queda `ia`.
- Evento `escalada` sintético con `datos = {"legado": true}`.
- **Asignación:** `asignada_a_nombre = tomada_por`, `asignada_a_usuario_id = NULL`, solo si queda `control = humano`. Las diferencias van al reporte de migración.
- **Sin sincronizaciones retroactivas:** las conversaciones escaladas de legado sin `caso_id` se listan en el reporte, no se reintentan solas.

**Medición de producción sobre las 46 candidatas (A6, A7):**
- **30 son de canales de prueba** (`whatsapp-simulado`, `api`). Siguen el mismo modelo, pero **no entran a la cola operativa**. Política de migración para esos hilos de prueba de legado, a decidir con el dato antes del corte: cerrarlos con `cerrada_por_tipo = operador` y `desenlace = otro`, o dejarlos en `control = humano` visibles solo en la vista de simulación. Ninguna de las dos opciones toca canales reales.
- **16 son de WhatsApp real** y quedarían con `control = humano` **sin `atendida_manual`** — o sea, clientes que según el modelo esperan a una persona y que nadie atendió. **Gate G8:** antes del corte de control, una persona las revisa **una por una** y decide para cada una: seguir en humano, cerrar (con desenlace), resolver el estado externo (caso/ticket) o volver a la IA cuando corresponda. **No se ocultan ni se resuelven automáticamente.** La decisión de cada una queda como evento del relevo (`datos = {"legado": true, "g8": <decision>}`).

### 11.3 Escritura en paralelo del legado
Hasta migrar todos los lectores, cada transición escribe también `escalada_a_humano` / `necesita_atencion_humana` / `tomada_por` en forma consistente.

Lectores a migrar [MAPEO, completar antes de implementar]:
- `lib/conversaciones/estado.js`
- `ultima_actividad` (`db.py:439-482`)
- `mensajes_de`, `atendida_por_humano`, `conversaciones_sin_respuesta`
- `_sesion_nueva`
- métrica de escalamiento (§8.3)
- supervisor y analista

### 11.4 `acciones_propuestas` existentes
- `conversation_id = NULL`. `aprobada` → `ejecutada_ok` / `ejecutada_fallo` según `codigo_error`.
- **Medido en producción: 36 en `pendiente`** (A5), invisibles hoy porque ninguna pantalla las muestra.
- **No se les pone un vencimiento para que desaparezcan.** **G3 es gate bloqueante de B5:** una persona revisa las 36.
  - **Obsoletas o de prueba** → `cancelada`, con evento y motivo.
  - **Todavía necesarias** → **no se aprueban tal cual**: se vuelven a proponer desde el contexto actual (con `conversation_id`), y pasan por la revalidación de §3.7.
- **Ninguna acción de legado sin `conversation_id` se ejecuta automáticamente**, ni por aprobación, ni por reconciliador, ni por migración (X24).

### 11.5 Cómo se entrega
- Migraciones por el ledger (`supabase/`), una por concepto:
  1. mensajes
  2. conversaciones + `relevo_eventos`
  3. `sincronizaciones_externas`
  4. acciones
- Cada migración es **solo DDL aditivo** (columnas nullable, tablas nuevas, índices) y **no cambia comportamiento**. **Sin `UPDATE` masivo dentro de la migración** [PRODUCCIÓN].
- Secuencia: (1) DDL aditivo → (2) escritura en paralelo para filas nuevas → (3) **backfill histórico en lotes cortos**, fuera de la migración → (4) migrar lectores → (5) retirar el legado.
- **Volumen medido (A8):** 2584 mensajes (1,3 MB) y 298 conversaciones. **No hace falta partir el backfill por rendimiento.** Se mantiene igual el **despliegue escalonado por seguridad de conducta** (DDL → escritura en paralelo → backfill → lectores → retiro) y el preflight de `lock_timeout`, locks y transacciones retenidas (G6). **La ejecución la decide el área de producción y despliegue.**
- Índices sobre tablas con tráfico: `CREATE INDEX CONCURRENTLY`, fuera de transacción, si el ledger lo permite; si no, se acuerda con el área de producción.
- El trabajo se entrega como commits y hashes en la rama de la fase; **no se pushea desde ella**. Integra y despliega un único responsable de producción (separación de git, no de diseño).
- Después de cada despliegue: `cli/diferencias_config.py` y `cli/evaluar.py rapilink --humo --base`.

---

## 12. Tests de comportamiento obligatorios

Afirman **efectos** en la base, la traza o las llamadas HTTP simuladas, nunca la existencia de un mecanismo. Patrón: `tests/test_pausa_escalada.py`, contra base local. **"Reinicio"** = vaciar `_sesiones`. **"Crash"** = cortar el flujo con una excepción inyectada entre dos pasos.

| # | Escenario | Afirmaciones |
|---|---|---|
| S1 | **Camino feliz.** IA → escala → A toma → A responde y sigue → cliente responde → A responde y devuelve → IA continúa → cliente confirma → cierre | Estados E0→E1→E2→E2→E2→E0→E0→E3 (**T15b**). `necesita_accion_de`: ia→humano→humano→cliente→humano→ia→ia→nadie. Eventos en orden. Caso abierto tras la devolución y cerrado al final. |
| S2 | Dos operadores toman a la vez | Un 200, un 409 con el dueño. Un evento `tomada`. |
| S3 | Reinicio tras un mensaje humano | Historial reconstruido con `(María, del equipo) …`, igual al historial en vivo. Pausa intacta. |
| S4 | Intervención sin escalada | `control = humano/intervencion`. La IA no responde el siguiente mensaje. Cero llamadas al CRM. Tasa de escalamiento sin cambios. |
| S5 | Aprobación pendiente | `necesita_accion_de = aprobacion`, visible en la conversación, cero escrituras externas. |
| S6 | El cliente escribe durante una aprobación | Mensaje guardado. La acción sigue `pendiente`. El modelo recibe el bloque `ACCION_PENDIENTE`. Cero ejecuciones. |
| S7 | Devolver con una aprobación pendiente | Permitido. `control = ia`. La acción sigue visible. `necesita_accion_de = aprobacion`. |
| S8 | D3 falla cerrado | `POST /chat` con `canal = 'whatsapp'` → 403 y cero filas. Simulada con el mismo número → sesión distinta. |
| S9 | Doble aprobación simultánea | Una ejecución (mock = 1). Un 409. |
| S10 | Aprobar con la conversación cerrada | 409, cero ejecuciones. |
| S11 | Escalada con CRM caído y reinicio | `control = humano` guardado. `crear_caso` pendiente. Tras el reinicio sigue en pausa. El siguiente mensaje **no** crea otra escalada. |
| S12 | Caso cerrado afuera, **sin asignación**, y reinicio | `control = ia` + evento {aplicado: true}. Tras el reinicio la IA responde. |
| S13 | Barrido con una verificación pendiente | No cierra. Sin la verificación, cierra. |
| S14 | Notas fuera del modelo | Una conversación con nota vence: la nota no está en el insumo del resumen ni en el historial reconstruido. |
| S15 | Reintentar | Misma clave → una fila. Si estaba en error, reintenta la entrega. |
| S16 | Legado `rol = assistant`, `origen NULL` en el historial | Cola: `humano` si es el último que cuenta. Modelo: **exactamente un** bloque `CONTEXTO HISTORICO LEGADO` antes del historial, y el mensaje con su contenido **byte a byte igual** al guardado. Sin mensajes de legado → cero bloques. Con varios → sigue habiendo uno solo. |
| S17 | Inactividad con control humano | No cierra. El mensaje entra al mismo hilo. |
| S18 | El cliente responde a una conversación asignada | La asignación se conserva. `necesita_accion_de = humano`. En "Mías" con marca, no en "Por atender". |
| S19 | Pendiente interno | Con la marca → `humano`. El siguiente mensaje de A sin la marca lo cierra. |
| S20 | Dos turnos simultáneos que deciden escalar | Una reserva, un evento `escalada`, un caso y un ticket. |
| S21 | Plantilla en canal no WhatsApp | 400 y cero filas. |
| **S22** | **Responder y devolver con fallo de Meta** | Mensaje en error. Evento `devolucion_fallida`. `control = humano`. Asignación intacta. **Cero `devuelta_a_ia`.** `necesita_accion_de = humano`. |
| **S23** | **Crash después de reservar la escalada y antes de crear caso y ticket** | Conversación en E1, visible en "Por atender". Sincronizaciones `pendiente`. Siguiente mensaje del cliente: la IA **no** responde (T10). T20 crea el caso **una sola vez**, incluido el reintento con un caso que ya existía por nombre. |
| **S24** | **Caso cerrado afuera mientras Pedro tiene la conversación asignada** | `control = humano`, asignación = Pedro, `aviso_relevo = caso_externo_cerrado`, evento {aplicado: false}. La IA no responde. |
| **S25** | **Aprobación envejecida o precondición cambiada** | (a) Pasado `vence_en` → `vencida`, cero escrituras. (b) La lectura de revalidación devuelve otro estado → `vencida`, cero escrituras. (c) La lectura de revalidación falla por red → sigue `pendiente`, cero escrituras. |
| **S26** | **Legado `rol = user`, `origen NULL`** | Entra al modelo como `user` (no `assistant`). En la cola cuenta como lado cliente. |
| **S27** | **Resolver a mano con fallo al cerrar el ticket** | Conversación cerrada. `cerrar_ticket` `pendiente` y visible. T20 reintenta. Tras N fallos, `fallida_definitiva` visible. La conversación **no** se reabre. |
| **S28** | **Dos propuestas equivalentes** | Una sola fila viva. Evento `accion_propuesta_duplicada`. El modelo recibe la existente. |
| **S29** | Crash en cada paso de T6 | Después del paso 3 (`wamid` guardado) → T20 completa el paso 4 una sola vez. Después del paso 1 o del 2 (sin `wamid` guardado) → pasados N min, mensaje `desconocido` + `devolucion_fallida`, control humano intacto y **cero reenvíos**. |
| **S30** | `NO_DETERMINADO` + tomar + soltar | `necesita_accion_de = humano` después de ambos. Solo T19, T7, T8 o T17 lo resuelven. |
| **S31** | Evento con campo no declarado o con un payload externo | La escritura se rechaza y no hay cambio de estado (I12). |
| **S32** | Config con una herramienta aprobable sin `revalidar` o sin `vigencia_minutos` | Modo advertencia: carga y registra la advertencia nombrando la herramienta. Modo error (tras activar Q3): la carga falla con ese mismo nombre. |
| **S34** | **La fila de legado `rol = 'humano'`** [PRODUCCIÓN A4] | Reconstrucción: `assistant` con contenido intacto (nunca `user`), y su conversación recibe el bloque de legado. Cola: no cuenta como respuesta con entrega aceptada (regla 10). La ventana de 24 h no la cuenta. |
| **S35** | **Cola operativa y canales de prueba** [A6] | Una conversación `whatsapp-simulado` con `control = humano` no aparece en "Por atender" operativa; sí en la vista de simulación. |
| **S36** | **Nada sale al cliente con `control = ia`** [AUDITORÍA] | Con `control = ia` en canal real: `POST /mensajes`, `/humano/media` y `/plantilla` → 409, **cero filas** y **cero llamadas a Meta**. Después de T8 (intervenir) los tres funcionan. La nota interna funciona en los dos estados. |
| **S33** | Clasificación de fallos de sincronización | (a) 503 → `pendiente` con `proximo_intento_en` futuro. (b) 403 → `fallida_definitiva` sin reintentos. (c) Timeout después de enviar → `desconocida`; el siguiente paso de T20 **consulta** antes de crear; sin forma de demostrar que no existe → sigue `desconocida` y **cero** creaciones nuevas. (d) La misma transición encolada dos veces → una fila (UNIQUE). |

**Casos dorados** nuevos en `evaluacion/rapilink.casos.yaml`: S3, S4 y S6, que afirman sobre la traza contra el motor real. Los que hoy afirman "escalada no confirmada → la IA sigue" se **actualizan en el mismo commit funcional de B4** (Q5).

---

## 13. Defectos que este contrato absorbe

| Id | Defecto | Evidencia | Marca | Lo cubre |
|---|---|---|---|---|
| D1 | Responder desde la bandeja no puede devolver a la IA | `api/conversaciones/[id]/humano/+server.js:35` solo `{tenant, mensaje}` | VERIFICADO | T6, T7 |
| D2 | Respuesta de persona sin autor | Mismo proxy | VERIFICADO | X13 |
| D3 | Texto de operador guardado como mensaje del cliente en conversación no escalada. No sale por Meta, pero mueve la ventana, `mensajes_tras_escalar` y el cierre por plazo, y comparte sesión con el canal real | `+page.svelte:1330-1343`; `/chat` sin envío [MAPEO] | VERIFICADO (no envío: MAPEO) | X1, X2, T8 |
| D4 | Dos operadores toman el mismo caso | `tomar_caso` sin condición | VERIFICADO | T2, §9.1 |
| D5 | El cliente que vuelve a escribir tras la respuesta humana no reaparece | `estado.js:33`, `atendida_manual` permanente | VERIFICADO | §4.2, S18 |
| D6 | No se distingue IA de persona; **ningún código escribe hoy** `rol = 'humano'`, pero **producción tiene 1 fila de legado** con ese rol (medido en producción) | `db.py:1113`, 4 consultas | VERIFICADO (la fila: medición de producción) | §3.2, §4.6, §10, S34 |
| D7 | Acciones propuestas invisibles: sin pantalla y sin vínculo a conversación | Ningún llamador en `django-crm` | MAPEO | T12–T14, §3.4 |
| D8 | Tras un reinicio, la IA ve como propio lo que escribió una persona | `historial_para_el_modelo` lee `rol, contenido` | VERIFICADO | §10, I13 |
| D9 | Pausa solo en memoria si el CRM lanza excepción o falta la herramienta | `escalamiento.py:680-684, 785-788` | VERIFICADO | T1, §3.6, S11, S23 |
| D10 | Un caso cerrado afuera levanta la pausa solo en memoria | `api.py:1010-1015` | VERIFICADO | T11, S12, S24 |
| D11 | Aprobar sin transición condicionada; `revisado_por` del cuerpo; rechazo sobre aprobada; "aprobada" aunque falle; sin revalidación | `api.py:4861-4923`, `db.py:2235-2241` | VERIFICADO | §3.7, §9.3, S9, S25 |
| D12 | Las notas internas entran al insumo del resumen de una conversación vencida sin resumen previo | `db.py:2349-2355`, `api.py:744-745` | VERIFICADO (aparición en un resumen real: sin verificar) | X8, S14 |
| D13 | El cierre por inactividad cierra conversaciones que esperan a una persona | `db.py:2338-2345`, `api.py:739-750` | VERIFICADO | T18, S17 |
| D14 | El barrido por plazo no revisa verificaciones pendientes | `db.py:954-991`, `operativo.py:164-202` | MAPEO | T16, S13 |
| D15 | "Reintentar" inserta una fila nueva | `+page.svelte:363-372` → `agregar_mensaje_humano` | VERIFICADO | X11, S15 |
| D16 | La plantilla guarda la fila antes de validar el canal | `api.py` ~3895 vs ~3905 | MAPEO | X12, S21 |
| D21 | Tres guardas reescribían la respuesta después de que el motor la agregara al historial y corregían solo la fila: el modelo recordaba en vivo un texto que el cliente nunca leyó | `atender_turno`, rewrites de traspaso, aviso de escalada y pregunta de cierre | VERIFICADO | Resuelto en B2.3 (un punto al final del turno); I13 |
| D22 | "Soltar" nunca funcionó: la pantalla mandaba `soltar: true` y el proxy de `/atender` lo descartaba; el motor volvía a tomar la conversación | `api/conversaciones/[id]/atender/+server.js` | VERIFICADO | Resuelto en B3.2 |

**Relacionados, fuera de este contrato:**
- Sin `MOTOR_SERVICE_TOKEN` configurado, el motor no exige token (`api.py:486-487`) [MAPEO]. Condición previa al deploy (§16, G1).
- Las respuestas del bot por webhook no guardan `wamid` ni `estado_entrega` [MAPEO].
- La ficha técnica de TV va solo al ticket, recortada a 400 caracteres, sin fuente ni fecha [MAPEO]. Insumo del paso "ficha con frescura".

**Corrección de documentación ya hecha:** CLAUDE.md decía que el texto de espera variaba según el motivo y no mencionaba el silencio después de que escribe una persona. Quedó alineado con `api.py:971-1009`.

---

## 14. Decisiones de la ronda 1 y preguntas abiertas

### 14.1 Resueltas en la primera ronda de auditoría
| # | Tema | Decisión |
|---|---|---|
| P1 | Acción primaria del botón | "Responder y devolver a la IA" como default de plataforma; el tenant puede cambiarlo; la otra opción siempre visible. La config se escribe solo si el tenant lo cambia. |
| P2 | Quitarle una conversación a otro | Solo `ADMIN`, con motivo y evento. Entre pares, por tenant, cuando se pida. |
| P3 | Revalidación | Por herramienta, declarativa y obligatoria + vigencia. Si no se puede comprobar, no se ejecuta (§3.7). |
| P4 | Avisar al cliente de aprobación o rechazo | Nada automático. Con control IA, el resultado llega como contexto. Con control humano, decide la persona. |
| P5 | Resolver a mano cierra caso y ticket | Sí por defecto, desmarcable. Los fallos quedan como sincronización pendiente visible y reintentable. |
| P6 | Devolver con una acción pendiente | Sí, con bloque estructurado y deduplicación (§9.7, X18). |
| P7 | Fin de una intervención | Nada automático. Solo un aviso por inactividad del operador. |
| P8 | Qué resuelve `NO_DETERMINADO` | Revisión explícita (T19), o T7/T8/T17. Tomar y soltar no. |
| P9 | Simulación | El mismo modelo. `origen = cliente` en canal simulado = representa al lado cliente. |

### 14.2 Resueltas en la ronda 2
| # | Tema | Decisión |
|---|---|---|
| Q1 | `atendida_manual` en el cierre por confirmación | **T15a (humano) lo exige; T15b (IA) no.** Con control IA el cierre funciona así hoy, y exigirlo impediría cerrar conversaciones que la IA resolvió sola. |
| Q2 | Deduplicación de `crear_ticket` en WispHub | **Sin reintento automático** hasta demostrar deduplicación (§3.6). Resultado incierto → `desconocida`, no un segundo ticket. |
| Q3 | Revalidación vs medición ON/OFF | **No se quita la aprobación humana.** Se construye todo lo que no escribe config; la config de Rapilink se activa al cerrar la medición; el validador pasa de advertencia a error en ese mismo cambio (§3.7). |
| Q4 | Tiempos por defecto | Aprobados **como defaults de plataforma**, junto con la taxonomía de §9.6: hasta 8 intentos con espera creciente y *jitter*, con tope ~6 h, **solo para errores transitorios**; 10 min `ejecutando` → `desconocida`; 15 min mensaje sin `wamid` → `desconocido`. **Corregido por A5:** las acciones de legado **no** reciben 24 h de vigencia; pasan por la revisión de G3. No son configuración por tenant. |
| Q5 | Fail-closed al escalar | **Aprobado, y adelantado a B3.2 (C1).** Si el evaluador decidió que hace falta una persona, un fallo de integración no le devuelve la conversación a la IA. Los casos dorados que afirmaban la conducta vieja se actualizan **en el mismo commit funcional**, con el mensaje diciendo que es una política nueva y no una regresión. |

### 14.3 Abiertas
Ninguna de arquitectura. Las verificaciones pendientes (deduplicación en WispHub, escritores para el backfill, llamadores de `/chat`) son **precondiciones de fase** (§15), no decisiones de diseño.

---

## 15. Construcción por fases

Nada de "big bang" [AUDITORÍA]. Cada fase sigue el mismo ciclo:

```
se construye en feature/bandeja-relevo → tests → commits → auditoría de Dexter
→ integración en fix/integracion-wisphub con las suites combinadas y los gates → un único responsable despliega
```

| Fase | Contenido | Precondiciones propias | Tests |
|---|---|---|---|
| **B1** | D3 falla cerrado (`/chat` rechaza canal real) + clave de sesión con canal + en la pantalla, con la IA atendiendo un hilo real, nada se le envía al cliente (texto, adjunto, voz, plantilla; X25) | Buscar todos los llamadores de `/chat` (cli, baterías, n8n) | S8 |
| **B2** | `messages.origen` (obligatorio desde el corte) + autor + clave de idempotencia; escritura en paralelo; formateo único del historial con marca neutral para legado (D8, A3, A4); notas fuera del resumen (D12); reintentar sin duplicar (D15); plantilla valida antes de guardar (D16) | G4 ya resuelto: sin backfill de procedencia | S3, S14, S15, S16, S21, S26, S34 |
| **B3** | En cinco pasos: **B3.1** esquema aditivo; **B3.2** transiciones con escritura en paralelo (escalar fail-closed con legado, cierre externo solo aviso) y `control_efectivo`; **B3.3** guardas del backend por `control_efectivo` en texto, media y plantilla; **B3.3b** compuerta durable del modelo por `control_efectivo` y T8 Intervenir (C7, C8); **B3.4** toma atómica y reasignación ADMIN (D4); **B3.5** proyección `necesita_accion_de` y cola operativa separada de la simulación. T2–T8, T10, T11, T19; D1, D4, D5, D9, D10, D13, D22 | **G8** antes del corte de control, con adopción explícita (I21); política para los 30 hilos de prueba de legado; T6 en canal real ya no espera G9 (verde) | S1, S2, S4, S11, S12, S17–S20, S22, S24, S29, S30, S31, S35, S36 |
| **B4** | `sincronizaciones_externas` + T20 con cadencia propia + taxonomía de errores (la parte de conducta de T1 fail-closed ya entró en B3.2) | Verificar deduplicación en WispHub (Q2); cadencia de T20 acordada con producción (G7) | S23, S27, S33 |
| **B5** | Acciones propuestas: `conversation_id`, estados, reserva, vigencia, deduplicación, bloqueo estructurado; motor y validador de revalidación en modo advertencia | **G3 (bloqueante):** revisión de las 36 acciones de legado; la activación de la config de Rapilink espera el cierre de la medición (Q3) | S5, S6, S7, S9, S10, S25, S28, S32 |
| **B6** | Frontend completo del relevo (controles, tarjeta de acción, estado de sincronización, compositor) + cierre con desenlace (T15a, T15b, T16, T17) y catálogo con `categoria_base` | — | S13 + recorrido de pantalla |
| **B7** | Migración de lectores del legado + backfill histórico en lotes + retiro gradual de `escalada_a_humano` / `necesita_atencion_humana` / `tomada_por` como fuente | Volumen medido y mecánica aprobada por producción (G6) | Consultas de invariantes sobre la base |

**Archivos, por referencia:**
- **Motor:** `nucleo/persistencia/db.py`, `nucleo/canales/api.py`, `nucleo/seguimiento/escalamiento.py`, `nucleo/seguimiento/operativo.py`, `nucleo/reloj.py`, `nucleo/config/schema.py` y el módulo nuevo `nucleo/relevo/` (proyección, esquemas de eventos e intenciones, formateo del historial).
- **Frontend:** `routes/api/conversaciones/[id]/*`, rutas nuevas (intervenir, devolver, revisar evaluación, acciones), `lib/conversaciones/estado.js`, y `routes/(app)/conversaciones/[id]/+page.svelte` con componentes extraídos.
- **Tests:** `tests/test_relevo_*.py` (S1–S36) y casos dorados.

---

## 16. Riesgos de producción y gates previos al deploy

### 16.1 Gates [DECISIÓN + AUDITORÍA]
Los verifica quien despliega **antes** de desplegar los endpoints nuevos. Ninguno exige leer ni imprimir secretos.

| Gate | Qué se comprueba | Cómo, sin exponer el secreto |
|---|---|---|
| **G1** | El motor exige `MOTOR_SERVICE_TOKEN` | La variable está presente (sí/no, sin valor); un request sin token a `/chat` → 401/403; un request válido desde el proxy funciona. **Estado: VERDE en producción.** |
| **G2** | El reloj corre en producción | Ya medido en producción: `RELOJ_HABILITADO=1`, `motor-reloj` activo, ciclo ~60 min. Se vuelve a medir antes de cada fase que dependa del reloj (el default `0` del compose no describe producción). |
| **G3** | **Bloqueante de B5.** Las 36 acciones `pendiente` de legado revisadas por una persona | Hecho (conteo): 36. Falta: la decisión de cada una — `cancelada` o re-propuesta desde contexto actual (§11.4). |
| **G4** | Evidencia del backfill de `origen` | **Hecho: 0 filas** con las reglas propuestas → todo el histórico queda `NULL` (§11.1). |
| **G5** | Casos dorados actualizados y en verde | `cli/evaluar.py rapilink --humo --base` después de aplicar |
| **G6** | Preflight de DDL y backfill [PRODUCCIÓN] | Volumen medido; sesiones `idle in transaction` = 0 y locks problemáticos = 0 sobre `asistente.conversations`, `asistente.messages` y `asistente.acciones_propuestas` (`pg_stat_activity`, `pg_locks`, solo lectura) inmediatamente antes de aplicar; estrategia de backfill aprobada por el área de producción. Con sesiones retenidas **no se aplica**, y subir `lock_timeout` no es la primera respuesta. |
| **G8** | **Revisión operativa de las 16 conversaciones reales** que quedarían en control humano sin `atendida_manual` [PRODUCCIÓN A7] | Antes del corte de control (B3): una persona decide cada una — seguir en humano, cerrar con desenlace, resolver el estado externo o volver a la IA. Queda registrada. Ninguna se oculta ni se resuelve sola. |
| **G9** | **Recibo de entrega punta a punta** [PRODUCCIÓN A1] | **Gate inicial:** envío real **controlado** desde la Bandeja → proxy → motor → Meta acepta → **`wamid` guardado en PostgreSQL** → el webhook correlaciona los acuses con esa fila. Hoy producción tiene 0 `wamid` guardados en 2584 mensajes. **No se provoca un reinicio de producción para esta prueba** [AUDITORÍA]: con el `wamid` en la base, la durabilidad ya está; la reconstrucción después de reiniciar se comprueba en el **siguiente reinicio o despliegue natural**. La arquitectura sí debe sobrevivir reinicios (§10). **T6 no se activa para canal real hasta aprobar el gate inicial.** Aceptado (`wamid`), entregado y leído (acuses) se verifican por separado. **Estado: VERDE en producción (16/09/2026)** — G9-A `wamid` persistido, G9-B entregado correlacionado. Ya no es un gate pendiente. |
| **G7** | Reconciliador [AUDITORÍA] | T20 habilitado; **cadencia efectiva medida** y compatible con los plazos de Q4 (1–5 min, no el ciclo horario); una sincronización artificial de laboratorio recorre `pendiente → en_curso → hecha` **sin tocar un sistema externo real**. |

### 16.1b Restricciones de implementación del área de producción
| Id | Restricción | Consecuencia en este contrato |
|---|---|---|
| **P-A** | Producción tiene `idle_in_transaction_session_timeout = 60s` en `postgres`, `crm_user` y `motor_user` | Ningún flujo espera una operación externa con una transacción abierta (I20, X23). Patrón obligatorio: transacción corta para reservar o guardar la intención → COMMIT → efecto externo → transacción corta para guardar el resultado → COMMIT. Aplica a T1, T6, T13, T17 y T20. |
| **P-B** | `lock_timeout = 1s`, y `conversations` y `messages` tienen tráfico permanente | Un `ALTER TABLE` puede fallar por no conseguir el lock aunque sea instantáneo. Preflight G6 antes de cada migración; con sesiones retenidas, no se aplica. |
| **P-C** | Sin backfills dentro de las migraciones de DDL | §11.5: DDL aditivo → escritura en paralelo → backfill → lectores → retiro. Con el volumen actual (A8) no hace falta partirlo por rendimiento; el escalonamiento es por seguridad de conducta. Ejecución a cargo del área de producción. |
| **P-D** | Las referencias `archivo:línea` envejecen | Se identifica por servicio, función o comentario; la línea es solo una ayuda sobre `92ebe78`. |

### 16.2 Riesgos
| Riesgo | Mitigación |
|---|---|
| Doble escritura del legado inconsistente durante la transición | Invariantes verificadas por consulta después de cada despliegue; lectores migrados de a uno |
| El backfill de `control` difiere de la pausa real en memoria | Misma regla que cualquier reinicio (`api.py:626`); el reporte de migración lista las diferencias |
| La regla de backfill por `estado_entrega` resulta falsa | G4; si falla, esa regla se elimina y quedan `NULL` |
| Bloquear `/chat` con `canal = 'whatsapp'` rompe un llamador desconocido | Buscar llamadores (cli, baterías, n8n) antes; registrar cada rechazo con su origen |
| Leer `control` de la base en cada turno suma latencia | Una lectura por clave primaria |
| Aparecen de golpe acciones `pendiente` que hoy están invisibles | G3 y decidir con el dato |
| El reconciliador no corre o corre demasiado lento para sus plazos | G7 (cadencia medida); además la bandeja muestra toda sincronización no `hecha`, así que nada queda invisible aunque T20 se atrase |
| Un `ALTER TABLE` no consigue el lock en horario de tráfico | G6; reintentar en otra ventana, no subir `lock_timeout` |
| Un backfill largo retiene locks o sesiones | P-C: lotes cortos, fuera de la migración, con la mecánica que decida producción |
| La revalidación declarativa no alcanza para expresar una precondición real | Esa herramienta deja de ser aprobable hasta que se pueda expresar (falla cerrado) |
