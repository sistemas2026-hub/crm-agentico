# Objetivo · El panel de actividad muestra todo lo que hace el Supervisor

> Abierto el 15/10/2026. Estado: **abierto**.

## Qué significa terminado

El panel «Actividad reciente del Supervisor» muestra **todo lo que el Supervisor
deja auditado** —incluidos los cierres de casos, que hoy no se ven—, deja
**filtrar por tipo de movimiento**, y permite **mirar hacia atrás sin límite**,
cargando más a medida que se pide.

## Lo que hoy NO se ve, y es el punto

Medido el 15/10/2026 sobre el local, con la auditoría completa a la vista:

| Entidad · acción | Filas | ¿Llega al panel? |
|---|---|---|
| `PropuestaSupervisor · CREATE` | 100 | sí |
| `PropuestaSupervisor · APPROVED` | 20 | sí |
| **`Case · CREATE`** | 69 | **no** |
| **`Case · ASSIGN`** | 69 | **no** |

`operaciones/auditoria.py::recientes` admite **cuatro** entidades
(`PropuestaSupervisor`, `ActividadOperativa`, `NovedadOperativa`,
`SituacionOperativa`) y **`Case` no es una de ellas**.

**La consecuencia que importa:** cuando el Supervisor cierra un caso
desincronizado, esa auditoría se escribe **sobre el caso**, con
`STATUS_CHANGED` (lo fija `test_m09s_cierre_al_aceptar.py::test_3`). O sea que
**la acción con más efecto que el Supervisor hace hoy —28 casos cerrados solo
el 14/10 en producción— es invisible en su propio panel de actividad.**

El filtro del 15/10 (`Todo` / `Pasados a Despacho`) resolvió otra cosa: que los
pases se diluyeran entre las propuestas creadas. No toca este hueco.

## Alcance, decidido el 15/10/2026

**SÍ · todo lo que queda auditado.** Propuestas, cierres de casos,
asignaciones: lo que ya se escribe en `common.Activity`, incluido lo que se
audita sobre el caso.

**SÍ · historial completo con paginación.** El panel trae los últimos N y
carga más hacia atrás cuando se pide. Subir el límite a 100 fue descartado: con
el ciclo corriendo cada hora se vuelve a llenar y el problema reaparece en días.

**NO · lo que el Supervisor *piensa*.** Las lecturas de reclamos y los
diagnósticos del equipo viven en `operaciones_razonamiento_supervisor`, no en la
auditoría. Unir dos fuentes con orden cronológico es otro trabajo; si hace
falta, se abre su propia ficha.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | Un **cierre de caso hecho por el Supervisor aparece en el panel**. Es el agujero que motiva esta ficha | una prueba que cierra un caso y afirma que el hecho sale en `auditoria.recientes`, con la salida pegada |
| 2 | El filtro **separa por tipo de movimiento** y cada opción **dice cuántos hay** | salida pegada de la prueba del componente |
| 3 | El contrafáctico: con el filtro puesto, **lo que no corresponde NO aparece** — y «el filtro no deja nada» dice algo distinto de «no hay actividad» | salida pegada |
| 4 | **Paginación**: pedir la página siguiente devuelve hechos **más viejos**, sin repetir ni saltear ninguno | salida pegada, con los ids de dos páginas seguidas |
| 5 | Las pruebas de 1–4 **mueren al mutar** el código que cada una protege | salida de la corrida mutada, pegada |
| 6 | Backend en verde: `pytest operaciones/tests/ campo/tests/` → **12 rojos o menos** (el baseline medido contra `ae4488ba`) | salida pegada |
| 7 | Frontend: `docker compose exec frontend pnpm check` **sin empeorar** el baseline de **81 errores / 35 archivos** | salida pegada. Nunca `pnpm check` en Windows con Docker arriba |
| 8 | `git diff --cached --name-only` sin nada ajeno | pegado |

## Restricciones

Las permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es **deploy a producción**.
- **NO escribir `tenant_config`.**
- **NO cargar config ni migrar contra producción.** Leer producción sí, y solo leer.
- **NO correr los 56 casos dorados** — `--humo` (~3 min).
- **Stage por rutas explícitas**: nunca `git add .`, `git add -A`, `commit -a`, `git add SPEC/`.
- **No amend.** No mocks productivos.

Las propias de este objetivo:

- **NO ampliar `auditoria.recientes` a toda `common.Activity`.** El comentario
  de esa función ya lo advierte: sin el filtro por entidad, el feed se llena de
  «contactos editados y correos enviados, que es cierto pero no es lo que esta
  pantalla pregunta». Se agregan las entidades que el Supervisor toca, no todas.
- **NO traer los razonamientos** a este panel: está fuera del alcance decidido.
- **NO filtrar por el texto traducido del evento.** El filtro del 15/10 ya usa
  la acción cruda por este motivo: atarlo al idioma hace que una redacción nueva
  lo deje sin encontrar nada, y la pantalla se ve igual, solo vacía.
- **NO tocar el sondeo de 10 segundos** que ya existe: funciona y no es parte de
  este objetivo.

## Qué NO hacer

- **No subir el límite y declararlo resuelto.** Está descartado con su motivo:
  retrasa el problema, no lo arregla.
- **No inventar colores.** La hoja `supervisor-noc.css` tiene sus tokens y el
  panel respeta tema claro y oscuro; un color fuera de los tokens se rompe solo
  al cambiar de tema.
- **No registrar hechos nuevos** para que aparezcan. Lo que falta mostrar **ya
  está auditado**: el trabajo es mostrarlo, no escribir más filas.

## Agentes involucrados

**No lo devolvió el `orquestador`: no se pudo invocar.** De los nueve agentes de
`.claude/agents/` solo `verificador-de-api` está cargado como tipo de agente en
esta sesión; los otros ocho existen en disco y no se pueden ejecutar. Esta tabla
es el plan hecho a mano, y lo declara.

| Agente | Para qué | Estado |
|---|---|---|
| `orquestador` | Dar este plan | **no se pudo invocar** |
| `arquitecto-dexter` | ¿Se amplía `recientes` o se hace una consulta aparte? | **no disponible**. Hecho a mano: se amplía, con la lista de entidades acotada |
| `revisor-de-pii` | El panel muestra nombres de casos y descripciones: qué dato queda a la vista de quién | **no disponible, y es el que más se necesita** |
| `verificador-de-api` | **Se saltea**: no entra ningún filtro, endpoint ni parámetro de una API externa | se saltea, con motivo |
| `auditor-de-frontera` | **Se saltea**: esto solo LEE auditoría, no produce ningún efecto fuera del sistema | se saltea, con motivo |
| `corredor-de-evaluacion` | **Se saltea**: no toca el prompt ni el catálogo del motor | se saltea, con motivo |
| `auditor-independiente` | El hueco que quien construyó no puede ver | **no disponible** |
| `guardia-de-config` / `guardia-de-release` | **Se saltean mientras no haya deploy** | se saltean, con motivo |

## Bloqueos

**B1 · Los agentes de revisión no se pueden ejecutar.** Para §11.2 este cambio
es relevante por una vía —cambia qué dato se muestra— así que pedía
`revisor-de-pii`. No bloquea arrancar; sí bloquea cerrar limpio: o se carga, o
el cierre declara que ese paso se salteó y por qué.

**B2 · `SPEC/DEXTER_ESTADO_ACTUAL.md` está del 24/09** y no menciona el
Supervisor NOC. No es de este objetivo arreglarlo (un solo escritor:
`integrar-centro-mando`), pero la autoridad del estado no describe el sistema
sobre el que se trabaja.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 15/10/2026 | Ficha abierta. Medido el hueco: `Case` no entra al panel, y por eso los cierres automáticos del Supervisor son invisibles. Alcance decidido: todo lo auditado, con paginación; los razonamientos quedan fuera | Todo | — |
