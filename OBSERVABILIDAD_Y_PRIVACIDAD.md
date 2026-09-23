# Observabilidad y privacidad

> La telemetría tiene que poder responder **"¿qué falló?"** sin poder responder
> **"¿quién era el cliente?"**. Sirve para operar Dexter; no es una copia de los
> datos del cliente en un servidor de terceros.

Dexter procesa conversaciones reales de clientes de un ISP. En la interfaz hay
nombres, teléfonos o identificadores de canal (BSUID), el hilo completo de
WhatsApp —donde el cliente escribe su cédula—, paneles de identidad y datos de
facturación. Nada de eso es un dato de operación, y ninguna herramienta de
monitoreo lo necesita para decir qué se rompió.

Este documento es el contrato. Lo hacen cumplir en código
`django-crm/frontend/src/lib/observabilidad/privacidad.js` (frontend) y
`nucleo/observabilidad/registro.py` (motor), y lo afirman las pruebas listadas
al final. Cambiar el contrato es cambiar esos archivos y esas pruebas, no sólo
este texto.

## Estado (23/09/2026)

- **Sentry está apagado en producción.** Cliente y servidor leen el DSN de
  `PUBLIC_SENTRY_DSN`; no está definido, `enabled` queda en `false` y no sale
  nada. `.env.example` no lo lista: activarlo es una decisión, no un descuido.
- La configuración quedó segura **antes** de cualquier activación: con DSN,
  todo lo que salga pasa por los ganchos de limpieza de abajo.
- Está pendiente decidir si un proveedor externo de monitoreo entra en la
  autorización de tratamiento de datos que firma el cliente (Ley 1581 de 2012,
  PRD RNF-01). Esa autorización hoy nombra al proveedor del modelo. **No
  activar Sentry hasta resolverlo.**

## Qué puede salir

| Sí sale | Ejemplo |
|---|---|
| Tipo de error y stack (archivo, función, línea, columna, `in_app`) | `TypeError` en `nodes/61.js:12` |
| Mensaje de error, **si es de operación** | `HTTP 502: Bad Gateway`, `Error cargando conversación` |
| Ruta y método de la petición, **sin query ni fragmento** | `GET /conversaciones/[id]` |
| Identificadores técnicos | `conversation_id` (UUID), `tenant`, `rol`, `herramienta`, códigos de bloqueo |
| Métricas, tiempos, estados, códigos HTTP | `status=404`, `duracion_ms` |
| Navegador y sistema | `Chrome 128`, `Windows` |
| Replay: la **forma** de la pantalla fuera de las áreas con datos, con todo el texto enmascarado | qué pantallas abrió el operador, dónde hizo clic, cuánto tardó |

## Qué nunca sale

- Nombres, apellidos, cédulas, documentos, teléfonos, correos, direcciones,
  coordenadas.
- Texto de mensajes, hilos, transcripciones, respuestas del ISP (WispHub,
  SmartOLT), historial de conversación.
- Identificadores de canal de Meta (`CO.…`, `wamid.…`), tokens (JWT), cookies,
  cabeceras, cuerpos de petición o respuesta, query strings.
- IP del operador, usuario de Sentry, geolocalización.
- Variables locales y líneas de código fuente de los frames.
- Nombre del operador que escribe (`autor_nombre`), igual que en el motor.

## Cómo se garantiza (frontend)

Un solo módulo, `src/lib/observabilidad/privacidad.js`, usado por
`src/hooks.client.js` y `src/instrumentation.server.js`:

1. **`sendDefaultPii: false`** en los dos `init`. Sin IP, sin cabeceras, sin
   cookies, sin usuario por defecto.
2. **Ganchos de limpieza en todo lo que sale**: `beforeSend` (errores),
   `beforeBreadcrumb` (migas: consola, fetch, navegación), `beforeSendTransaction`
   (trazas de rendimiento) y `beforeSendLog` (logs). Cada uno **falla cerrado**:
   si limpiar revienta, el evento no sale.
3. **Dos capas sobre cualquier texto.** Patrones (correos, BSUID, wamid, JWT,
   teléfonos colombianos, cadenas de 6+ dígitos) reemplazan por marcadores
   (`<telefono>`, `<numero>`…). Y una segunda capa que decide si el mensaje
   habla de una persona: por **vocabulario** ("cliente", "titular", "cédula",
   "nombre"…) o por **forma de nombre** (dos o más palabras seguidas con
   mayúscula inicial o en mayúsculas — "Juan Pérez", "MARIO SABANAGRANDE" —
   que no sean frases de estado HTTP ni siglas). En ese caso el mensaje se
   reemplaza **entero** por `mensaje omitido (posible dato personal) #hash`.
   Se pierde legibilidad en ese caso; se conserva la agrupación (el hash es
   estable) y el stack, que es lo que dice qué falló. Una regex no sabe que
   "Juan Pérez" es un nombre; la heurística de forma acepta el falso positivo
   (un mensaje de operación omitido de más) porque el falso negativo es un
   nombre en un servidor ajeno. Las dos capas se aplican también a cualquier
   texto libre dentro de los payloads (`extra`, atributos de logs, argumentos
   de consola), no sólo al mensaje principal.
   Las **rutas** se limpian como rutas, no como mensajes: sin query ni
   fragmento y con los segmentos numéricos reemplazados (`/api/clientes/5832/`
   → `/api/clientes/<id>/`), porque un id de cliente identifica tanto como una
   cédula — el motor tampoco lo deja salir por el log. Los UUID se quedan:
   identifican una conversación, no a una persona.
4. **Claves prohibidas por nombre** en los payloads libres (`extra`,
   `contexts`, `tags`, `data` de migas y spans, atributos de logs):
   `nombre_cliente`, `usuario_externo`, `telefono`, `cedula`, `texto`,
   `mensajes`, `respuesta`, `cookies`, `authorization`, `user`… Se eliminan.
   Los campos estructurales de Sentry se tratan uno por uno: `request` se
   reduce a método y ruta; `user`, `server_name`, `contexts.user` y
   `contexts.geo` se eliminan; los frames se quedan sin `vars` ni código.
5. **Session Replay**: `maskAllText`, `maskAllInputs`, `blockAllMedia`, sin
   cuerpos de red (`networkDetailAllowUrls: []`), y **bloqueo entero** —ni la
   forma se graba— de todo lo marcado con `data-privado`: el contenido de la
   app (`.v2-main`), la bandeja (`.mesa.bandeja`), instalaciones y la
   solicitud pública (`.hoja`), y el compositor. Si mañana una pantalla nueva
   muestra datos de personas, se marca con `data-privado`; si no se puede
   garantizar, se apaga el replay (`replaysSessionSampleRate: 0`).
6. **`console.*` en el código**: nunca un objeto del dominio ni un error
   entero. Un `Error` de `fetch`/axios carga la respuesta del backend (texto
   de clientes) y, en axios, las cabeceras con el JWT. Se registra
   `{ tipo, method, endpoint (sin query), ...describirError(error) }`. Una
   prueba recorre `src/` y falla si aparece `console.error(..., conversacion)`
   o parecido.
7. **Ruido que no es de Dexter** (`ignoreErrors`): "Extension context
   invalidated", "message channel closed before a response was received" —
   extensiones del navegador.

## Cómo se garantiza (motor)

El motor ya tenía su propia regla, anterior a este documento:
`nucleo/observabilidad/registro.py` redacta y usa HMAC (no hash plano) para
identificadores; `registrar()` sólo acepta un evento fijo y campos nombrados;
`tests/test_registro_sin_pii.py` inyecta canarios por cada camino de WhatsApp
y exige que ninguno salga por stdout, stderr ni logging. La traza de
herramientas (`asistente.tool_calls`) guarda metadatos, nunca la respuesta
cruda de WispHub. Las tablas de observabilidad nuevas siguen la misma regla
(ver `asistente.identidad_eventos`: etapa, motivo fijo, rol, herramienta —
sin cédula ni nombre).

## Antes de activar un proveedor externo

1. Resolver si entra en la autorización de tratamiento (Ley 1581 / RNF-01), y
   en qué región se alojan los datos.
2. Correr las pruebas de abajo en verde.
3. Definir `PUBLIC_SENTRY_DSN` **primero en un entorno que no sea producción**,
   provocar errores con datos de prueba (nombre, teléfono, cédula, mensaje) y
   revisar en el panel del proveedor que no aparezcan: eventos, migas,
   contexto, replays, logs. Las pruebas afirman sobre el código; esa revisión
   afirma sobre lo que el proveedor guardó.
4. Recién entonces, producción.

## Pruebas

```
cd django-crm/frontend && pnpm test          # incluye las tres de abajo
  src/lib/observabilidad/privacidad.test.js    canarios por cada gancho
  src/lib/observabilidad/init_sentry.test.js   opciones reales de los dos init + marcas data-privado
  src/lib/observabilidad/consola.test.js       barrido de console.* en src/
py -3.13 tests/test_registro_sin_pii.py        # motor
```

## Lo que este documento no cubre todavía

- Métricas y eventos del Command Center: cuando existan, entran en la misma
  tabla de "qué puede salir" (identificadores técnicos, estados, tiempos) y
  usan los mismos ganchos.
- Logs del servidor Node (`console.*` en `+page.server.js` y `lib/server`):
  ya usan `describeError()` para no volcar errores de axios; no pasan por
  Sentry salvo que se active el servidor con DSN, en cuyo caso aplican los
  ganchos de arriba.
