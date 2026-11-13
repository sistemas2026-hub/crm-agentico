# Referencias canónicas de Stitch para la Bandeja

Proyecto Stitch: `projects/9659115480350175497`
Sistema de diseño: `assets/43cabc873c9142d2a1e118cef84be35d` — «Mission Control Operations Console», v1.

**Especificación visual CONGELADA el 18/09/2026** para la primera implementación.

Este manifiesto es la única lista que la implementación debe consultar. Existen en el proyecto
otras pantallas —variantes tempranas y duplicados— que **no** son referencia: están enumeradas
al final para que nadie las use por error.

Reglas del congelamiento:

- No se generan pantallas nuevas salvo por un defecto concreto y acordado.
- No se cambia el sistema de diseño ni sus tokens.
- No se reinterpretan estados: la verdad funcional la fija `CONTRATO_RELEVO_IA_HUMANO.md`, no Stitch.
- Stitch se consulta por MCP como referencia durante cada fase, nada más.

---

## 1. Cómo se usa esto en cada fase

```
abrir la pantalla canónica por MCP
        ↓
implementar solo esa zona
        ↓
comparar con Stitch
        ↓
mantener las reglas reales de Dexter por encima del diseño
        ↓
reportar las diferencias deliberadas
        ↓
aprobar
```

Cuando el diseño y el contrato se contradicen, **gana el contrato**. La diferencia se reporta,
no se resuelve en silencio.

---

## 2. Referencias canónicas

### IA atendiendo — `control = ia`
- **Stitch:** Dexter Operations - AI Handling State
- **ID:** `1714196c413f403f9aa69f3145d0c50a`
- **Pestaña:** Network
- **Propósito:** acción primaria **Intervene**, nunca «Take Conversation». Compositor bloqueado
  con la explicación a la vista y la nota interna habilitada. Badge `[AI HANDLING]` con punto violeta.
- **No copiar:** `AI Conf: 32%`, `#DIAG-8821`, telemetría OLT/PON, footer `v4.2.1-isp · WebSocket Live Sync`.

### Humano · asignada a mí — referencia maestra del hilo
- **Stitch:** Dexter Operations - Human Control State (Assigned to Me)
- **ID:** `c427b43a84534a489891f111217439a4`
- **Pestaña:** Network
- **Propósito:** define **los cinco autores** (cliente, Dexter AI, operador humano, nota interna,
  evento de sistema), cada uno con **etiqueta Y color**, y **los seis estados de entrega**:
  Sending / Sent / Delivered / Read / Failed con reintento / **Discarded sin reintento**.
  `Discarded` es terminal por D24: no se reintenta, no entra al historial.
- **No copiar:** RX/OLT, `#DIAG-8821`.

### Humano · dueño ajeno, visto por ADMIN
- **Stitch:** Dexter Operations - Assigned to Luis Vargas (Admin View)
- **ID:** `a845526e367544578d2991da3ee24df9`
- **Pestaña:** Network
- **Propósito:** solo **Reassign** y «⋯». Sin Release, sin Take, sin Intervene. Compositor bloqueado
  con la franja que nombra al dueño; la nota interna sigue habilitada.
- **No copiar:** RX/OLT, ids de diagnóstico.

### Reasignación ADMIN
- **Stitch:** Dexter Operations - Reassign Dialog (Admin View)
- **ID:** `3087381a409e4b7e87a4557836b66125`
- **Pestaña:** Network (detrás del scrim)
- **Propósito:** único elemento del sistema con sombra. Motivo **obligatorio** con la ayuda
  «Required — stored in the audit trail»; el botón de confirmar está deshabilitado mientras esté vacío.
- **No copiar:** la lista de operadores.

### Conflicto de asignación (409)
- **Stitch:** Dexter Operations - Assignment Conflict State
- **ID:** `44fe4fd29a764c8b9791e5e21b4750d3`
- **Pestaña:** Network
- **Propósito:** banner operativo neutro con filete azul, **sin rojo y sin modal**. Detrás del banner
  la pantalla ya muestra el estado verdadero: dueño ajeno, compositor bloqueado.
- **No copiar:** RX/OLT.

### Legado sin adoptar — `relevo_version = 0`
- **Stitch:** Dexter Operations - Legacy Conversation State
- **ID:** `64cfb00cd593478a87a0408e5465f04c`
- **Pestaña:** Case
- **Propósito:** badge ámbar `[LEGACY · REVIEW]`, fila apagada, **sin línea de dueño**, un solo
  control discreto «Review». **Nada puede sugerir que abrirla la adopte** (G8).
- **No copiar:** la referencia de ticket legado.

### Banda 1 — el cliente volvió a escribir
- **Stitch:** Dexter Operations - Customer Replied State (Assigned to Me)
- **ID:** `23bdda329b764e56b0f80aeb7edbc3c4`
- **Pestaña:** Network
- **Propósito:** el orden de la cola se explica **por bandas B3.5**, con el motivo en una línea.
  **Nunca un puntaje.**
- **No copiar:** RX/OLT.

### Contexto · Customer
- **Stitch:** Dexter Operations - Customer Context State (Assigned to Me)
- **ID:** `5ae3980c31944932821ed61be3749a72`
- **Pestaña:** Customer
- **Propósito:** identidad, ubicación, servicio y facturación. Pie «Read live from the ISP — not
  stored by Dexter».
- **No copiar:** dirección, localidad, saldo, facturas y pagos.

### Contexto · Network
- **Stitch:** Dexter Operations — Network Context (Canonical)
- **ID:** `7634891e2ea84b98848a89b9fd358a6c`
- **Pestaña:** Network
- **Propósito:** **reemplaza a la NOC Console** como referencia de Network. Dos secciones
  separadas y visualmente desparejas a propósito. `CONFIRMED — LIVE FROM SMARTOLT`: estado de ONT,
  potencia RX con su rango, serial GPON, MAC, causa de la última caída, perfiles de velocidad,
  dispositivos conectados, estabilidad de 24 h e incidente de zona; pie «Read live from SmartOLT —
  not stored by Dexter». `FUTURE DATA / NOT AVAILABLE TODAY`: degradada sobre fondo gris, valores
  apagados, cada fila con etiqueta `MOCK` y el aviso «Design placeholder. Do not implement as real
  data».
- **No copiar:** la sección 2 entera — modelo, firmware, temperatura, voltaje, corriente de bias,
  OLT, slot, puerto, PON, splitter, CTO.
- **Restricción de la Fase 8 (skill `smartolt-api`, verificada el 14/08/2026):** el diagnóstico real
  sale de `/api/onu/get_onu_full_status_info/{sn}`, que reemplaza a `get_onu_details` +
  `get_onu_signal`. Tiene ~10 s de latencia y el proveedor pide **no usarlo en polling ni en bulk**.
  Por eso Network es **bajo demanda, con caché y TTL**, nunca en vivo.

### Contexto · Case
- **Stitch:** Dexter Operations - Case Context State (Assigned to Me)
- **ID:** `81de07d2fa73428fa52d7189d7d5bef5`
- **Pestaña:** Case
- **Propósito:** tres bloques **separados** —`DEXTER CONVERSATION`, `CRM CASE`, `OPERATIONAL TICKET`—
  más `RETENTION` con motivo obligatorio. Lleva impresa la frase **«CRM ticket owner is not the
  conversation owner»**: el dueño del ticket del CRM puede diferir del dueño durable de Dexter, y
  **Dexter es la fuente de verdad** (D28).
- **No copiar:** ids de caso y de ticket.

### Contexto · Activity
- **Stitch:** Dexter Operations - Human Control State (Activity Timeline)
- **ID:** `cea0ff0a30d34a63b96a0c0dc351017d`
- **Pestaña:** Activity
- **Propósito:** línea de tiempo auditable, **nunca burbujas de chat**. Escalada y devolución en
  violeta; tomada, soltada y reasignada en azul; cierre en verde. Pie «Ordered by relay version»:
  el orden es `datos.version`, causal, **no** `creado_en` (D27).
- **No copiar:** horas y nombres de ejemplo.

### Contexto · Tools
- **Stitch:** Dexter Operations — Tools Context
- **ID:** `d58c8ed20b664173b3c0972070388931`
- **Pestaña:** Tools
- **Propósito:** dos bloques plegables y nada más. `AI PROCESS` (diagnóstico, contadores
  `steps 5 · blocked 1 · errors 0`, pasos con estado, el paso bloqueado con filete ámbar y
  «Jump to step») y `DOCUMENTATION` (búsqueda, fragmentos con código/versión/similitud,
  «Copy fragment»). Sin telemetría, sin acciones externas, sin herramientas inventadas.
- **No copiar:** pasos, duraciones y documentos de ejemplo.

### Ventana de WhatsApp cerrada
- **Stitch:** Dexter Operations - WhatsApp Window Closed
- **ID:** `79e78c7bced443c381284d78153a786f`
- **Pestaña:** Customer
- **Propósito:** franja neutra «WhatsApp messaging window closed / Use an approved template to
  continue» con acción primaria **Choose Template**. Adjuntar, imagen y micrófono deshabilitados;
  nota interna habilitada. Selector de plantillas abierto con variables, «Cancel» y «Send template».
  **En este estado no se muestran pistas de Enter para enviar**; el gesto normal de Enter no cambia
  en los demás estados y no se introduce `⌘+Enter` como regla nueva.
- **No copiar:** `#DIAG-8821`, teléfono, DNI, número de cuenta, la lista de plantillas.

### Devolver el control a la IA
- **Stitch:** Dexter Operations - Return to AI State Sheet
- **ID:** `c4cd76b95c5249fbb0c1333d9bff1935`
- **Pestaña:** — (hoja de estados)
- **Propósito:** cuatro estados. Idle; «Returning control…» con el compositor deshabilitado;
  confirmado con bloque violeta y línea de sistema; y error neutro «Could not confirm the handoff.
  Human control remains active.» con la cabecera **todavía en HUMAN CONTROL**. La regla: el relevo
  se muestra como devuelto **solo cuando el backend lo confirma**.
- **No copiar:** nada; no tiene datos.

### Vacío · sin resultados · error
- **Stitch:** Dexter Operations — Queue States Reference
- **ID:** `9b5e969b91ca4558b28c615b52a5e410`
- **Pestaña:** — (tres columnas de cola)
- **Propósito:** A «Nothing needs attention». B «No conversation matches «fibra corte»» con
  «3 filters are active» y el contador que prueba que la cola **no** está vacía, solo la búsqueda.
  C «Conversations could not be loaded / Retrying automatically…» con filete ámbar y «Retry now».
  El error es controlado: **sin código, sin proveedor, sin stack, sin detalle interno**.
- **No copiar:** el contador y los filtros de ejemplo.

### Tablet ≈1180 px
- **Stitch:** Dexter Operations — Tablet Workspace (1180px Drawer Open)
- **ID:** `98bd3945dea74790b49f7f22150f705c`
- **Dispositivo:** se pidió TABLET; Stitch lo registró como DESKTOP.
- **Propósito:** dos paneles, cola 320px y conversación. El contexto pasa a **drawer derecho ~360px**
  sobre un scrim que oscurece solo la conversación. **No se comprimen las tres columnas.** Bandas,
  línea de dueño, estado IA/Humano y compositor quedan intactos.
- **No copiar:** RX/OLT.

### Móvil
- **Stitch:** Dexter Operations - Mobile Master-Detail (Queue & Conversation)
- **ID:** `dd007179d24f411699e924b1cb084123`
- **Dispositivo:** se pidió MOBILE; Stitch lo registró como DESKTOP.
- **Propósito:** master–detail, una vista por vez, toques ≥44 px. El contexto es una hoja a pantalla
  completa, nunca una tercera columna.
- **No copiar:** `#DIAG-8821`, `-32.4 dBm`.

### Ajustes · Branding
- **Stitch:** Dexter Operations — Settings · Appearance & Branding
- **ID:** `099ebdec45474af4a363eaf602526c06`
- **Pestaña:** — (ajustes)
- **Propósito:** nav de ajustes 240px; `CURRENT LOGO` con vista previa en la barra superior;
  `REPLACE LOGO` con zona de carga y comparación lado a lado antes de guardar; «Restore default logo»;
  footer «Changes apply to every operator in your organization». **Sin selector de organización**,
  sin colores personalizados, sin favicon. Representa aislamiento multi-tenant: desde acá no se puede
  tocar el branding de otro tenant.
- **No copiar:** el nombre de organización, ni el nombre, peso y dimensiones del archivo.

---

## 3. NO COPIAR COMO DATOS REALES

Todo lo siguiente es **referencia visual, no contrato**. Aparece en las pantallas porque un diseño
vacío no se puede evaluar, pero **ninguno de estos valores se convierte en literal al implementar**:

- AI confidence (`AI Conf: 32%`) y cualquier puntaje del modelo.
- Ids de diagnóstico ficticios (`#DIAG-8821`).
- SLA, cuentas regresivas y T-Minus.
- Topología no confirmada: OLT, slot, puerto, PON, splitter, CTO.
- Telemetría no confirmada: modelo, firmware, temperatura, voltaje, corriente de bias.
- Ids de alarma inventados.
- Métricas de salud inventadas, footer de versión (`v4.2.1-isp`) y `WebSocket Live Sync`.
- BGP, SNMP, salud de clúster.
- Datos inventados de archivo y logo: nombre, peso, dimensiones, nombre de organización.
- Teléfonos, DNI y números de cuenta.
- Listas de operadores y de plantillas de ejemplo.

**Confirmado hoy contra SmartOLT** y por lo tanto implementable como dato real: estado de ONT,
potencia RX óptica, serial GPON, MAC, causa de la última caída, perfiles de velocidad, dispositivos
conectados, estabilidad, contexto de incidente y afectados.

---

## 4. Network canónico: cómo se recuperó, y la lección

La pantalla se generó el 18/09/2026 y su llamada devolvió el informe completo del agente
—confirmando que se construyó— pero **sin objeto de pantalla y sin id**. Seis llamadas seguidas a
`list_screens` no la mostraron. Se concluyó que era irrecuperable y se regeneró una vez, con el
mismo resultado.

Era falso. **La pantalla apareció sola en un listado posterior**, con id
`7634891e2ea84b98848a89b9fd358a6c`, una sola vez —de las dos generaciones quedó una sola pantalla,
sin duplicado— y junto a las otras cinco que también faltaban. Todos los ids capturados en las
respuestas de creación coincidieron exactamente con los del listado.

La explicación real no es que el listado «solo muestra lo colocado en el lienzo», como se supuso:
es que **la consistencia eventual tarda minutos, no segundos**. La lección para quien trabaje con
este MCP: cuando algo no aparece, la afirmación correcta es «todavía no aparece», no «no existe».
Declarar irrecuperable algo que solo necesitaba tiempo costó una regeneración innecesaria.

La NOC Console original (`13bdbe1ddb2544d7886dda989e7750a5`) sigue sin servir de reemplazo: su
barra NOC, sus porcentajes de API, su footer de clúster/BGP y su topología son mock, y usarla como
referencia es exactamente el riesgo que la pantalla canónica venía a evitar.

---

## 5. Branding — regla congelada

```
organization.branding.logo
  existe    → logo de la organización
  no existe → fallback de la marca Dexter
```

`Dexter Ops.svg` es el fallback, **no** un asset fijo. La regla es parte del sistema de diseño y no
obligó a regenerar las pantallas: el logo de la barra superior se lee como un slot.

Coherente con la regla multi-tenant del repo (ver `CLAUDE.md`): ningún dato de empresa se hardcodea
en código ni en YAML; se persiste en la config del tenant y se edita desde la interfaz.

`BANDEJA-DATA-028` queda registrado en el inventario. **El backend de branding no se implementa
todavía**; primero hay que auditar qué soporte existe.

Modelo conceptual (hoy solo `logo` y `display_name` son requisito):

```
branding
├── logo           REQUISITO
├── display_name   REQUISITO
├── favicon        FUTURO
├── primary_color  FUTURO
└── accent_color   FUTURO
```

---

## 6. Pantallas NO canónicas — no usar

| Nombre | ID | Motivo |
|---|---|---|
| Dexter Operations Logo | `b75e4829e286482fa673c73f1a37f270` | Asset SVG; ahora es un slot, no un dibujo fijo |
| NOC Console | `13bdbe1ddb2544d7886dda989e7750a5` | Base original llena de mock; reemplazada como referencia de Network |
| Tools State (Assigned to Me) | `045e6760a79e47b592d4cecea868d2ba` | Duplicado de Tools, de una tanda anterior |
| Human Control State | `0a193ac89d6f46f584d8f95562201b60` | Variante temprana |
| Human Control State (Message Reference) | `73af9a74beff4242b35e00aec3fc00bf` | Duplicado |
| Human Control State (Message Reference) | `c3cc7a0d939e4725851d93b54d9194cd` | Duplicado |
| Assigned to Another Operator (Admin View) | `2ee70bbd75284133ba683fedbbba0523` | Variante temprana |
| Assignment Conflict | `ac753f67052645c59bfde353e9cd832a` | Variante temprana |

No se borran: quedan como referencia histórica del proceso.

---

## 7. Limitaciones conocidas del MCP de Stitch

Quien trabaje con estas referencias se va a encontrar con esto:

1. **`list_screens` es eventualmente consistente, y tarda minutos.** Una pantalla recién creada
   puede no aparecer en seis llamadas seguidas y aparecer después. **El listado no sirve para
   concluir que algo no existe**; sirve para confirmar que existe. Este manifiesto es la fuente de
   verdad de los ids.
2. **Una generación puede completarse sin devolver la pantalla**, sin id y sin objeto, aunque el
   agente informe que la construyó. Pasó con Network canónico. La pantalla existía igual: hay que
   esperar y volver a listar, no regenerar.
3. **Un timeout no implica fracaso** — y tampoco lo contrario. Hay que revisar la respuesta antes
   de reintentar, y no generar de nuevo a ciegas: se acumulan duplicados.
4. **`get_screen` y `get_project` fallan** con «Request contains an invalid argument», incluso con
   ids que el propio listado acaba de devolver.
5. **`deviceType` lo decide el resultado, no la petición**: tablet y móvil volvieron como DESKTOP.

---

## 8. Orden de implementación

```
FASE 0  Componentizar sin cambiar comportamiento
FASE 1  Tokens Stitch acotados a la Bandeja
FASE 2  Cola — bandas B3.5, dueño Dexter, jerarquía visual
FASE 3  Hilo — cliente, Dexter AI, humano, nota, sistema
FASE 4  Header + relevo + compositor
FASE 5  Case + Tools
FASE 6  Activity / relevo_eventos
FASE 7  Customer
FASE 8  Network real — bajo demanda, con caché y TTL (§2, Network)
FASE 9  Branding configurable
```

Network queda deliberadamente tarde pese a ser la pantalla más vistosa: primero se implementa lo
que ya tiene datos disponibles y aporta valor inmediato.

**Precondición de la Fase 0, cumplida:** B3.5 / D18 cerrado en `eb5b4bf` el 18/09/2026 —regresión
completa, mutación negativa de D18 que mata la prueba en las dos capas, `svelte-check` sin un solo
hallazgo en `conversaciones/`—. El rediseño no se mezcla con el trabajo funcional.

**Regla de la Fase 0:** partir las 4036 líneas de `[id]/+page.svelte` y las 1193 de
`+layout.svelte` **sin cambiar ni un píxel ni una conducta**. Cirugía estructural primero, pintura
después.
