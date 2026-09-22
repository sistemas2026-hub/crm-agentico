# Lo que la aplicación de campo no sabe, y quién tiene que saberlo

Este documento convierte el catálogo `apps/tecnicos-mobile/docs/campo_datos_pendientes.md`
—52 datos que el diseño de Stitch muestra y ningún sistema entrega— en trabajo
de backend con nombre, dueño y orden.

No es una lista de deseos: cada dato ya está pintado en la aplicación detrás del
modo demostración, con su identificador `CAMPO-DATA-XXX`. Cuando el backend
empiece a entregarlo, se borra el valor de ejemplo y la pantalla no cambia.

## La regla que gobierna este documento

Un dato sale de la demostración y pasa a producción **cuando el backend lo
entrega de verdad**. Mientras tanto se ve solo con `--dart-define=DEXTER_DEMO=true`
y no decide nada. Por eso este trabajo se puede hacer de a poco y sin coordinar
despliegues: cada campo que el servidor empieza a mandar es una línea menos de
ejemplo, y ninguno rompe la versión que ya está en la calle.

## Lo primero: mucho de esto ya está en la base

El inventario del 22/09/2026 sobre `django-crm/backend/campo` encontró que una
parte del catálogo **no hay que construirla, hay que exponerla**. Son datos que
el servidor ya guarda y ningún serializer devuelve.

| Ya en la base | Dónde | Qué dato del catálogo cubre |
|---|---|---|
| `OrdenTrabajo.contexto` (JSON) | `models.py:265` | Plan contratado (023), serial de la ONU (011 parcial), estado del abonado |
| `OrdenTrabajo.origen_sistema/_tipo/_ref` | `models.py:194-210` | De qué ticket nació la orden (029) y su origen (047) |
| `OrdenTrabajo.vuelta` | `models.py:250` | Cuántas veces volvió de validación |
| `OrdenTrabajo.cerrada_en` | `models.py:275` | Completa el par de tiempos (017) |
| `WorkTypeVersion.esquema["pasos"]` | `models.py:91` | **El protocolo de atención (049)**: ya viene por tipo de trabajo |
| `AsignacionTrabajo` (rol, es_principal) | `models.py:317` | La cuadrilla del trabajo (007 parcial) |
| `EventoTrabajo.datos` | `models.py:358` | La bitácora entera, incluida la lista de qué hay que corregir |

### El hueco más caro de todos

Cuando un supervisor devuelve una orden, la lista de **qué hay que rehacer**
(`requisitos_a_corregir`) se guarda en un `EventoTrabajo` y **no viaja a la
aplicación** (`transiciones.py:170-176`, leída por `validador.py:206-211`). El
técnico ve su orden en `correccion_requerida` y no sabe qué le devolvieron: lo
tiene que averiguar por teléfono.

Eso no es un dato de diseño pendiente. Es un trabajo que se rehace a ciegas, y
por eso encabeza la primera tanda.

---

## Tanda 1 — Exponer lo que ya existe

Sin migraciones. Solo serializers, con sus pruebas. Es la tanda con mejor
relación entre lo que cuesta y lo que resuelve.

| # | Qué | Dónde | Cubre |
|---|---|---|---|
| 1.1 | `correccion` en el detalle: `{vuelta, requisitos_a_corregir[], observacion, devuelta_en}`, armado desde el último evento `correccion_requerida` de la vuelta actual | `serializers.py` + `validador.requisitos_a_corregir` | El hueco de arriba |
| 1.2 | `origen`: `{sistema, tipo, ref}` en lista y detalle | `serializers.py` | 029, 047 |
| 1.3 | `contexto` en el detalle, tal como se congeló al despachar | `serializers.py` | 023 (plan), 011 (serial), y lo que el motor haya dejado |
| 1.4 | `pasos` dentro de `tipo`, leídos de `esquema["pasos"]` | `serializers.py` | **049 deja de ser mock** |
| 1.5 | `vuelta` y `cerrada_en` en el detalle | `serializers.py` | 017 completo |
| 1.6 | `cuadrilla`: los asignados con su rol, no solo el principal | `serializers.py` + `AsignacionTrabajo` | 007 parcial |

Contrato: todo **aditivo**. Ningún campo cambia de nombre ni de tipo, así que la
versión de la aplicación que está en la calle sigue funcionando igual.

---

## Tanda 2 — Campos nuevos en la orden

Migración aditiva sobre `OrdenTrabajo`, todos opcionales (`null=True` o
`default=""`), para que ninguna orden existente quede inválida.

| # | Campo | Tipo | Cubre |
|---|---|---|---|
| 2.1 | `ventana_inicio`, `ventana_fin` | `DateTimeField(null=True)` | 020 — hoy solo hay `programada_para`, que es un instante y no la franja que se le prometió al cliente |
| 2.2 | `prioridad` | `CharField(choices=alta/media/baja, default="media")` | 004 |
| 2.3 | `zona` | `CharField(blank, default="")` | 003 |
| 2.4 | `resumen` | `CharField(255, blank, default="")` | 037 |
| 2.5 | `cliente_detalle_acceso` | `CharField(255, blank, default="")` | 041 — sin esto el técnico llega al edificio y no al apartamento |
| 2.6 | `cliente_id_abonado` | `CharField(64, blank, default="")` | 040, si no viene ya dentro de `contexto` |
| 2.7 | `requisitos_seguridad` | `JSONField(default=list)` | 045 — qué certificación exige el trabajo |
| 2.8 | `sla_vence_en` | `DateTimeField(null=True)` | 002 — el SLA se calcula contra esta fecha, no se inventa en el teléfono |

Quién los llena: el despacho (`services/despacho.py`), al crear la orden desde
el ticket o la solicitud.

---

## Tanda 3 — La jornada del técnico

Módulo nuevo: hoy no existe nada. Cubre 006 turno, 007 cuadrilla, 013 alertas
del día, 014 cumplimiento de SLA, 021 confirmación del kit y 038 modo de trabajo.

Lo importante del 038: el modo (en sitio, en ruta, disponible, pausa) **se marca
en la calle, sin señal**. Nace con cola de sincronización propia y clave de
idempotencia, como las transiciones de orden; si no, el primer cambio que se
pierda enseña a desconfiar de la pantalla.

Piezas: `JornadaTecnico` (org, profile, fecha, turno_inicio, turno_fin,
cuadrilla, estado, estado_cambiado_en) y `EventoJornada` append-only, igual que
`EventoTrabajo`. Los contadores del día (013, 014) se calculan, no se guardan.

---

## Tanda 4 — Inventario y custodia

Módulo nuevo. Cubre 009, 021, 025, 026, 044, 051, 052. Es el más grande y el que
más reglas de negocio tiene: un material serializado no se puede duplicar, y un
consumo tiene que poder viajar sin señal sin descuadrar la bodega.

Antes de escribir modelos hay que decidir una cosa que este documento no puede
decidir sola: **si el inventario vive en Dexter o si Dexter es un espejo del
sistema del ISP**. Con WispHub de por medio, la respuesta cambia el diseño
entero.

---

## Tanda 5 — Telemetría de red

Cubre 001, 011, 012, 024, 030, 031, 032, 033, 048. No es un módulo: es una
integración con SmartOLT, y hoy el backend **no habla con SmartOLT a propósito**
(`services/despacho.py:198-213`): la telemetría entra como snapshot dentro de
`contexto`, pedida al motor.

Dos caminos, y hay que elegir uno:
- **Ampliar el snapshot**: más campos en `contexto` al despachar. Barato, pero
  la lectura envejece: lo que el técnico ve es de cuando se creó la orden.
- **Consulta en vivo**: un endpoint que pregunta al motor cuando la app lo pide.
  Caro y con un modo de falla nuevo (sin señal no hay telemetría), pero es lo
  que el diseño promete con su etiqueta "Live".

Los tres parámetros de red (031 rango óptico, 032 longitud de onda, 033 umbral)
**no son telemetría**: son configuración de la empresa. Van en la config del
tenant, editable desde la interfaz, como manda la regla de multi-tenant del
proyecto. Ninguno debe quedar fijo en el código.

---

## Tanda 6 — Academia y vehículos

Cubre 018, 028, 043, 050 (academia) y 008, 042 (vehículos). Ninguno bloquea una
orden de trabajo; son los últimos.

El 050 (procedimiento recomendado para la falla) se apoya en lo que ya hay:
`cases.Solution` existe en el CRM y podría ser la base en vez de un módulo nuevo.

---

## Lo que no es del backend

Estos cinco no se resuelven con API y no hay que ponerlos en ningún endpoint:

| Dato | Dónde se resuelve |
|---|---|
| 022 modo de trabajo de datos | Texto de la aplicación |
| 027 medición por Bluetooth | El teléfono y el medidor; hoy el botón avisa que falta |
| 035 nombre del enlace | Texto de la aplicación |
| 036 última sincronización con éxito | `SyncQueueService` tiene que guardar la marca de tiempo del último envío bueno |
| 039 hora estimada de llegada | Cálculo con la posición del técnico; necesita 2.x y permiso de ubicación |

Y uno que no se va a construir: **019, la foto del técnico**. Se decidió mostrar
sus iniciales, que son reales, en vez de un avatar.

---

## Dos arreglos que el inventario dejó a la vista

No son datos del catálogo, pero salieron del mismo repaso y conviene no
perderlos:

1. **`validar_esquema_plantilla` existe y nadie la llama** (`validador.py:30-80`).
   Hoy se puede publicar una plantilla con tipos o reglas que la aplicación no
   entiende, y el error aparece en el teléfono del técnico.
2. **`TrabajosListView` no pagina**: `next_cursor` siempre es `null` y hay un
   corte duro en 100 (`views.py:113-114`). Con una cuadrilla grande, la orden
   101 no existe para la aplicación.

---

## Cómo se verifica cada tanda

Lo mismo que se le exige al resto del repositorio:

- Pruebas de contrato sobre la respuesta, no sobre la forma interna del modelo.
- Una prueba por dato nuevo que afirme **el efecto**: que el campo llega, que
  llega vacío cuando no hay dato, y que la orden vieja sigue siendo válida.
- Ninguna tanda se da por buena sin correr `pytest campo/` completo.
