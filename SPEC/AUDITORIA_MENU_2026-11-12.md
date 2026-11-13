# Auditoría del menú — cómo funciona cada sección, cómo se engranan, qué está mal y qué falta (12/11/2026)

**Qué es.** Una pasada de solo lectura sobre las 27 entradas del menú (`lib/v2/components/Sidebar.svelte`), hecha por ocho agentes en paralelo —uno por grupo del menú y uno transversal— y consolidada por la sesión principal. Es **historia con evidencia** (CLAUDE.md §1): no manda; las decisiones que salieron de acá están en PRD §8.23. Todo lo marcado **V** se leyó en el código con `archivo:línea`; **I** es inferido sin ejecutar. Nada se midió contra producción.

**Para qué sirve.** Cada hallazgo de abajo es una entrada de trabajo ya ubicada. Cuando se tome uno, se cierra acá con el hash.

---

## 1. El diagnóstico en una página

1. **Las pantallas del ISP son islas.** Las heredadas de BottleCRM se enlazan densamente entre sí (cuentas ↔ contactos ↔ prospectos ↔ negociaciones ↔ facturas ↔ tickets); las de Dexter no: `conversaciones → ∅` (salvo el ticket), `centro-mando → ∅`, `instalaciones → ∅`, `inventario → ∅`, `supervisor-noc → tickets, capacidad`. Para ir de un ticket al chat, de una orden detenida al cliente que escribió, o de una instalación a su conversación, había que buscar a mano por teléfono. **V**
2. **No hay una identidad única del cliente.** Cinco representaciones sin clave de unión persistida: `conversations.id_cliente`, `Case.external_service_id`, `OrdenDeCampo.cliente_*` (copia), `Solicitud.telefono/documento`, la ONU en SmartOLT. `accounts` está vacía en producción (237 de 237 casos sin cuenta, medido el 25/09 en `cases/models.py:218-262`). **V**
3. **Sigue habiendo aprobaciones humanas para trabajo no crítico** (PRD §2 las llama pendientes): el Supervisor NOC nace en `NIVEL_OBSERVAR` con sus diez tareas apagadas; cerrar un ticket pasa por `ApprovalRule pre_close`; la factibilidad de cada instalación la decide una persona aunque la cobertura barrio → zona → cuadrilla ya se calcula. **V**
4. **Lo que el equipo marca para enseñarle a Dexter no llega a Dexter**: los ejemplos del Manual no los lee ningún agente ni la evaluación; aprobar una revisión no tiene efecto; la Base de conocimiento (`/solutions`) no la lee el RAG. **V**
5. **Un tercio del menú es herencia del CRM sin alimentación propia**: Cuentas, Contactos, Base de conocimiento, Tareas, Objetivos, Facturas (8 subpantallas), Registro de horas. Ninguna la escribe el motor; varias confunden («¿dónde está la factura del cliente?» → en WispHub, no acá). **V**
6. **Tres huecos de privacidad por rol**, todos del mismo tipo: la ficha completa del cliente (cédula, dirección, teléfono, saldo) la ve cualquier rol en la Bandeja y en el ticket; el PDF del expediente de instalación (foto de cédula, recibo, firma) lo lee cualquier autenticado. **V**

---

## 2. Por grupo del menú

### Operación en vivo

**Hoy (`/`)** — seis fuentes en paralelo (`lib/server/v2/hoy-operacion.js`), función pura con pruebas, enlaza bien a cada cola.
- Media **V** — pedía `/conversaciones` sin `cerradas_dias` (la Bandeja manda 30): la portada era la consulta más cara. **Arreglado el 12/11.**
- Baja **V** — el estado vacío afirmaba «sin órdenes detenidas ni pedidos» para roles a los que esas fuentes se les ocultan por 403. **Arreglado.**
- Baja **V** — no se refresca (la Bandeja sondea cada 8 s). Las bandas «sin asignar»/«revisar» mandan a `/conversaciones` a secas: el layout no lee `searchParams`.

**Conversaciones (`/conversaciones`)** — master-detail sobre la proyección del motor; ticket ↔ chat bidireccional y bien hecho (`CasePanel.svelte:135`, `tickets/[id]/+page.server.js:85`).
- **Alta (producto) V** — la Bandeja **aprueba pero no rechaza**: `ActionsPanel.svelte` solo ofrece «Aprobar y ejecutar»; el motor tiene `POST /acciones/propuestas/<id>/rechazar` (`api.py:11189`) sin proxy ni botón. La evidencia de autonomía ganada nunca recibe el «no».
- Media **V** — `CAMPOS_FICHA_CLIENTE` (`api.py:9295`) incluye cédula, dirección, teléfono, email y saldo, y la ruta no mira rol (`:9302-9397`); `CustomerPanel.svelte:145-181` lo pinta a todos. Las pestañas de contexto tampoco se filtran por rol (`[id]/+page.svelte:420-426`).
- Media **V** — `DELETE /api/conversaciones/<id>` solo exige estar autenticado (motor `api.py:13524` solo tenant). Nadie lo llama desde la Bandeja, pero borrar datos es crítico (PRD §2).
- Baja **V** — `atender/+server.js:62-66` empareja el dueño del ticket por `name === email`; si falla no avisa en pantalla. El log llevaba el error crudo del CRM (**arreglado**). `humano/+server.js` hacía `request.json()` sin `catch` → 500 por un cuerpo malformado (**arreglado**).
- Único `href` saliente de toda `lib/conversaciones`: el ticket. No se llega a la solicitud de instalación, a la orden/Supervisor NOC (`CasePanel.svelte:261-270` pinta `ticket_operativo` como chip sin enlace) ni al agente.

**Supervisor NOC IA (`/supervisor-noc`)** — corta por rol en el servidor (`ROLES_GESTION`), dos lecturas esperadas y el resto en promesas; enlaza a `/tickets/{caso_id}` y `/capacidad`.
- **Alta V** — nace pidiendo permiso para lo no crítico: sin fila la empresa está en `NIVEL_OBSERVAR` (`operaciones/autonomia.py:102`) y las diez tareas exigen `exige_nivel: 3` **más** delegación (`tareas_delegadas.py:66-110`), con un docstring que lo justifica por la regla anterior al 02/11. Pasar a despacho, armar la jornada, crear órdenes, cargar material y cerrar lo revisado están en la lista de no críticas de PRD §2.
- Media **V** — Google Fonts por CDN en ocho pantallas (`+page.svelte:1194-1199`, ajustes, cuadrillas, despacho, fallas, planes, plantillas; también Bandeja e Inventario): tercero no nombrado en la autorización de tratamiento y dependencia de internet saliente.
- Baja — el menú lo muestra a todo rol y un USER rebota en un candado; `ChatBurbuja` se monta sin gate de rol (**I**); dos hojas de estilo a la vez y una página de 2.807 líneas. No enlaza a la conversación que originó una propuesta, ni a `/agentes` desde «Autonomía ganada».
- *No confirmado:* el agente señaló que el comentario «ACEPTAR NO EJECUTA NADA» (`supervisor-noc.js:185`) era falso; `+page.server.js:160` sostiene lo contrario y la evidencia citada (`:182`) es del ciclo, no de la revisión. Queda sin tocar hasta medirlo.

**Centro de mando (`/centro-mando`)** — oficina isométrica (PixiJS) con la ficha de cada puesto; eventos por lista blanca sin datos de cliente.
- Media **V** — tres pantallas para dos preguntas: «Qué puede hacer» de la ficha (`FichaDePuesto.svelte:381-400`) es la misma lectura que `/agentes` sin el botón para cambiarla. **Cero enlaces salientes.**
- Baja **V** — título «Oficina virtual» vs menú «Centro de mando» (**arreglado**); cabecera contradictoria (`+page.svelte:7-12`); `/centro-mando/spike-three` (prototipo Three.js) navegable en producción con datos reales, sin decisión tomada.

**Asistente (`/asistente`)** — chat del colaborador con el motor; sin historial entre recargas; es además donde se entrena (`CorregirAgente`).
- Media **V** — se solapa con el chat del Supervisor: dos burbujas, dos backends, dos historiales; un ADMIN puede preguntarle «al Supervisor» por los dos caminos y obtener respuestas distintas.
- Media **V** — nombraba `PRIVATE_ASISTENTE_URL/TENANT` al usuario con un 500 (**arreglado**: mensaje para personas y 503). Tildes faltantes (**arreglado**). Sin pruebas.

### Campo

**Instalaciones (`/instalaciones`)** — bandeja de `SolicitudServicio` (`gestion.py:229`, máx. 200 ENVIADA); única acción: Decidir. El hilo: chat → `registrar_solicitud_servicio` → Lead + solicitud → formulario público → ticket de WispHub + correo (`entrega.py:264-297`) → bandeja → aprobar reasigna el ticket → el importador lo trae como Case → clasificación → orden → cuadrilla.
- **Alta V** — cualquier rol de la organización lee la bandeja y **el PDF con foto de cédula, recibo y firma** (`gestion.py:80,145,237,342`: solo `IsAuthenticated + HasOrgContext`). Inventario sí restringe escrituras con `ROLES_INVENTARIO`. *Pendiente de una decisión: qué rol usan hoy quienes deciden factibilidad en Rapilink (no está medido); con eso, `ROLES_GESTION | {"VENTAS"}` en bandeja, decisión y expediente.*
- **Alta V** — rechazar (`SIN_FACTIBILIDAD`) no cierra el ticket de WispHub ni le avisa al cliente la `nota_revision` (`gestion.py:263-284`); `cerrar_ticket_wisphub` ya existe (`entrega.py:301`).
- Media **V** — «se puede reintentar» (`gestion.py:242`) es falso: `DecidirView` devuelve 409 a toda solicitud que no esté ENVIADA; una aprobada con `fallo_integracion` queda huérfana.
- Media — la factibilidad es una aprobación humana no crítica; la cobertura barrio → zona → cuadrilla ya se calcula (`campo/despacho_pantalla_views.py:610`). Que alcance para decidir sola es **I**.
- Baja **V** — Hoy decía «antes de crear el ticket» cuando el ticket ya existe (**arreglado**); `fecha()` sin `timeZone` (**arreglado**); «Ver en el mapa» manda el GPS exacto de la vivienda a Google en la URL (`+page.svelte:66`).
- La solicitud no sabe qué orden la instaló (sin FK); la costura posible es el ticket de WispHub en `OrdenTrabajo.origen_ref`.

**Inventario (`/inventario`)** — doce pestañas sobre un libro append-only (`MovimientoDeMaterial`, `campo/models.py:1052`) con FK a la orden; ninguna lectura inventa ceros.
- Media **V** — la historia de un aparato recibe `orden` del backend (`services/inventario.py:687`) y `BuscarAparato.svelte` no la pinta; `Reportes.svelte:310` muestra `#numero` como texto. **No existe una página web de orden** a la que enlazar.
- Media **V** — `comprometido` llega siempre vacío: el CRM nunca reserva contra una orden (lo documenta la app, `materiales_de_esta_orden.dart:27-31`).
- Baja **V** — fuentes de Google por CDN; tres indicadores con «—» permanente (`inventario/+page.svelte:16-22`).

### Clientes

**Tickets (`/tickets`)** — cola por área contra `/cases/` (fail-closed sin área), detalle con conversación y ficha WispHub/SmartOLT por el motor; responder va al motor (WhatsApp + WispHub).
- **Alta V** — `ApprovalRule pre_close` bloquea cerrar un caso (`cases/models.py:420-445`); cerrar un ticket es no crítico (PRD §2) y le pega al agente: `nucleo/relevo/efectos_externos.py:165-169` deja la acción en «permanente, esperando a alguien». Si hay reglas activas en producción: **I**.
- Media **V** — la regla `MANAGER` no matchea ningún perfil (`cases/approvals.py:28-32`): una opción elegible que nunca funciona.
- Media **V** — cédula, teléfonos y dirección del titular a cualquier rol (`tickets/[id]/+page.svelte:1121-1142`); el importador decidió «su cédula no» para el Supervisor (`importacion_io.py:246-249`).
- Ticket ↔ orden de campo **cortado**: `Case.external_ticket_id` y `SolicitudServicio.ticket_wisphub` comparten el id de WispHub sin FK ni enlace. Ticket → conversación no existía (**arreglado**: «Abrir en Conversaciones»). `tickets/[id]/+page.svelte:426,1305` enlaza a `/accounts/{id}`, que para casos importados no existe.
- Baja — «An approval is required before this case can be closed» llega en inglés (`cases/models.py:442-445`).

**Tareas (`/tasks`)** — `Task` genérico; **nada del motor crea tareas**. Lista manual paralela al seguimiento real (Instalaciones, Supervisor NOC, el reloj). Herencia.

**Cuentas y Contactos** — fichas genéricas (rubro, empleados, ingresos). No se relacionan con el cliente de WispHub ni con WhatsApp; el motor no las crea. Duplicación vacía. (**Arreglado** lo mínimo: los títulos respetan la terminología del tenant, como el menú.)

**Base de conocimiento (`/solutions`)** — `Solution` con flujo borrador → revisado → aprobado. **No la lee el RAG** (cero referencias en `nucleo/`); el sugeridor (`SolutionSuggester.svelte`) no está montado en ninguna ruta; los textos «los clientes lo ven» (`solutions/+page.svelte:37,131`) prometen una visibilidad que no existe. Segunda base de conocimiento que nadie lee.

**Documentos (`/documents`)** — **este sí es el engranaje con el RAG** (`usar_en_asistente` → Celery `ingerir_documento_en_asistente`, `common/tasks.py:443`).
- **Alta V** — `documents.js::toDoc` no copiaba `usar_en_asistente`, `estado_ingesta`, `ingesta_fragmentos`, `ingesta_detalle` ni `roles_asistente`, aunque el serializer los manda (`common/serializer.py:845-850`) y la lista los lee: el indicador «N fragmentos / No se pudo indexar» no se dibujó nunca. El patrón de `requiere_noc` (CLAUDE.md §6). **Arreglado el 12/11, con `documents.test.js` atravesando `listDocuments`.**

### Ventas y Facturación

El hilo prospecto → cliente: el agente `ventas` crea Lead + solicitud en una transacción (`solicitudes/views.py:93-110`); el Lead nace `assigned`/`source=other` y **nada vuelve a tocarlo**: queda «assigned» para siempre aunque el cliente ya esté instalado. `leads/[id]` no enlaza a la solicitud, el chat ni la instalación; «Convertir prospecto» crea Account + Contact + Opportunity del CRM, cuando la conversión real es *cliente en WispHub*. **El embudo que el dueño necesita (chats de venta → links → enviadas → aprobadas → instaladas → activas) no existe en ninguna pantalla, y todos los datos ya están.** **V**
- **Prospectos**: estado y origen se mostraban crudos en inglés («assigned», «other») con los rótulos ya existentes en `enums.js` (**arreglado**); dos botones «Importar» sin acción (**retirados**); «Origen: Otro» para WhatsApp (el YAML mapea `whatsapp: other`, línea 5882); `requiere_confirmacion` del consentimiento Ley 1581 «HOY NO FRENA NADA» (YAML 5771-5781).
- **Negociaciones**: técnicamente la mejor de las cinco; conceptualmente duplica `SolicitudServicio`.
- **Objetivos**: cuenta negociaciones ganadas del CRM → 0 en un ISP. Menú «Objetivos» vs página «Metas» (**arreglado**).
- **Facturas**: cero integración con WispHub (`grep -i wisphub backend/invoices` → nada); ocho subpantallas (~3.700 líneas) sin uso; el estado vacío manda a «Ir al pipeline». La factura real la consulta el asistente en WispHub.
- **Registro de horas**: help-desk por horas; sin uso en tarifa plana.

### Dexter

**Agentes (`/agentes`)** — editor de roles vía `editor._editar` (bloquea la fila, valida, sube `config_version` solo si cambió); autonomía con `promover`/`retirar` que el motor vuelve a exigir. D7 sigue abierto (`editor.py:498-500` lo dice); `Herramienta.roles_permitidos` muerto en runtime y aun así obligatorio (`schema.py:994`). Enlaza solo a Habilidades.

**Habilidades (`/habilidades`)** — `propuesta → vigente → obsoleta`; el motor inyecta el índice en cada turno (`motor.py:3516-3524`).
- Media **V** — la evidencia no se puede abrir: el motor manda hasta 20 ids de conversación (`api.py:10622-10645`) y la pantalla solo dibuja «Motivada por N casos». Quien aprueba «lo que el agente seguirá al pie de la letra» decide sin poder leerlos.
- Media **V** — el analista cuenta conversaciones del simulador como evidencia (`analista.py:160-175` sin filtro de canal; la autonomía ganada sí usa `canales.REALES`).
- Media — las muestras van al modelo sin `redaccion.py` (`analista.py:218-228`): un nombre o teléfono puede quedar persistido en los pasos de una habilidad vigente.

**Manual (`/manual`)**
- **Alta V** — los ejemplos marcados (`ejemplos_validados`) **no los lee ningún agente ni la evaluación** (único lector: `api.py:10116`; `motor.py` y `cli/evaluar.py`: cero). El menú promete «de qué ejemplos aprende» y es un archivador.
- Media **V** — aprobar una revisión del supervisor no tiene efecto (nadie lee `estado='aprobado'`); aprobar/descartar lo podía cualquier usuario (**arreglado**: ADMIN en el servidor y los botones); mezcla simulado y real (`db.py:5122-5131`); texto literal de clientes a todo rol (**I**).

**Simulador WhatsApp (`/simulador-whatsapp`)** — pasa por `atender_turno` (`api.py:3194`), a diferencia de `cli/evaluar.py`. No muestra la traza (`+page.svelte:128-152`) aunque se persiste (`api.py:2116`); no reproduce una conversación real ni exporta un caso dorado. El hilo Manual → Simulador → `evaluacion/*.casos.yaml` está cortado en los dos extremos.

### Administrar

**Equipo y accesos** — roles `ADMIN | USER | BODEGA`; al desactivar traspasa los casos abiertos. Rótulo del hub «Equipo y acceso» (**arreglado**).

**Configuración (`/settings`)** — 29 subpáginas: 12 escriben `tenant_config` por `editor.py`, 17 escriben Django; 7 son herencia que el motor no lee (`routing`, `escalation`, `ticket-approvals`, `reopen`, `inbound-email`, `macros`, `custom-fields`). Tres pares con la misma palabra y distinto efecto: Organización (datos de factura vs pisos), Escalamiento (SLA de tickets vs IA → persona), Macros vs respuestas rápidas.
- **Alta V** — ajustes del motor que solo se cambian por YAML (viola §3.3): `escalamiento.mensaje`, `mensajes_por_motivo`, `mensaje_ya_escalada`, `mensaje_si_falla`, `frases_de_traspaso` (`schema.py:2910-2952`), `cierre_inactivas_ia`, `limites.horas_inactividad_cierra`, `vision_*`, `promesas_pago`, `desenlaces`. El editor solo **lee** `cierre_inactivas_ia` para validar la Bandeja (`editor.py:1319-1326`): un formulario puede rechazar un valor por un tope que ninguna pantalla permite tocar.
- Media **V** — `/settings/instalaciones` no está enlazada desde ningún archivo. Errores de Django llegan en inglés por `form-errors.js:20-58` (**I**).

**Conectar sistema / Conectar API nueva**
- **Alta V** — tras aplicar un conector la pantalla mandaba a «Ajustes → Variables», **que no existe** (**arreglado el texto**); el motor expone `GET/PUT/DELETE /configuracion/variables` (`api.py:5039-5095`) pero no hay pantalla genérica: una `base_url_ref` nueva no tiene dónde cargarse sin código. Es lo que falta para el segundo ISP junto con el paquete base de agentes (D5).
- Media **V** — `catalogo.py:150` lista como faltantes todos los secretos sin mirar cuáles ya están.

**Consumo** — el tope sí frena (`api.py:1805, 5827, 12012`); `consumo.tope_superado` (`consumo.py:341`) no tiene llamador.
**Capacidad** — `personas_del_equipo` se declara a mano cuando `/team` ya lo sabe (**I**).

### Transversal
- La paleta ⌘K busca `lead, deal, account, contact, ticket, invoice, solution` (`search.js:13-21`): **no llega a conversaciones, solicitudes, órdenes ni agentes**. **V**
- Las insignias del menú miden volumen del CRM (`tickets` = todos los abiertos), no trabajo humano pendiente: conversaciones que piden persona, órdenes detenidas e instalaciones por decidir no tienen insignia aunque Hoy ya las calcula. **V**
- Roles en dos capas: 13 rutas con puerta ADMIN en el servidor; `/team` depende de que `listTeam` falle; `/manual` gateaba solo en el cliente. **V**
- Terminología a medias: el menú relabela con `termKey` y cuatro títulos escribían el literal (**arreglado**).
- `lib/components/*` conserva textos en inglés en 16 componentes que **ninguna ruta importa**: código muerto (180 archivos candidatos; verificar antes de borrar).

---

## 3. Lo que se hizo el 12/11/2026 (commit en la rama `diseno/conversaciones-v2`)

Veinte arreglos chicos, cada uno con una sola coincidencia en el código y sin cambio de contrato; las pruebas de los archivos tocados en verde (63 + 1 nueva de 3 casos):

| Dónde | Qué |
|---|---|
| `lib/server/v2/documents.js` + `documents.test.js` | El estado de ingesta llega a la pantalla (defecto alto) |
| `lib/server/v2/hoy-operacion.js` | Hoy pide la cola con el mismo tope de 30 días que la Bandeja |
| `routes/(app)/+page.svelte` | El vacío no afirma lo que no pudo leer |
| `routes/(app)/tickets/[id]/+page.svelte` | «Abrir en Conversaciones» desde el ticket |
| `routes/api/manual/revisiones/[id]/{aprobar,descartar}` + `manual/+page.svelte` | Resolver una revisión es de ADMIN, en el servidor y en los botones |
| `routes/api/asistente/+server.js`, `asistente/+page.svelte` | Sin variables de entorno en pantalla; 503; tildes |
| `routes/api/conversaciones/[id]/{humano,atender}` | 400 por cuerpo malformado; log sin el error crudo |
| `leads/+page.svelte` | Estado y origen legibles; sin botones muertos |
| `accounts`, `contacts`, `pipeline`, `invoices` | Título con la terminología del tenant |
| `instalaciones/+page.svelte` | Hora en Bogotá también en el servidor |
| `conectores/+page.svelte`, `settings/+page.svelte`, `Sidebar.svelte`, `centro-mando/+page.svelte` | Textos que mandaban a pantallas inexistentes o no coincidían con el menú |

**No se hizo, y por qué:** el gate de rol en Solicitudes (hace falta saber qué rol decide hoy en Rapilink), borrar `tope_superado` (toca `nucleo/`: va con su guarda en un commit propio), el comentario del Supervisor (no confirmado), y todo lo de la sección 4.

---

## 4. Qué construir, ordenado por valor hacia el objetivo (PRD §1)

| # | Qué | Por qué mueve el objetivo | Tamaño |
|---|---|---|---|
| 1 | **El Supervisor NOC nace con sus tareas no críticas delegadas** y la bandeja queda para lo crítico; lo no crítico se muestra como «hecho · deshacer» en Actividad | Es la bandeja de aprobaciones más grande del producto, para trabajo que PRD §2 declaró no crítico | grande |
| 2 | **Rechazar con motivo desde la Bandeja** (proxy + botón) | Sin el «no», la autonomía ganada no tiene evidencia completa | chico |
| 3 | **Cerrar el bucle del Manual**: un ejemplo marcado o una revisión aprobada genera un caso dorado desde la traza; «Corregir» como camino único | El trabajo humano de marcar hoy se tira | mediano |
| 4 | **Pre-factibilidad automática** con la cobertura que ya se calcula; la bandeja de Instalaciones queda para «fuera de zona / GPS dudoso». Y **cerrar el bucle del rechazo** (ticket + WhatsApp) | Es la tarea humana más grande de Campo y no es crítica | mediano + chico |
| 5 | **Ficha del cliente por `id_servicio`** (`/clientes/[id_servicio]`): conversaciones, tickets, órdenes, solicitudes, ONU; enlazada desde todas partes | Resuelve la isla y la identidad de una vez | grande |
| 6 | **Ticket ↔ orden de campo** (FK + bloque «Campo» en el detalle), **página de orden** y `OT-n` como enlace | «¿Hay técnico asignado?» hoy no se responde desde el ticket | mediano |
| 7 | **Ficha por rol**: `CAMPOS_FICHA_CLIENTE` por área, PDF del expediente y detalle del ticket con el mismo criterio | Tres huecos de privacidad del mismo tipo | mediano |
| 8 | **Quitar `pre_close`** o declararla no crítica; ocultar Aprobaciones y `ticket-approvals` | Un ticket que el agente cerró y «espera a alguien» es mano de obra | chico |
| 9 | **Página «Variables de la empresa»** y **editor de textos de escalamiento / cierre por inactividad** | Cierra las dos violaciones de §3.3 y destraba el segundo ISP | chico + mediano |
| 10 | **Embudo real en Ventas** (chats → links → enviadas → aprobadas → instaladas → activas), Lead sincronizado con su solicitud, seguimiento automático a las 24 h del que abrió el link y no envió | El embudo del ISP no existe en ninguna pantalla y todos los datos están | mediano |
| 11 | **Simulador con traza y «reproducir esta conversación»**; evidencia navegable en Habilidades; `canales.REALES` y `redaccion.py` en el analista | Verificar una habilidad antes de aprobarla, sin leer a mano | mediano |
| 12 | **Podar el menú heredado** por bandera de tenant (Cuentas, Contactos, Base de conocimiento, Tareas, Objetivos, Facturas, Horas) y mover las 7 subpáginas de Configuración que el motor no lee a «Avanzado (CRM)» | Menos pantallas que confunden; «Facturación» pasa a ser Cobranza sobre WispHub | chico |
| 13 | **Insignias de trabajo humano** y **paleta ⌘K** con conversaciones, solicitudes y órdenes; deep-link `/conversaciones?pestana=` | El menú mide volumen del CRM, no lo que una persona tiene que hacer | mediano |
| 14 | **Un solo chat interno** (Asistente + Supervisor) con historial; decidir Pixi vs Three y borrar el perdedor; fuentes autoalojadas | Pulido que hoy confunde o depende de un tercero | mediano |
