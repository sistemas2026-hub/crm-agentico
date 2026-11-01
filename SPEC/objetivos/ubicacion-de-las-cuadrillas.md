# Objetivo · Dónde está cada cuadrilla (el mapa GPS)

> Abierto el 31/10/2026. Estado: **servidor construido, sin desplegar. La recolección NO se enciende** hasta resolver la autorización del empleado.

## Qué significa terminado

El supervisor ve en un mapa dónde está cada cuadrilla, con la hora de la última señal, y nunca una posición vieja presentada como actual. Es la Etapa 2-3 de [centro-de-supervision-de-programacion.md](centro-de-supervision-de-programacion.md).

## De dónde sale

El usuario, 31/10/2026: *«queremos adicionarle un mapa donde uno pueda ver la posición actual de cada técnico, el cual va a tener el GPS activo en su celular, con el fin de hacerle seguimiento»*.

Antes había preguntado si la app podía leer la ubicación **con el GPS apagado y sin que se note**. La respuesta fue que no, y no se construye: con el switch del sistema apagado no hay API que lo evada, y rastrear a alguien sin que lo sepa es vigilancia encubierta. Lo que sí se construye es esto: **con permiso, visible, y solo durante la jornada**.

## Decisiones (31/10/2026)

**1 · Mapa: OpenStreetMap con Leaflet**

Google y Mapbox recibirían la ubicación de los técnicos. La autorización de tratamiento que firma el cliente **nombra a los proveedores** (CLAUDE.md §5): meterlos obliga a un trámite antes de encender nada. OSM no agrega un tercero. Para pines sobre Soledad rinde igual.

**2 · Solo durante la jornada, y la garantía va en código**

`registrar()` rechaza, fallando CERRADO, tres casos: quien no tiene jornada hoy, quien llega fuera del **horario de las cuadrillas** (con 60 min de margen), y la empresa que no cargó horario. Si esa regla viviera solo en el teléfono, una versión vieja de la app seguiría mandando a las 22:00 — y a esa hora la coordenada es **la casa del técnico**.

**3 · Solo la última posición. La tabla no guarda el recorrido**

Una fila por persona, que se pisa. Un rastro permanente de por dónde anduvo un empleado es otro dato y otra decisión; la operación necesita saber dónde está, no por dónde pasó. (Los respaldos de la base son otra cosa: eso se resuelve en la política de respaldo.)

**4 · Se borra a los 2 días**

`purgar()`, desde `ciclo_de_la_madrugada`, que ya recorre las empresas y corre **antes** del filtro de «le toca»: si colgara del ciclo que sí corre, la empresa cuyo ciclo no corre hoy no barrería nunca.

**5 · Un día es el del reloj de las cuadrillas, no el de la empresa**

`Org.timezone` trae `UTC` por omisión: a las 22:00 de Bogotá el servidor ya está en mañana. El día de la jornada y el día del horario salían distintos. `zona_operativa()` los unifica.

**6 · Una fecha pasada no muestra nada**

La lectura ata la posición a `jornada__fecha`. Sin eso, pedir el mapa del 25 devolvía la posición de **este minuto** rotulada bajo aquella fecha.

**7 · Al cablear la lectura, exigir rol de gestión**

`IsCampoAuthenticated` solo comprueba sesión y empresa: **no mira rol**. Si la vista de lectura lo copia, cualquier técnico ve la posición viva de sus compañeros. El patrón de `campo` es `_exigir_gestion(request)` dentro del método. **Decidido de antemano, antes de que exista la pantalla.**

## Lo que esto NO prueba

Que el técnico esté ahí: que **su teléfono** reportó esa coordenada. No hay control de plausibilidad. Un punto en una pantalla se lee como un hecho sobre una persona, y de ahí a una conversación disciplinaria hay un paso: eso tiene que viajar a quien dibuje el mapa.

## BLOQUEO para encender la recolección

**La autorización del empleado (Ley 1581).** Lo que el repo documenta (PRD RNF-01) es la autorización del **cliente del ISP**, para otra finalidad. El técnico es otro titular y esto es otro uso. Antes de que la app mande una sola posición hace falta: aviso y autorización del empleado, finalidad y plazo declarados, y quién puede leer el mapa (decisión 7).

El servidor se puede desplegar: **nada lo llama todavía**.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 31/10/2026 | **Servidor construido.** `campo/ubicacion_de_cuadrilla.py` (modelo, `registrar`, `dentro_del_horario`, `zona_operativa`, `purgar`, `de_las_cuadrillas`), `POST /api/campo/ubicacion/`, migración `0046`, barrido en `ciclo_de_la_madrugada`, y `anonimizar_campo` borra las posiciones. **Medido:** 29 pruebas contra Postgres; **mutaciones 10/10 muertas**. La regresión completa encontró que `test_l4` reventaba por una restricción única del helper de pruebas — y que la mutación de H3 había "muerto" por ese error y no por lo que decía medir: se arregló y se volvió a medir con el aserto a la vista | Regresión; la recolección NO se enciende | este commit |

### Lo que encontró el revisor de PII, y qué pasó con cada cosa

| # | Hallazgo | Estado |
|---|---|---|
| H1 | «Solo durante la jornada» era «cualquier hora de un día con jornada»: la casa del técnico a las 22:00 se guardaba y se servía como fresca | **Arreglado** (decisión 2) |
| H2 | `anonimizar_campo` decía por escrito que reemplazaba «coordenadas» y dejaba esta tabla intacta | **Arreglado** |
| H3 | Pedir una fecha pasada devolvía la posición de ahora | **Arreglado** (decisión 6) |
| H4 | No hay camino de lectura, y el permiso que hay no mira rol | **Decidido de antemano** (decisión 7) |
| H5 | La posición no se borraba nunca, ni la de quien se fue | **Arreglado** (decisión 4) |
| H6 | Una fecha imposible daba 500; con DEBUG, devolvía la coordenada en el cuerpo | **Arreglado** |
| H7 | «No se guarda el recorrido» vale para la tabla, no para los respaldos | **Matizado en el texto**; la política de respaldo queda fuera |
| H8 | La autorización que existe es la del cliente del ISP, no la del empleado | **Bloqueo abierto**, arriba |

**Lo que el revisor verificó que NO pasa:** la coordenada no llega a ningún log, traza ni telemetría (el `__str__` del modelo no la lleva, a propósito); no hay un segundo camino de escritura (ni admin, ni señales, ni router, ni serializer genérico); no llega al modelo de lenguaje; no hay tercero nuevo. Lo que falta es una **guarda**: nada impide que mañana alguien escriba un log con la coordenada.
