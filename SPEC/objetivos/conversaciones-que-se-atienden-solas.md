# Objetivo · Las conversaciones se atienden sin salir de la Bandeja

> Abierto el 29/10/2026. Estado: **abierto**. Rama `bandeja/ux-conversacion`
> (worktree `C:/tmp/dexter-bandeja-ux`).

## Qué significa terminado

Quien atiende una conversación escalada puede escalarla a otra área, dejarla
en espera, ver cuánto le queda de ventana, saber si el cliente es reincidente,
pedir un borrador a la IA y avisarle a un compañero, sin salir de la pantalla;
y quien supervisa ve la carga de cada operador y reparte varias a la vez.

## Por qué

Pregunta del usuario el 29/10/2026: *"si a un usuario le escalaron la
conversación, hizo sus validaciones y no solucionó el problema sino que tiene
que escalarlo?"*. Medido en el código ese día: no hay forma. Un operador solo
puede **Soltar** (T3), que la devuelve a la cola general sin motivo ni
destino; pasarla a alguien es **Reasignar** (T4), solo `ADMIN`. Quien la toma
después empieza de cero si no quedó una nota.

## Las siete funciones y lo medido de cada una (29/10/2026)

| # | Función | Lo que había | Fase |
|---|---|---|---|
| 2 | Cuenta regresiva de la ventana de 24 h | El compositor dice "abierta/cerrada", no cuánto queda. `ultimo_mensaje_cliente` ya viaja | A |
| 5 | Aviso de reincidencia | Las conversaciones del número ya se guardan; nadie las cuenta | A |
| 7 | Carga por operador y reasignar varias | T4 de a una | A |
| 3 | En espera | **El contrato ya lo define** (`pendiente_interno_desde`/`_nota`, banda 4, eventos `pendiente_interno_abierto/cerrado`, opción de T5) y la migración 202609161800 creó las columnas — **pero nada las escribe** | A (sin recordatorio) · B (recordatorio) |
| 1 | Escalar a un área | T4 dice *"habilitarlo entre pares por tenant queda para cuando una empresa lo pida"*: la pide ahora | B |
| 4 | Borrador de respuesta de la IA | El motor ya tiene lo consultado | C |
| 6 | Mencionar a un compañero en una nota | `common.Notification` del CRM existe | C |

## Decisiones (29/10/2026, del usuario)

- **Por fases**, un deploy probado por fase: A (2, 5, 7, 3 sin recordatorio),
  B (1 y el recordatorio de 3), C (4 y 6).
- **Escalar a un área lo puede hacer cualquier operador**, eligiendo el ÁREA
  (no una persona), con motivo y nota obligatorios. Pasarla a una persona
  concreta sigue siendo T4, de `ADMIN`. Es un cambio del contrato del relevo:
  se registra allí como transición nueva en la Fase B, antes del código.
- **El borrador de la IA es a pedido** (botón), nunca automático, y nunca
  envía: crece en alcance, no en autonomía.
- **Las columnas nuevas** (área de destino, hora del recordatorio) van por
  migración del ledger, que aplica el usuario con el dueño de la base. El
  `MIGRATOR_DBUSER` del `.env` no tiene permiso sobre `asistente` (medido en
  una sesión anterior, ver la memoria del 28/10/2026).

## Fase A — lo construido (29-30/10/2026)

- **2 · Ventana de 24 h.** Corrección a lo que se dijo al analizar: la vista
  de una conversación YA avisaba en la última hora (`ventana_whatsapp`,
  08/09/2026). Lo que faltaba era la cola y el número siempre visible. Ahora
  GET /conversaciones manda `ventana_whatsapp` por fila, calculada con el
  mismo `whatsapp.estado_de_ventana` y desde el último mensaje del NÚMERO; la
  fila marca «Ventana 45 min» con menos de 2 h y control humano
  (`lib/conversaciones/ventana.js`); el compositor dice «quedan 3 h».
  Guardas: `tests/test_cola_ventana.py`, `ventana.test.js`, `banda_estado.test.js`.
- **3 · En espera (sin recordatorio).** `transiciones.marcar_pendiente_interno`
  escribe lo que el contrato definía y nada escribía. Con nota abre/renueva,
  sin nota cierra (T5). La nota vive solo en la columna: el evento no la
  lleva, porque es texto libre que puede traer datos del cliente. La banda 4
  pasa a decir «En espera». Guardas: `tests/test_relevo_pendiente_interno_base.py`
  (Postgres real), `tests/test_pendiente_interno_cableado.py`, `humano/espera.test.js`.
- **5 · Reincidencia.** `db.reincidencia_de` cuenta por número y canal dentro
  de `conversaciones.reincidencia_dias` (30 por defecto, 0 apaga, editable en
  /settings/bandeja). Es un hecho, no un veredicto. Guarda:
  `tests/test_reincidencia_base.py` (Postgres real).
- **7 · Carga del equipo.** Panel «Equipo» para ADMIN: abiertas por persona
  y la espera más vieja (`lib/conversaciones/carga.js`), filtro de la cola,
  y «Pasar todas a…» que es T4 una por una con motivo. La lista del equipo se
  pide al abrir (`/api/bandeja/operadores`, solo ADMIN), no cada 8 s.

## Fase B — lo construido (30/10/2026)

Contrato del relevo **v3.3** escrito ANTES del código (C21, C22, T22, §3.1,
§3.3, §4.10).

- **1 · Escalar a un área (T22).** `transiciones.escalar_a_area`: la deja sin
  dueño (E1) marcada para un área de `TenantConfig.areas`, con motivo y nota
  obligatorios; la nota va además como nota interna del hilo, y no viaja en
  el evento. La de otra persona da 409 «eso es Reasignar». Cualquier
  operador; se conserva el área al tomarla, se borra al cerrar o al
  devolver a la IA. En pantalla: «Escalar a un área» en el bloque del relevo
  (FUERA del bloque de Tomar/Soltar: el caso típico es una conversación ya
  atendida), «→ Soporte Técnico» en la fila, y «Mi área» en la barra para
  quien pertenece a un área.
- **3 · El recordatorio de la espera (C22).** `pendiente_interno_hasta`:
  «Avisar en 1 h / 4 h / mañana 8:00» al marcar la espera. Vencida, la fila
  sube a la banda 1 con «La espera venció». Una hora pasada no se acepta.
- **Migración** `supabase/202610301500_escalar_a_area_y_vencimiento_de_espera.sql`:
  cuatro columnas nullable y el tipo `escalada_a_area` en el CHECK.

**ORDEN DE DEPLOY, al revés que la Fase A:** el código nuevo LEE columnas que
solo existen después de la migración. Primero `cli/migrar_asistente.py
--aplicar` con el dueño de la base (aplica también las dos que ya estaban
pendientes, 202610281600 y 202610290900, que son de otra sesión), y recién
después el push.

Guardas: `tests/test_relevo_pendiente_interno_base.py` (14, Postgres real con
la base construida por el ledger), `tests/test_escalar_area_api.py`,
`tests/test_cola_bandeja.py` (bandas nuevas), `escalar_area_render.test.js`,
`escalar-area/escalar.test.js`, `espera.test.js`, `humano/espera.test.js`.

## Fuera de alcance, y por qué

- Que la IA cierre o escale sola un caso ya tomado por una persona: es
  autonomía sobre algo que una persona atiende.
- Etiquetas libres sobre el cliente ("difícil", "VIP"): PII con poco valor
  operativo.
- Atajos de teclado y "Mías" (el punto 8 del análisis): no entraron en el
  pedido de las siete.

## Criterios de aceptación

Por fase, comando y salida:

- `py -3.13 tests/test_nucleo_sin_tenants.py` → `[OK]`.
- Las pruebas de la Bandeja en contenedor (`vitest run src/lib/conversaciones`)
  en verde, y `svelte-check` sin errores nuevos en archivos tocados.
- Cada función nueva con una prueba que atraviese la cadena (pantalla →
  intermediario → motor), no solo el servicio (CLAUDE.md §6).
- Fase B: la transición nueva escrita en `SPEC/CONTRATO_RELEVO_IA_HUMANO.md`
  ANTES del código, y la migración aplicada por el ledger
  (`cli/migrar_asistente.py --estado` sin pendientes).
