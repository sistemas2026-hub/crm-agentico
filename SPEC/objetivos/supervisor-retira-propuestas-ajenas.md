# Objetivo · El Supervisor retira solo lo que no es suyo

> Abierto el 16/10/2026. Estado: **cerrado en código y verificado en producción** (16/10, 11:00 Bogotá). Falta que `SPEC/DEXTER_ESTADO_ACTUAL.md` lo refleje.

## Qué significa terminado

La pestaña **Pendientes** de `/supervisor-noc` solo contiene propuestas sobre
tickets de `soporte_tecnico` y `operativo` —con dos excepciones dichas: las
propuestas de **cierre** (`CASO_DESINCRONIZADO`) siguen para todas las áreas
por decisión, y lo que **no se sabe** de qué área es (sin área escrita, y sin
nadie o con alguien que el motor no conoce) no se toca porque no se adivina—;
las demás que ya existían sobre otras áreas se cancelaron solas, con motivo,
sin esperar a que expiren a los 7 días; y ninguna de las señales de ruido
vuelve a proponer un ticket que se sabe ajeno a la hora siguiente. El comando
cuenta las dos excepciones aparte, para que un `fuera de área: 0` no se lea
como "limpio".

## De dónde viene, y qué NO duplica

- `cdaa9b27` (15/10, desplegado) escribió el área en `Case.area` y filtró por
  área **una** de las cuatro señales que leen tickets
  (`_tickets_abiertos_con_tecnico`, `operaciones/supervisor.py:533`). Las otras
  tres —`_casos_abiertos_antiguos` (:254), `_casos_que_necesitan_visita` (:343)
  y `_casos_cerrados_en_el_proveedor` (:711)— siguen leyendo todas las áreas.
- `1482523d` (16/10, desplegado) hizo lo mismo en la pantalla de Tickets.
- Las propuestas creadas **antes** del filtro, sobre cartera, ventas y
  administrativo, siguen en estado `PROPUESTA` hasta que una persona las
  revise o expiren por tiempo (`DIAS_VIGENCIA_PROPUESTA = 7`). Nada las retira
  por alcance: `expirar_vencidas` (:3266) solo mira `expira_en`.
- Esta ficha **continúa** `supervisor-solo-su-area.md`, que vive en otra
  sesión (`C:/Users/Usuario/wt-cerebro-prod`, commit `4b75be33`, sin pushear)
  y es de un solo escritor. Aquella escribe el área y filtra la lectura con
  diagnóstico; esta retira lo ya propuesto y filtra las señales de ruido. No
  se solapan en archivos; `fbef09bb` (misma sesión, sin pushear) toca
  `nucleo/seguimiento/importacion.py` y hace que los casos viejos reciban
  `area` al reconciliarse. Cuando llegue, una propuesta cancelada hoy por
  persona puede volver a proponerse si el área escrita resulta propia —
  `CANCELADA` no bloquea, y eso es correcto.

## Decisiones tomadas al abrir (16/10/2026)

| Decisión | Qué se decidió | Por qué |
|---|---|---|
| ¿Cancelar o expirar? | **`CANCELADA`**, con motivo | Su semántica escrita (`supervisor.py:3530-3548`): "dejó de tener sentido mirarla; la razón es un hecho del mundo". `EXPIRADA` significa "nadie la miró a tiempo", que sería falso |
| ¿La señal de cierre (`CASO_DESINCRONIZADO`) se filtra por área? | **No.** Sigue para todas las áreas, y sus propuestas pendientes **tampoco se retiran** | Lo decidió el usuario: es la única que cierra en el CRM un ticket que WispHub ya cerró, y hoy nadie más lo hace. Retirarlas sería deshacer cada hora lo que la señal permitida propone. Sus propuestas de otras áreas pueden seguir apareciendo |
| Área vacía y sin asignado, o asignado a alguien que no figura en el mapa del motor | **No se cancela**: es "no se sabe" | Misma regla que la ficha hermana: vacío no es un área, y no se inventa |
| Propuestas ya `ACEPTADA` / `MODIFICADA` / `RECHAZADA` sobre tickets ajenos | **Se dejan** | Una persona ya decidió; `cancelar` las rechaza con `YaRevisada` y está bien que lo haga |
| Texto del motivo | Fijo: área del caso + id del caso | Va a `auditoria.registrar` y a transcripciones: sin nombre de responsable ni texto del ticket |
| Las señales de ruido (`CASO_ANTIGUO`, `CASO_REQUIERE_VISITA`) con el mapa vacío | **Proponen solo lo que no depende de la persona**: área escrita propia, o sin área y sin nadie. Un área escrita ajena se excluye sin mapa; lo que tiene gente encima espera a la vuelta en que el motor conteste (`sin_ajenos`) | Primera versión (16/10, al construir): proponían también lo asignado sin mapa, "igual que ayer". La auditoría de frontera midió que eso oscilaba **caso por caso** con el motor caído una vuelta: retirar, re-proponer, retirar, con cota del orden de los ~500 tickets de cartera importados antes del campo, más llamadas al modelo gastadas en ajenos por `CASO_REQUIERE_VISITA`. Costo de la regla final: con el motor caído una vuelta, un caso sin área con un técnico encima espera una hora. Ninguna prueba existente siembra casos asignados sin mapa (medido con grep) |
| Qué propuestas retira | Solo las de las señales filtradas: `TIPOS_RETIRABLES_POR_AREA` (lectura con diagnóstico, caso antiguo, requiere visita) | Las de cierre (`CASO_DESINCRONIZADO`) no: la señal sigue para todas las áreas y retirarlas sería deshacer cada hora lo que propone |
| Grafía del área escrita | Se compara **sin mayúsculas ni espacios alrededor** (`Soporte_Tecnico` y `soporte_tecnico ` son soporte). Acentos y guiones no se tocan | Auditoría independiente (16/10): `Case.area` se escribe tal cual viene de `destinos`, el núcleo lo valida normalizado, y compararlo exacto cancelaba cada hora lo propio con otra grafía. Normalizar al escribir es trabajo de la importación: deuda compartida con la ficha hermana |
| Una lectura con diagnóstico cancelada por área | **No vuelve a proponerse** aunque el caso reciba después un área propia: `_tickets_abiertos_con_tecnico` excluye lo ya leído sin mirar el estado. La lectura queda en la fila cancelada, visible en "Ya decididas" | Auditoría independiente (16/10). Se deja así: cambiar `ya_leidos` para que ignore canceladas es otra decisión (volvería a pagar modelo también por lo expirado), y el caso real exige un mapa equivocado. **Decisión abierta para el dueño** |

## Criterios de aceptación

Comando y salida pegada, nunca resumida. Las pruebas del backend corren sobre
**Postgres real** (sin `TEST_DATABASE_URL` el conftest salta el contexto RLS y
el verde vale menos). La receta que funcionó el 16/10 está en la memoria
`pytest-backend-desde-worktree`: Postgres efímero en la red del compose más un
contenedor de un solo uso con el worktree montado.

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | `pytest operaciones/tests/test_el_supervisor_retira_lo_ajeno.py operaciones/tests/test_el_supervisor_lee_su_area_y_no_la_ajena.py --no-cov -v` con `TEST_DATABASE_URL` → `N passed`, 0 failed | Salida pegada **incluyendo la línea de comando** con `TEST_DATABASE_URL`. El archivo nuevo cubre, con un caso de control adentro por cada caso afuera: (a) `PROPUESTA` sobre caso `area='ventas'` asignado a un técnico → `CANCELADA`, motivo con área e id; (b) sobre caso `soporte_tecnico` → sigue `PROPUESTA`; (c) `area=''` + responsable de cartera según el mapa → `CANCELADA`; (d) `area=''` + técnico → sigue; (e) `area=''` + sin asignado → sigue; (f) `area=''` + asignado fuera del mapa → sigue; (g) mapa vacío → 0 cancelaciones; (h) `ACEPTADA`/`RECHAZADA`/`MODIFICADA` sobre ticket ajeno → intactas; (i) `correr_ciclo(org)` cancela y lo cuenta en `resumen["retiradas_por_area"]`; (j) `CASO_ANTIGUO` y `CASO_REQUIERE_VISITA` no se proponen para un caso `ventas` asignado a técnico y sí para el de control; (k) `CASO_DESINCRONIZADO` **sí** se sigue proponiendo para un caso de cartera cerrado en el proveedor, y (k2) una propuesta pendiente de ese tipo sobre un caso ajeno **no** se retira, mientras una de lectura sobre el mismo caso sí; (l) el comando `manage.py propuestas_fuera_de_area --org <id> --contar` imprime el mismo número que el ORM bajo contexto RLS, e imprime ids y conteos, nunca `name` ni `description` |
| 2 | Cuatro mutaciones, cada una deja al menos una prueba en rojo | Salida pegada por mutación (la línea `N failed`): quitar el fail-closed del mapa vacío; retirar también `ACEPTADA`; quitar el filtro de área de `_casos_abiertos_antiguos`; escribir `EXPIRADA` en vez de `CANCELADA`. Restaurar después de cada una y decirlo |
| 3 | `ruff check operaciones/` y `ruff format --check operaciones/` → exit 0 | Son pasos duros del CI del backend |
| 4 | `git diff --name-only origin/fix/integracion-wisphub` solo muestra rutas bajo `django-crm/backend/operaciones/`, esta ficha y, si hubo, `SPEC/auditorias/*` | Nada en `nucleo/`, nada en `django-crm/frontend/` |
| 5 | `auditor-de-frontera` y `revisor-de-pii` corrieron (en paralelo) y después `auditor-independiente`; cada hallazgo resuelto o anotado con motivo en `SPEC/auditorias/` | Primer escritor **automático** de un estado de propuesta, sin humano, cada hora: no se saltea |
| 6 | Esta ficha tiene la fila de bitácora del día con el hash del commit | Sin hash no hay cierre de sesión |
| 7 | **En producción, por una persona, fuera del `/goal`:** tras el deploy, pulsar "Correr ciclo" en `/supervisor-noc` (o esperar las :07) y pegar el conteo de "Pendientes" y la salida de `manage.py propuestas_fuera_de_area --contar` → `fuera de área: 0` | Es el criterio real del pedido y nadie más que una persona lo ejecuta. El 15/10 "Pendientes" eran 76 contra 64 en Soporte Técnico |
| 8 | `SPEC/DEXTER_ESTADO_ACTUAL.md` refleja el cierre | Lo escribe la sesión dueña del estado: se le entrega hash + una línea |

## Restricciones

Las permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF.
- **NO cargar config ni migrar contra producción.**
- **NO correr los 56 casos dorados** — no aplica a este cambio; si alguien
  los pide, `--humo`.
- Stage por rutas explícitas: nunca `git add .` ni `git add -A`.

Las propias de este objetivo:

- No tocar `nucleo/` ni `django-crm/frontend/`.
- No tocar `assigned_to__isnull=False` (la ficha hermana lo prohíbe) ni
  `AREAS_DEL_SUPERVISOR` (es decisión del tenant, no del código).
- `_casos_cerrados_en_el_proveedor` **no** se filtra por área (decisión del
  16/10, arriba).
- El retiro solo toca `estado = PROPUESTA` con `origen_tipo = "case"` y de
  los tipos que proponen las señales filtradas (`TIPOS_RETIRABLES_POR_AREA`:
  lectura con diagnóstico, caso antiguo, requiere visita). Nunca escribe
  `revisado_por`.
- Con el mapa del motor vacío o inalcanzable: **0 cancelaciones** y una línea
  de log sin datos de cliente. Fail-closed, igual que la lectura.
- `area=''` sin asignado, o con asignado fuera del mapa: no se cancela.
- Estado `CANCELADA`, nunca `EXPIRADA`. Motivo fijo con área e id del caso.
- Una sola función decide el criterio de área (un `Q` más una bandera "no se
  pudo saber") y la usan las tres señales de ruido y el retiro. No reutilizar
  `dentro_del_alcance` (`models.py:1100`): es nivel de autonomía, no área.
- El retiro corre dentro de `correr_ciclo`, junto a `expirar_vencidas` y
  **antes** de detectar; así corre a las :07 y con el botón "Correr ciclo".
- El comando de gestión recibe el tenant, fija `app.current_org` (sin eso
  `Case` y `PropuestaSupervisor` devuelven 0 filas sin error) y no recorre
  todas las organizaciones. Tiene `--contar` para medir sin escribir.
- Nada se ejecuta contra producción desde una sesión: ni el botón, ni el
  comando, ni un ciclo. Eso lo hace una persona.

## Qué NO hacer

- **No limpiar las pestañas "Todas" ni "Ya decididas"**: seguirán mostrando
  las canceladas con la leyenda "Propuesta cancelada. Ninguna acción se
  ejecutó." Es frontend, no hay agente para ese módulo, y "Pendientes" es la
  que abre por defecto.
- **No rellenar el área de los casos viejos**: eso es `fbef09bb`, de la otra
  sesión. Rellenarla desde acá por la persona asignada heredaría el error que
  `cdaa9b27` vino a cerrar.
- **No cancelar en un data migration al desplegar**: una migración no puede
  consultar el mapa del motor, y una escritura automática al arrancar sin que
  nadie la pida es justo lo que el diseño del Supervisor evita
  (`CicloSupervisorView`, "se expone como ruta y no como trabajo del
  scheduler a propósito").
- **No tocar `_casos_cerrados_en_el_proveedor`**, por la decisión de arriba.

## Agentes involucrados

Lo devolvió el `orquestador` el 16/10/2026. Clasificación: **relevante**,
por "produce un efecto": primera escritura automática de `CANCELADA` (hoy la
única llamada a `supervisor.cancelar` es humana, `views.py:393`), y el filtro
de señales cambia qué candidatos ve el cierre automático.

| Agente | Para qué | Estado |
|---|---|---|
| `arquitecto-dexter` | Una sola función de criterio de área para las señales y el retiro; dónde va el retiro en el ciclo; estructura de `operaciones/management/` (no existe; patrón en `common/management/commands/`) | corrió: confirmó la ubicación, `--org` UUID, y advirtió que un fail-closed en las señales de ruido rompía 14 archivos de pruebas |
| implementación | Sesión principal, con pruebas en `operaciones/tests/` siguiendo `test_el_supervisor_lee_su_area_y_no_la_ajena.py` (la fixture pasó a monkeypatchear `area_por_persona`) | hecha: 31 pruebas en verde sobre Postgres real, 6 mutaciones muertas |
| `auditor-de-frontera` | Afirmar por efecto: solo `PROPUESTA` + `origen_tipo="case"`; mapa vacío → 0; sin cierre, sin aviso al chat, sin `gobierno.registrar_decision`; que ninguna señal sin filtro re-proponga lo que acaba de cancelar (`CANCELADA` no está en `ESTADOS_QUE_BLOQUEAN`, `models.py:870`); tenant respetado | corrió, con 7 pruebas propias: 5 hallazgos, 4 cerrados y 1 anotado como deuda (`SPEC/auditorias/RETIRO-PROPUESTAS-AJENAS.md`) |
| `revisor-de-pii` | El motivo va a auditoría y la salida del comando a transcripciones: sin nombres ni texto del ticket; `logger.info` sin datos de cliente | corrió: 2 hallazgos, los dos cerrados (título fijo en la fila de auditoría; pruebas con cliente, teléfono y correos sembrados) |
| `auditor-independiente` | El hueco probable: área vacía sin asignado, y la oscilación cancelar/re-proponer | pendiente |
| `guardia-de-release` | Reducido: sin migración ni variable nueva; `core.hooksPath`, stage por rutas, `git patch-id` contra origin, evidencia post-deploy | corrió: sin bloqueos; nada automático (hook ni CI) ve un push de `django-crm/backend/` |
| `verificador-de-api` | — | se saltea: no toca ninguna API externa; `/agentes/areas` ya existe y su cliente corre en producción desde `cdaa9b27` |
| `corredor-de-evaluacion` | — | se saltea: no cambia prompt, catálogo ni modelo |
| `guardia-de-config` | — | se saltea: no toca `tenants/*.yaml` ni `tenant_config` |

El `pre-commit` solo tiene reglas para `nucleo/`: para `django-crm/` no va a
recordar ningún agente. Este plan se sigue a mano.

## Bloqueos

Ninguno impide construir. Dos impiden **afirmar que funciona en producción**:

1. **No está verificado que el worker de Celery de producción reciba el mapa
   de áreas.** Las tres variables (`MOTOR_URL`, `MOTOR_TENANT`,
   `MOTOR_SERVICE_TOKEN`) están declaradas en `docker-compose.prod.yml` para
   `celery-worker`, pero el valor no se puede ver desde una sesión. Si no
   llega, desde `cdaa9b27` la lectura no lee nada y el retiro no retira nada,
   y el síntoma es **indistinguible** de "no hay propuestas ajenas". Evidencia
   a buscar, por quien tenga acceso: en el panel, propuestas
   `TICKET_SIN_DIAGNOSTICO` creadas después del 15/10 22:01; o en el log del
   worker, la ausencia de `Supervisor: sin mapa de areas` (texto desde el
   16/10; antes decía `sin responsables de [...]`).
2. **Quien revisa necesita `EsJefeDeOperaciones`** para pulsar "Correr
   ciclo"; si no, el único camino es esperar las :07, y las :07 exigen
   `CICLO_AUTOMATICO` activa para Rapilink (probable: el ciclo corre en
   producción desde el 08/10; no se asume).

Coordinación con la otra sesión (`wt-cerebro-prod`), sin bloquear:

- Sus commits `fbef09bb`, `4b75be33` y `a03a183d` no están en origin. El
  segundo arregla los `.claude/agents/*.md` con CRLF; en esta sesión los
  agentes cargaron igual (corrieron dos), pero otra sesión puede no poder
  invocarlos hasta que ese arreglo llegue.
- Al cerrar, entregar a esa sesión el hash y una línea: su ficha tiene como
  criterio que "Pendientes" deje de superar a Soporte Técnico, y este
  objetivo es lo que lo produce.
- En su worktree hay sin trackear `django-crm/backend/tickets_reales.json`
  y `sembrar_tickets_reales.py`: el `pre-commit` solo frena lo que está en
  el stage.

Y uno que no es de nadie: el mapa de áreas se cachea 15 minutos en el worker
(`areas_del_tenant.py`). Un cambio de áreas tarda hasta eso en llegar. Desde
el 16/10 también se recuerda **un minuto** que el motor no contestó
(`SEGUNDOS_SIN_RESPUESTA`): un ciclo lee el mapa diez veces (tres señales, el
retiro y `detectar` tres veces) y sin eso eran diez esperas de hasta 5 s,
cuatro con la organización bloqueada, y lecturas distintas en la misma vuelta.

**Deuda anotada, no resuelta acá (auditoría de frontera, H3):** el mapa es
del `MOTOR_TENANT` del proceso y `AREAS_DEL_SUPERVISOR` es constante de
código. Con una segunda empresa cuya área de soporte se llame distinto, la
rama "área escrita ajena" cancelaría cada hora todas sus propuestas con área
escrita. Preexistente para la lectura desde `cdaa9b27`; el retiro lo vuelve
escritura. Hoy un solo tenant: sin efecto. Es el mismo D5 de CLAUDE.md §13
(el frontend y el backend del CRM saben de un solo tenant), y se resuelve
con ese objetivo, no con un parche acá.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 16/10/2026 | Ficha abierta tras `/objetivo`. Decisión del usuario: la señal de cierre no se filtra por área. Nada construido | Todo lo de arriba | — |
| 16/10/2026 | Construido y auditado: criterio de área en un solo lugar, retiro en el ciclo y a demanda, tres señales de ruido filtradas, comando que mide. 37 pruebas en Postgres real, 7 mutaciones muertas, 15 hallazgos de auditoría (11 cerrados; detalle en `SPEC/auditorias/RETIRO-PROPUESTAS-AJENAS.md`) | Push (= deploy, lo decide una persona); evidencia en producción (criterio 7); dos decisiones abiertas: la lectura cancelada que no vuelve y el multi-tenant de `AREAS_DEL_SUPERVISOR` | `eac5715c` |
| 16/10/2026 | **Desplegado** (`8fe34f0e`, push 10:33 Bogotá) y medido en producción por una persona, org `8a0a07ac…` ("Rapilink"; la otra, "Rapilink Telecomunicaciones", no tiene propuestas): `--contar` antes: 662 pendientes sobre tickets, 566 fuera de área (cartera 540, ventas 25, administración 1). Retiro a demanda con el comando. `--contar` después: 96 pendientes, 0 fuera de área, 0 sin saber, 0 cierres ajenos. El backend recibe el mapa del motor (sin él, el comando falla y no contó) | Que `DEXTER_ESTADO_ACTUAL.md` lo refleje; confirmar en el log del worker la línea `retiradas_por_area=` del ciclo de las :07; las dos decisiones abiertas | — |
| 29/10/2026 | **Pendientes no repite lo que ya está en Despacho: los avisos de plazo de orden (H-11, H-12) se dicen y no se proponen.** El usuario, mirando Pendientes: *«esos tickets que dicen OT-número son los mismos que están en Despacho, ¿por qué aparece acá otra con una propuesta?»* y *«creo yo que no debería duplicar esa información»*. Medido en la captura: OT-5…10 y OT-19…23 con «VENCIDO 24–25 horas», y el plazo que medían era la duración del tipo de trabajo contada desde que se creó la orden (una orden de ayer programada para hoy ya «vencía»); varias de «por vencer» seguían abiertas con la orden ya vencida. `supervisor.SOLO_SE_CUENTAN`: el ciclo y el asistente de Programación las detectan y las cuentan (el tablero las muestra), sin abrir propuesta; `retirar_las_que_solo_se_cuentan` cancela en cada ciclo las pendientes de antes, con motivo en la auditoría. Las fichas H-11 y H-12 no cambian: describen la detección. La urgencia real va en la prioridad de la orden (`ordenes_de_despacho.prioridad_del_caso`). Medido: `test_m04a_detectores_sla` 30 passed (5 reescritas: exigían la propuesta; 2 nuevas); mutaciones 5/5 muertas; ruff igual que HEAD; regresión `campo operaciones business_hours`: 3840 passed, 94 failed = las mismas de la base | Deploy; que en Pendientes no quede ninguna «OT-…» de plazo | este commit |
