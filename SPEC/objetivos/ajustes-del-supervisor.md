# Objetivo · Ajustes del Supervisor

> Abierto el 27/10/2026. Estado: **abierto** (construido; falta deploy).
> Nace de «Anotado para otro momento» en `supervisor-arma-la-jornada.md`,
> punto 1 (interruptores por tarea). Los puntos 2 a 5 de esa nota siguen
> abiertos.

## Qué significa terminado

Una persona de gestión delega o quita cualquier tarea del catálogo del
Supervisor con un clic desde **Supervisor NOC → Ajustes**, y queda registrado
quién, cuándo y por qué. Lo que el Supervisor hace (el ciclo y el chat) cambia
con ese clic.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | Las pruebas del efecto pasan contra Postgres | `pytest operaciones/tests/test_ajustes_del_supervisor.py campo/tests/test_informe_de_cruces.py` en verde |
| 2 | Lo que ya existía sigue igual | `pytest operaciones/tests/test_tareas_delegadas.py operaciones/tests/test_la_pantalla_dice_que_esta_delegado.py` en verde |
| 3 | El frontend manda lo que debe | `npx vitest run src/lib/supervisor/ajustes.test.js "src/routes/(app)/supervisor-noc/ajustes/page-server.test.js"` → 16 passed |
| 4 | Las guardas matan su mutación | runner de mutaciones: todas MUEREN |

**Medido el 27/10/2026:** 67 pruebas del backend en verde contra Postgres; regresión de
`campo` + `operaciones` con las mismas rojas que la base (22, por nombre), después de
declarar la ruta en `test_m09f_gobernanza`; 21/21 mutaciones del backend y 12/12 del
frontend mueren; vitest sin rojas nuevas (una de antes curada); `svelte-check` 145/27
igual que la base; `vite build` pasa. `auditor-independiente`: 8 hallazgos, los que
rompían lo prometido corregidos (A10–A14, el día en el informe), el resto en
«Límites conocidos».

## Decisiones tomadas solas (regla del usuario del 24/10/2026)

Cada una se puede revertir; están anotadas para eso.

| # | Fecha | Decisión | Motivo |
|---|---|---|---|
| A1 | 27/10/2026 | **Motivo obligatorio en las dos direcciones**, una línea | El pedido dice «con persona y motivo registrados». Mismo criterio que el freno de mano: una línea, no un informe |
| A2 | 27/10/2026 | El motivo de delegar va en `pedido_textual`; el de quitar, en un campo nuevo `motivo_al_quitar` (migración `operaciones/0027`) | `pedido_textual` ya es «con qué palabras se pidió»; quitar no tenía dónde guardar el porqué |
| A3 | 27/10/2026 | La pantalla manda el **estado que quiere**, no «invertir»; si ya estaba así, 409 y no se escribe | Dos personas con la pantalla abierta se pisarían el quién y el motivo |
| A4 | 27/10/2026 | Escribe por `td.delegar`/`td.quitar` y reusa la lectura de `AutonomiaSupervisorView._delegaciones` | Una regla en dos lugares se separa el día que cambia una |
| A5 | 27/10/2026 | Se muestra el **nombre** de quien delegó o quitó, nunca el correo | El pedido pide «quién»; `td.delegadas` sigue devolviendo solo el id (lo lee el chat) |
| A6 | 27/10/2026 | Ver la pantalla también exige gestión, no solo cambiarla | Igual que el resto del Supervisor (`EsJefeDeOperaciones`) |
| A7 | 27/10/2026 | `td.quitar` escribe el motivo **siempre**, también vacío | Quitar por el chat no debe dejar a la vista el motivo de la vez anterior |
| A8 | 27/10/2026 | Pestaña «Ajustes» en Pendientes, Programación y Plantillas | Cuadrillas y Despacho los estaba cambiando otra sesión: **falta agregarla ahí** |
| A9 | 27/10/2026 | La pantalla escribe, y deja de valer «SOLO LECTURA, A PROPÓSITO» (21/10) | Lo pidió el usuario el 27/10: «un interruptor para delegarla o quitarla con un clic, por las funciones que ya existen». Comentarios de `views.py` y `supervisor-noc/+page.svelte` actualizados |
| A10 | 27/10/2026 | `td.bloquear`: un bloqueo por empresa y tarea (`pg_advisory_xact_lock`) en la pantalla y dentro de `td.delegar`/`td.quitar` | Dos personas que delegaban por primera vez a la vez se pisaban el registro (auditor). Prueba con dos transacciones reales |
| A11 | 27/10/2026 | `td.quitar` rechaza una tarea ya quitada | El chat re-sellaba y borraba quién y por qué sin cambiar nada (auditor) |
| A12 | 27/10/2026 | Al volver a delegar sin conversación, se conserva la del chat solo si es de la misma persona | Los avisos iban al chat de quien la delegó antes (auditor) |
| A13 | 27/10/2026 | El POST devuelve solo `{clave, delegada}`; la lista se relee con un GET | Si la lectura del nivel fallaba después de guardar, la persona veía un error de un cambio que sí quedó (auditor) |
| A14 | 27/10/2026 | Una línea de log por cambio (clave, acción, id de la persona) | La fila guarda el último estado; el historial con «volver a como estaba» es el punto 4 de la nota y no se construyó |

## Límites conocidos

- **Avisos en el chat.** Van a la conversación donde se delegó la tarea, o a
  la última conversación de quien la delegó. Una tarea delegada desde Ajustes
  por alguien que nunca habló con el Supervisor hace su trabajo igual, pero
  **no avisa en el chat**.
- **Volver a delegar una tarea ACTIVA por el chat** la pone a nombre de quien
  lo pide (regla del 08/10, con su prueba); la pantalla no lo hace (409).
- **Sin historial.** Solo el último estado y el log (A14).
- **Que las páginas de facturas y horas usen `data.hoy`** no tiene prueba:
  este vitest no puede renderizar páginas que importan `$app/forms`
  (`vitest.config.js` lo documenta). Lo cubre que la carga lo devuelva.

## Qué quedó fuera

- La pestaña en Cuadrillas y Despacho (A8).
- Los puntos 2 a 5 de la nota original: números dentro de frases, vista
  previa antes de guardar, historial con «volver a como estaba», un solo lugar
  con enlaces.

## Entregado en el mismo bloque

- **`informe_de_cruces --org <id> --dias 30`** (solo lectura): días en que dos
  o más cuadrillas tuvieron órdenes en el mismo barrio, y qué porcentaje de
  órdenes trae coordenadas del cliente. Sale solo barrio, fecha y conteos.
  Decisiones: el día de la orden es `iniciada_en` → `programada_para` → su
  asignación, en el reloj de la empresa (primero cuándo se fue de verdad: el
  reparto toma lo atrasado sin mover la fecha; auditor); la cuadrilla se
  deduce con `cuadrillas.destinatarios` (la orden no la guarda); las
  canceladas no cuentan; `(0, 0)` no cuenta como coordenada. Límites escritos
  en el comando.
- **«Hoy» en el reloj de la empresa** en facturas nuevas, facturas
  recurrentes, hoja de horas (semana por defecto y columna de hoy) y la fecha
  de cierre de un ticket. Antes salía de `toISOString()` (UTC): desde las 19:00
  de Bogotá era mañana. De paso se arregló una prueba roja de antes en
  `timesheet.test.js`: buscaba «entry» y el mensaje se tradujo a «registro».

## Bitácora

| Fecha | Qué |
|---|---|
| 27/10/2026 | Construido: ruta `supervisor/ajustes/`, pantalla, migración 0027, pruebas del efecto y mutaciones. También `informe_de_cruces` y «hoy» de la empresa en cuatro pantallas |
