# Objetivo · El Supervisor retira solo lo que no es suyo

> Abierto el 16/10/2026. Estado: **abierto**.

## Qué significa terminado

La pestaña **Pendientes** de `/supervisor-noc` solo contiene propuestas sobre
tickets de `soporte_tecnico` y `operativo`; las que ya existían sobre otras
áreas se cancelaron solas, con motivo, sin esperar a que expiren a los 7 días;
y ninguna de las señales de ruido vuelve a proponer un ticket ajeno a la hora
siguiente.

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
| ¿La señal de cierre (`CASO_DESINCRONIZADO`) se filtra por área? | **No.** Sigue para todas las áreas | Lo decidió el usuario: es la única que cierra en el CRM un ticket que WispHub ya cerró, y hoy nadie más lo hace. Sus propuestas de otras áreas pueden seguir apareciendo |
| Área vacía y sin asignado, o asignado a alguien que no figura en el mapa del motor | **No se cancela**: es "no se sabe" | Misma regla que la ficha hermana: vacío no es un área, y no se inventa |
| Propuestas ya `ACEPTADA` / `MODIFICADA` / `RECHAZADA` sobre tickets ajenos | **Se dejan** | Una persona ya decidió; `cancelar` las rechaza con `YaRevisada` y está bien que lo haga |
| Texto del motivo | Fijo: área del caso + id del caso | Va a `auditoria.registrar` y a transcripciones: sin nombre de responsable ni texto del ticket |

## Criterios de aceptación

Comando y salida pegada, nunca resumida. Las pruebas del backend corren sobre
**Postgres real** (sin `TEST_DATABASE_URL` el conftest salta el contexto RLS y
el verde vale menos). La receta que funcionó el 16/10 está en la memoria
`pytest-backend-desde-worktree`: Postgres efímero en la red del compose más un
contenedor de un solo uso con el worktree montado.

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | `pytest operaciones/tests/test_el_supervisor_retira_lo_ajeno.py operaciones/tests/test_el_supervisor_lee_su_area_y_no_la_ajena.py --no-cov -v` con `TEST_DATABASE_URL` → `N passed`, 0 failed | Salida pegada **incluyendo la línea de comando** con `TEST_DATABASE_URL`. El archivo nuevo cubre, con un caso de control adentro por cada caso afuera: (a) `PROPUESTA` sobre caso `area='ventas'` asignado a un técnico → `CANCELADA`, motivo con área e id; (b) sobre caso `soporte_tecnico` → sigue `PROPUESTA`; (c) `area=''` + responsable de cartera según el mapa → `CANCELADA`; (d) `area=''` + técnico → sigue; (e) `area=''` + sin asignado → sigue; (f) `area=''` + asignado fuera del mapa → sigue; (g) mapa vacío → 0 cancelaciones; (h) `ACEPTADA`/`RECHAZADA`/`MODIFICADA` sobre ticket ajeno → intactas; (i) `correr_ciclo(org)` cancela y lo cuenta en `resumen["retiradas_por_area"]`; (j) `CASO_ANTIGUO` y `CASO_REQUIERE_VISITA` no se proponen para un caso `ventas` asignado a técnico y sí para el de control; (k) `CASO_DESINCRONIZADO` **sí** se sigue proponiendo para un caso de cartera cerrado en el proveedor; (l) el comando `manage.py propuestas_fuera_de_area --tenant <org> --contar` imprime el mismo número que el ORM bajo contexto RLS, e imprime ids y conteos, nunca `name` ni `description` |
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
- El retiro solo toca `estado = PROPUESTA` con `origen_tipo = "case"`. Nunca
  escribe `revisado_por`.
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
| `arquitecto-dexter` | Una sola función de criterio de área para las señales y el retiro; dónde va el retiro en el ciclo; estructura de `operaciones/management/` (no existe; patrón en `common/management/commands/`) | pendiente |
| implementación | Sesión principal, con pruebas en `operaciones/tests/` siguiendo `test_el_supervisor_lee_su_area_y_no_la_ajena.py` (monkeypatch de `areas.responsables_de`) | pendiente |
| `auditor-de-frontera` | Afirmar por efecto: solo `PROPUESTA` + `origen_tipo="case"`; mapa vacío → 0; sin cierre, sin aviso al chat, sin `gobierno.registrar_decision`; que ninguna señal sin filtro re-proponga lo que acaba de cancelar (`CANCELADA` no está en `ESTADOS_QUE_BLOQUEAN`, `models.py:870`); tenant respetado | pendiente |
| `revisor-de-pii` | El motivo va a auditoría y la salida del comando a transcripciones: sin nombres ni texto del ticket; `logger.info` sin datos de cliente | pendiente, en paralelo con el anterior |
| `auditor-independiente` | El hueco probable: área vacía sin asignado, y la oscilación cancelar/re-proponer | pendiente |
| `guardia-de-release` | Reducido: sin migración ni variable nueva; `core.hooksPath`, stage por rutas, `git patch-id` contra origin, evidencia post-deploy | pendiente |
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
   worker, la ausencia de `Supervisor: sin responsables de [...]`.
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
(`areas_del_tenant.py:72`). Un cambio de áreas tarda hasta eso en llegar.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 16/10/2026 | Ficha abierta tras `/objetivo`. Decisión del usuario: la señal de cierre no se filtra por área. Nada construido | Todo lo de arriba | — |
