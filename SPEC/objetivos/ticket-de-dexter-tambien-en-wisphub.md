# Objetivo · Un ticket creado en Dexter nace también en WispHub

> Abierto el 25/10/2026. Estado: **abierto** — construido el 26/10/2026, sin desplegar.
> Falta: deploy, cargar la config y el ticket real de prueba (ver Bloqueos).

## Qué significa terminado

Un ticket creado desde **Nuevo ticket** en Dexter existe también en WispHub,
atado a su caso desde el primer momento, y lo que se responde allá vuelve al
caso por la importación sin crear un caso duplicado.

## Por qué

Hoy hay tres puertas de entrada y solo dos llegan a WispHub:

| Entrada | Dónde nace | ¿Llega a WispHub? | ¿Su hilo vuelve a Dexter? |
|---|---|---|---|
| Llamada / oficina | WispHub | sí | sí, por la importación |
| WhatsApp escalado | Dexter + WispHub (al escalar) | sí | no por la importación: el caso no está atado al ticket. Desde el 25/10 la Bandeja avisa la primera respuesta directo |
| **Nuevo ticket en Dexter** | **solo Dexter** | **no** | — |

WispHub es el registro operativo del ISP: lo leen los técnicos, el despacho y
la facturación. Un ticket que solo vive en Dexter es invisible para todo eso.
Con esta tercera puerta, las tres entradas terminan en el mismo lugar y la regla
única de primera respuesta (`cases/signals.py::sellar_primera_respuesta`) cubre
las tres sin caminos especiales.

## Lo medido antes de diseñar (25/10/2026)

- **La ruta para que el CRM escriba en WispHub ya existe**:
  `POST /interno/herramienta/<nombre>` del motor (`nucleo/canales/api.py`), con
  `invocable_por_servicio` como permiso e `Idempotency-Key` como origen. La usan
  `solicitudes/entrega.py` (ticket de instalación) y campo.
- **Esa ruta entra por la puerta AUTÓNOMA**: `motor.ejecutar_para_servicio`
  consulta el interruptor. Con la autonomía detenida, una persona no podría
  crear un ticket desde el formulario.
- **La herramienta que crea el ticket existe**: `crear_ticket_caso`
  (`POST /api/tickets/`, multipart), verificada el 12/08 y el 22/08/2026.
  WispHub **exige** el servicio del cliente, y el asunto de una **lista cerrada**
  (un asunto fuera del catálogo responde 400).
- **El riesgo de duplicado es real**: la importación clasifica como `dexter`
  solo los tickets que figuran en `asistente.conversations.ticket_operativo` o
  en `solicitudes_solicitudservicio.ticket_wisphub`. Un ticket creado desde el
  formulario entra por la cuenta de la API, no figura en ninguna de las dos y
  sería importado **como un caso nuevo**, salvo que el caso ya esté atado
  (`provider` + `external_ticket_id` → `YA_EXISTE`).

## Decisiones

1. **El formulario elige el servicio del cliente** (búsqueda por nombre o
   cédula a través del motor, con la política de campos de un rol: la ficha
   cruda de WispHub no llega a la pantalla). Sin servicio no se crea en
   WispHub, y la pantalla lo dice: el caso queda solo en Dexter, que es un
   estado válido.
2. **Orden: guardar primero, entregar después** (§12). Se crea el caso en Dexter,
   y después el ticket en WispHub con `Idempotency-Key` = id del caso: el
   origen es la SOLICITUD, no el intento, así que un reintento no crea dos.
3. **El caso se ata en el mismo paso** que crea el ticket
   (`provider`/`external_ticket_id`/`external_service_id`). Si atarlo falla, el
   reintento recupera el id por el registro de operaciones externas en vez de
   crear otro ticket.
4. **Puerta humana, con la persona como actor** — el mismo patrón que
   `operativo.responder`: una persona llenó el formulario. No reabre la
   decisión de la puerta humana (`SPEC/objetivos/puerta-humana-y-los-ocho-pasos.md`):
   aplica la regla vigente, "con actor identificado entra por la humana".
5. **Asunto y departamento salen de la config del tenant**, no del código: la
   lista cerrada de asuntos y el departamento de cada área
   (`importacion_tickets.destinos`, en sentido inverso).

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | Crear desde el formulario con servicio → un ticket en WispHub y el caso atado | prueba de la cadena `formulario → acción → motor → herramienta → CRM`, con la herramienta doblada, que afirma el `external_ticket_id` del caso |
| 2 | Mismo envío dos veces → un solo ticket | la prueba cuenta los POST a la herramienta: 1 |
| 3 | La importación siguiente lo ve como `YA_EXISTE`, no como candidato | prueba que corre `descubrir` sobre ese ticket |
| 4 | Sin servicio → caso solo en Dexter y la pantalla lo dice | prueba de la acción |
| 5 | Con el interruptor abajo, una persona igual puede crearlo | prueba de la puerta |
| 6 | Un ticket real creado en WispHub con el cliente de prueba, leído de vuelta con `GET` | evidencia pegada (necesita la autorización de Bloqueos) |
| 7 | `auditor-de-frontera` y `auditor-independiente` corrieron | hallazgos resueltos o anotados |

## Restricciones

- **NO push** sin decisión explícita — push a `fix/integracion-wisphub` es deploy.
- **NO escribir `tenant_config`** fuera del paso de carga autorizado.
- No se cambia cómo entra un ticket por WhatsApp ni por la importación.

## Qué NO hacer

- **No atar los casos de WhatsApp a su ticket por `external_ticket_id`** para
  que la importación les traiga el hilo. Medido el 25/10: traería también la
  nota de cierre automático "por plazo", que no es una respuesta, y la
  reconciliación de estados sobre casos que hoy no la tienen. La primera
  respuesta de esos casos ya la avisa la Bandeja.

## Bloqueos

- **Autorización para crear un ticket real en WispHub** con el cliente de prueba
  (el mismo `6555` del 28/09/2026), y para leerlo y cerrarlo después. Sin eso el
  criterio 6 no se puede cumplir, y la documentación de una API externa es una
  hipótesis (§4).

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 25/10/2026 | Diseño, mediciones y decisiones | Todo el código; la autorización de Bloqueos | — |
| 26/10/2026 | Construido: `nucleo/seguimiento/ticket_desde_dexter.py` + rutas del motor (`/tickets-desde-dexter/asuntos`, `/servicios/<id>/titular`, `/casos/<id>/ticket-operativo`); `POST /api/importacion/casos/<id>/vincular/` (solo admin, no pisa, 409 si el ticket ya tiene caso); herramienta `vincular_caso_externo` y `tickets_desde_dexter.asuntos` en la config (15 asuntos, todos ya usados por el escalamiento en producción); "Crear también en WispHub" en Nuevo ticket con "Verificar" titular. Decisión al construir: **la primera versión usa solo valores ya probados en producción** (la herramienta `crear_ticket_caso` del escalamiento, su departamento y sus asuntos) — lo que no está verificado contra WispHub no entra | Deploy; cargar la config; el ticket real de prueba | — |
