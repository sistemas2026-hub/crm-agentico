# Objetivo · Programación viva, con el progreso de cada orden y la pestaña Cerradas

> Abierto el 30/10/2026. Estado: **construido, sin desplegar**.

## Qué significa terminado

Programación se actualiza sola cuando el técnico reporta desde la app: no hay que recargar la página ni tocar un botón, y no parpadea. Cada orden muestra su progreso, como en la app. Lo que ya se cerró sale de la pestaña Hoy y vive en **Cerradas**, con su historial.

## De dónde sale

El usuario, 30/10/2026, sobre el boceto que aprobó (https://claude.ai/artifact/MXrFBSfA6nsBftighYFnsh):

- «en la tarjeta debe salir este progreso para cada ticket»
- «es el historial del ticket anterior, no tiene que salir»
- «esto de supervisor cargó material tampoco debe ir ahí»
- «estos ticket que están a la espera colocalos que se puedan contraer»
- «estas tarjetas tienen que estar vivas: si manda un reporte desde la app, que no se tenga que recargar la página ni presionar un botón; solo y sin que se vea»

## Decisiones (30/10/2026; las recomendadas, por la regla del usuario «escoge la más recomendable»)

**1 · Viva, por sondeo**

Cada 15 s, solo con la pestaña a la vista, y al volver a ella. Es el mismo patrón que la Bandeja de conversaciones.

- Se pide **solo lo publicado del día**, por la ruta `programacion/vivo`. El material y su configuración no se recalculan en cada vuelta.
- Los datos se cambian en su lugar, así que una sección abierta sigue abierta.
- No hay WebSocket todavía, igual que en la Bandeja.

**2 · Lo que se está escribiendo no se pisa**

El porqué y las casillas de «Devolver» se toman una vez, al abrirlo, y no de la revisión en vivo.

**3 · El log de la cuadrilla, solo con lo abierto**

Lo de una orden terminada o cancelada vive en su tarjeta de Cerradas. El avance («2 de 5») sigue contando lo terminado.

**4 · El historial de una orden es de esa orden**

Entra quién la asignó, salió, llegó, sus reportes, terminó, la devolución, quién la aprobó y el ticket del ISP. El material y las novedades son del día de la cuadrilla.

**5 · La foto de la revisión al aprobar**

Se guarda una foto de lo que decía el Supervisor al aprobar, tanto si aprueba una persona como si aprueba el Supervisor. Una orden cerrada ya no se revisa, y recalcularla diría otra cosa.

**6 · «Esperan cuadrilla», plegado y agrupado**

Agrupado por el motivo que da el servidor, del grupo más numeroso al menos.

**7 · «Por revisar»: lo terminado sin cerrar de cualquier día (31/10/2026)**

El error que lo originó: la OT #4 se terminó en la app el 30/10 («Trabajo entregado. Queda esperar la revisión del supervisor») y el 31 no salía en ningún lado. Hoy muestra lo terminado **solo el día en que se terminó**, y Cerradas, solo lo cerrado. El usuario: «en la supervisor no sale el ticket».

- Una sección arriba de Hoy con toda orden en `completada_campo` que no esté ya en una cuadrilla del día, de la más vieja a la más nueva.
- Cada una con su tarjeta, la revisión del Supervisor y sus botones (Aprobar y cerrar, Devolver, o Cerrar si ya estaba aprobada). Sale de ahí cuando se cierra o se devuelve.
- Las cuentas del día no la cuentan: se cuenta aparte (`cuentas.por_revisar`).

**8 · Los recordatorios, en la tarjeta de la orden (31/10/2026)**

El error que lo originó: el usuario probó la vibración con la OT #4 y no vibró. Al terminar la orden, el recordatorio desaparecía de todos lados: el log de la cuadrilla solo muestra lo abierto (decisión 3) y el historial de Cerradas no lo trae. No había cómo saber si el Supervisor lo mandó.

- Cada orden trae los suyos (`recordatorios: [{cuando, llego}]`), terminada o no: «El Supervisor le recordó reportar · 16:05», o «(no llegó al teléfono)» si Google no lo aceptó.
- Si no hay ninguno, la regla de los 30 minutos no se cumplió: el problema no está en el teléfono.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 30/10/2026 | **Construido.** Servidor: `campo/ordenes_cerradas.py` y `GET /api/campo/cerradas/?desde&hasta` (solo gestión, hasta 31 días); `revision_del_cierre.guardar_foto` en `ValidarTrabajoView` y en `cierre_por_el_supervisor`; el log de la cuadrilla deja afuera lo terminado. Web: `ProgresoDeLaOrden`, `EsperanCuadrilla`, `OrdenCerrada`, las pestañas Hoy y Cerradas (Hoy, Ayer, Últimos 7 días) y la ruta `programacion/vivo`. **Medido:** 7 pruebas de Cerradas contra Postgres (dos pruebas viejas se actualizaron porque afirmaban lo que el usuario pidió sacar), 162 de la web, mutaciones 15/15 (dos sobrevivieron hasta afinar sus pruebas), `svelte-check` 143 = base, `vite build` OK. **No medido por prueba:** el sondeo en sí (es un efecto del navegador): se ve en vivo después del deploy | Regresión; deploy; un reporte desde la app que aparezca solo | este commit |
| 31/10/2026 | **Por revisar y recordatorios en la tarjeta** (decisiones 7 y 8). Servidor: `dia_publicado.del_dia` da `por_revisar` y `recordatorios` por orden. Web: `PorRevisar.svelte`, la línea del recordatorio en `OrdenDelDia`. **Medido:** `test_r` y `test_r2` contra Postgres (24/24 en el archivo); mutaciones 11/11 en el servidor y 3/3 en el componente; 266 de la web (la prueba del recordatorio encontró que Svelte se comía el espacio antes de «(no llegó al teléfono)»); `svelte-check` 143 = base; `vite build` OK. **No medido:** si el recordatorio de la OT #4 salió: se ve en su tarjeta después del deploy | Deploy; la tarjeta de la OT #4 en «Por revisar» | este commit |
