# M09-G · Lo que el tablero del Supervisor NOC IA no puede mostrar

El tablero está replicado del diseño «Supervisor NOC IA — Dexter-nueva» y
desplegado. Cinco cosas que el diseño pide quedaron **declaradas en pantalla
con su motivo** en vez de rellenadas. Este documento dice qué falta exactamente
y dónde está ya el dato, para que la sesión de backend no empiece buscando.

La regla que vale para las cinco: **un cero inventado se lee igual que un cero
medido.** La pantalla existe para mostrar esa diferencia; llenar un bloque con
un valor plausible la borra.

## Lo primero: cuatro de las cinco no son datos que falten

Al verificar contra los modelos, cuatro de los cinco GAPs resultaron ser datos
que **ya existen en otro modelo y nadie expone**. Eso cambia el trabajo: no hay
que agregar campos ni migrar, hay que agregar o propagar.

| # | Bloque | Dónde está el dato hoy | Qué falta |
|---|--------|------------------------|-----------|
| 1 | Tickets por origen | `campo.OrdenTrabajo.origen_sistema` (`wisphub`, `solicitudes`, `crm`, `manual`) | Un indicador que los agrupe |
| 2 | Mapa de operación | `campo.OrdenTrabajo.gps_lat` / `gps_lng` | Que la propuesta los alcance |
| 3 | Columna «Zona» | `operaciones.LineaProgramacion.zona` | Que la propuesta la alcance |
| 4 | Columna «Técnico» | `campo.AsignacionTrabajo` (persona ↔ orden) | Que la propuesta la alcance |
| 5 | Actividad reciente | — | No existe; ver abajo |

El puente que falta en 2, 3 y 4 es el mismo: `PropuestaSupervisor` apunta a su
origen con `origen_tipo` + `origen_id` y no resuelve nada más. Quien lo cierre,
lo cierra una vez para los tres.

---

## 1 · Tickets por origen

**Lo que el diseño pide:** una dona partiendo los tickets entre «WispHub» y
«Dexter + WispHub».

**Lo que hay:** `origen_sistema` ya distingue cuatro sistemas, con un default
de `manual`. El diseño pide dos categorías; el modelo tiene cuatro. Vale la
pena decidir eso antes de agrupar — «Dexter + WispHub» no es una de ellas y
habría que definir qué combinación significa.

**Lo que falta:** una clave en `indicadores_programacion()`, al lado de
`ordenes_por_estado`, del estilo `ordenes_por_origen`. Con el envoltorio
`conteo()` como todas las demás, para que el frontend pueda distinguir un cero
de un hueco.

## 2 · Mapa de operación

**Lo que el diseño pide:** los casos ubicados sobre una zona.

**Lo que hay:** `gps_lat` / `gps_lng` en la orden, poblados desde WispHub.

**Dos advertencias, y la segunda es la que importa:**

- Un mapa de verdad necesita una librería de mapas en el frontend. Hoy no hay
  ninguna en `package.json`, y agregarla es una decisión de peso, no un detalle.
- **Las coordenadas son PII.** `django-crm/frontend/src/lib/server/v2/programacion-noc.js::leerOrden`
  ya las quita en el servidor, junto con el teléfono, y lo hace a propósito.
  Ponerlas en el tablero deshace esa decisión. Antes de exponerlas hay que
  decidir si el mapa las justifica, no asumir que sí porque el diseño las pide.

## 3 y 4 · Las columnas «Zona» y «Técnico» de la tabla

**Lo que el diseño pide:** dos columnas más en la tabla de hallazgos.

**Lo que hay:** la zona en `LineaProgramacion.zona`; el técnico, en
`campo.AsignacionTrabajo`.

**La trampa que hay que evitar con «Técnico»:** `PropuestaDetalleSerializer` ya
trae `responsable_sugerido` y `responsable_sugerido_email`. Es tentador ponerlo
en esa columna y darla por cerrada. **No es lo mismo:** `responsable_sugerido`
es a quien la IA *propone*, no quien tiene la orden. Mostrarlo ahí afirmaría
que alguien ya la tiene. Si se llena esa columna, que sea con la asignación
real, o con dos columnas distintas y rotuladas distinto.

Nota menor: `responsable_sugerido` está solo en el detalle.
`PropuestaListaSerializer` no lo incluye, así que la tabla no lo tiene aunque
se quisiera.

## 5 · Actividad reciente del Supervisor

**Lo que el diseño pide:** un feed de los últimos eventos del Supervisor.

**Lo que hay:** auditoría **por propuesta**, visible dentro de «Ver detalle».

**Lo que falta:** esto sí es nuevo — un listado transversal de los últimos
renglones de auditoría de la organización, ordenados por fecha. Es el único de
los cinco que no se resuelve exponiendo algo que ya está.

---

## Números legibles de caso y ticket

El diseño muestra `CS-1842` y `WH-91288`. La tabla hoy muestra los primeros 12
caracteres del UUID de `origen_id`, que no le sirve a nadie para buscar en otro
sistema.

`OrdenTrabajo` tiene los dos campos que hacen falta: `numero` (consecutivo
interno por organización) y `origen_ref` (cuyo propio `help_text` dice «ID o
número del origen externo (ej. #91288)»). Falta que lleguen a la propuesta —
mismo puente `origen_tipo` + `origen_id` de los puntos 2, 3 y 4.

---

## Tres decisiones de producto, sin responder todavía

No son GAPs de datos: son preguntas que nadie contestó y que cambian qué se
construye.

1. **Los porcentajes de tendencia** («+3 vs. ayer»). No hay tabla de historial
   de KPI, y no por olvido: los indicadores se derivan en el momento de la
   consulta, a propósito. Mostrar una tendencia exige guardar cortes, que es
   una decisión de diseño distinta, no un cálculo más.

2. **La prioridad como texto o como número.** El backend devuelve `30`. El
   diseño muestra «Alta / Media / Baja». Traducir en el frontend inventa los
   cortes; traducir en el backend los fija para todos. Hay que elegir dónde
   vive esa regla antes de escribirla en cualquiera de los dos lados.

3. **Tres tipos de hallazgo del diseño no existen en el catálogo**: *Ejecutado
   sin validar*, *Reprogramación* y *Diferencia de datos*. El catálogo tiene 15
   señales (`PropuestaSupervisor.TIPOS_SENAL`) y ninguna es esas tres. O se
   agregan como señales con su detector, o el diseño se ajusta al catálogo.
   Ponerlas como etiquetas sin detector daría una pantalla que promete una
   detección que nadie hace.

---

## Dónde está escrito esto en el código

Los motivos que la pantalla muestra viven en un solo lugar, para que se borren
de ahí el día que el dato exista:

- `django-crm/frontend/src/lib/v2/supervisor-noc-tablero.js` → `BLOQUES_SIN_DATO`
- las columnas ausentes de la tabla → `COLUMNAS_SIN_DATO`, en el mismo archivo

Las derivaciones del tablero están ahí y no dentro del componente porque la
regla que más fácil se rompe —un `?? 0` de más que convierte un indicador caído
en «todo en orden»— no se puede ejercitar sin montar el `.svelte`. Sus 28
pruebas están en `supervisor-noc-tablero.test.js` y casi todas son sobre ese
borde.
