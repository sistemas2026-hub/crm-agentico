# Objetivo · El Supervisor pasa a Despacho según las cinco reglas

> Abierto el 14/10/2026. Estado: **abierto**, bloqueado por la Fase 0.

## Qué significa terminado

Un ticket de soporte técnico u operativo aparece en la pantalla de Despacho
**sin que una persona acepte la propuesta**, cuando una de las cinco reglas lo
habilita — y los casos que ninguna regla habilita siguen esperando a una
persona, con el motivo escrito.

**Hasta dónde llega, decidido el 14/10/2026:** el Supervisor acepta su propia
propuesta y el caso entra a la cola de Despacho. **No crea la orden de trabajo
y no asigna técnico ni fecha**: eso lo sigue haciendo el despachador. Nadie sale
a la calle por decisión de la IA, y ese límite es el que hace reversible todo lo
demás — un caso mal pasado ensucia una cola; una cuadrilla mal mandada son dos
horas de alguien.

## Las cinco reglas

Decididas por el usuario el 14/10/2026. Los números son la cola real medida ese
día: **71 tickets abiertos** de `soporte_tecnico` y `operativo`.

| # | Grupo | n | Regla |
|---|---|---|---|
| 1 | **Falla de servicio**<br>no tiene internet 20 · intermitente/niveles altos 3 · lento 1 | 24 | **La medición manda.** `caido`+`fibra` → pasa solo. `senal=debil` → pasa solo. `caido`+`sin_energia` → NO es visita: hay que preguntarle al cliente. `en_linea`+`senal=buena` → **contradice el reclamo** → persona, proponiendo preguntar al cliente. `desconocido` o `sin_dato` → persona (no se lee como sano) |
| 2 | **Trabajo pedido por el cliente**<br>domicilio 5 · TDT 4 · punto TV 2 · recolección 2 · clave WiFi 1 · cámara 1 · reconexión 1 | 16 | **Pasa solo, sin condición de medición.** El equipo sano es lo normal: cambiar la clave del WiFi igual necesita que alguien vaya. Se mide igual y una falla se agrega como aviso. "No se pudo medir" **no** lo frena |
| 3 | **Obra de red**<br>intervención/mantenimiento de CTO, caja y splitter 16 · ampliaciones 6 · proyectos 2 | 24 | **Pasa solo, sin medir.** Medir al abonado del que cuelga el ticket no dice nada de una caja. Queda escrito que no había equipo de abonado que medir |
| 4 | **Reclamo que nada mide**<br>páginas bloqueadas | 2 | **Siempre persona.** Ni el ping ni los niveles ópticos lo ven |
| 5 | **Ni cliente ni red**<br>cambio de aceite · entrega de guantes · 3 con solo un nombre | 5 | **Siempre persona.** El Supervisor no tiene nada que diagnosticar |

**El reparto, y es lo que lo hace auditable:** el **modelo** clasifica el ticket
en uno de los cinco grupos leyendo la **descripción** —no el título, que viene
sucio: `INSTATALACION NUEVA`, nombres sueltos—. El **código** verifica la
medición y decide el paso. El modelo no juzga si −27 dBm es débil: eso ya lo
calcula el código contra el rango de la guía (PRD §12.5).

**Lo que esta decisión revierte, a propósito.** `models.py:811`, sobre la señal
que sale de leer el reclamo, dice: *"una labor que salió del texto queda fuera
del reparto, porque mandar una cuadrilla a manejar hasta una casa por lo que
decía una frase es pedirle a alguien que confíe en lo que nadie verificó"*. Los
grupos 2 y 3 —**40 de 71**— pasan exactamente así. El usuario lo decidió
sabiéndolo, el 14/10/2026, y lo que lo hace tolerable es el límite de alcance de
arriba: pasar a la cola no es mandar a nadie.

## Criterios de aceptación

### Fase 0 · La causa del cierre que no cierra (BLOQUEA todo lo demás)

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 0.1 | La causa está **nombrada y medida**, no inferida: el paso exacto donde se detienen las 26 que no cerraron, con la línea de código o la fila que lo prueba | pegado en la conversación |
| 0.2 | Una prueba que reproduce el **1 de 27** y **muere si se revierte el arreglo** | la salida de la corrida, y la salida de la corrida con el código mutado a propósito — las dos pegadas |
| 0.3 | En producción (solo lectura), el conteo de pendientes de desincronizado **baja del 27 medido el 14/10 17:55 UTC**, y las que queden tienen su motivo escrito | la salida del conteo por `nivel_autonomia_requerido` y `external_status`, pegada, antes y después |

### Fase 1 · Las cinco reglas

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1.1 | Una prueba **por regla** que afirma el **EFECTO** —la propuesta queda aceptada y el caso entra a la cola de Despacho— y **no** un contador del informe | salida pegada, un test nombrado por regla |
| 1.2 | El **contrafáctico de cada regla**: los grupos 4 y 5 **no** pasan, y en el grupo 1 un equipo `en_linea`+`senal=buena` **no** pasa | salida pegada |
| 1.3 | Cada prueba de 1.1 **muere al mutar** el código que la regla habilita | salida de la corrida mutada, pegada |
| 1.4 | Las 12 guardas de la zona del Supervisor en verde | `pytest` sobre `test_el_cierre_sincroniza`, `test_diagnostico_optico`, `test_m09r_cierre_controlado`, `test_m09s_cierre_al_aceptar`, `test_m09l_ciclo_integrado`, `test_ciclo_periodico`, `test_cerebro_ciclo`, `test_aviso_al_chat`, `test_m09d_shadow`, `test_m09f_gobernanza`, `test_m09_supervisor`, `test_tareas_delegadas` → `N passed`, salida pegada. El 14/10 el verde eran **361** |
| 1.5 | Si se tocó `nucleo/`: `py -3.13 tests/test_nucleo_sin_tenants.py` | salida pegada. Si no se tocó, decirlo |
| 1.6 | Si se tocó el frontend: `docker exec <frontend> pnpm check` **sin empeorar** el baseline de **81 errores / 35 archivos** | salida pegada. Nunca `pnpm check` en Windows con Docker arriba |
| 1.7 | `git diff --cached --name-only` antes de cada commit, con nada ajeno | pegado |

### Fase 2 · Cierre

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 2.1 | Los agentes de §11.2 que **sí** estén disponibles corrieron; los que no, **declarados** con su motivo | ver Bloqueo B2 |
| 2.2 | Hash entregado + una línea de qué cerró, para que `integrar-centro-mando` escriba el estado | este objetivo **no** escribe `DEXTER_ESTADO_ACTUAL.md` |

## Restricciones

Las permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es **deploy a producción**.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF.
- **NO cargar config ni migrar contra producción.** Leer producción sí, y solo leer.
- **NO correr los 56 casos dorados** — `--humo` (~3 min); los 56 tardan ~23.
- **Stage por rutas explícitas**: nunca `git add .`, `git add -A`, `commit -a`, `git add SPEC/`.
- **No amend.** No mocks productivos.

Las propias de este objetivo:

- **NO crear la orden de trabajo ni asignar técnico o fecha.** Es el límite de alcance decidido hoy, y es lo que mantiene todo reversible.
- **NO tocar `cierre_de_caso.py`** sin una prueba que muera al revertirla: ahí viven las 12 condiciones revalidadas con la fila bloqueada.
- **NO hacer que los grupos 4 y 5 pasen solos**, por ningún atajo.
- **NO reabrir** que los grupos 2 y 3 pasen sin medición (decidido el 14/10; para reabrirlo hace falta una medición nueva, §10).
- **NO afirmar sobre contadores del informe** como criterio de que algo funciona. El 14/10 ocho pruebas estuvieron en verde con el síntoma vivo por exactamente eso.

## Qué NO hacer

- **No asignar cuadrilla ni fecha.** Decidido hoy: el despachador reparte. Un error de la IA ahí cuesta el viaje de una persona, no una fila en una cola.
- **No tocar el historial de señal de SmartOLT.** El usuario lo descartó el 13/10: *"nos alcanza con el de caídas"*.
- **No clasificar por el título del ticket.** Medido: 41 asuntos distintos en 71 tickets, con typos (`INSTATALACION NUEVA`), nombres de asesora y nombres sueltos. La descripción es la fuente.
- **No usar `external_service_id` para separar grupos.** Medido el 14/10: los **71** lo tienen, incluidas las obras de red — WispHub obliga a colgar el ticket de un cliente. No separa nada.
- **No construir un segundo ciclo.** `test_m09l_ciclo_integrado.py::test_api_no_hay_segundo_ciclo` lo guarda, en dos eslabones (la vista encola, la tarea aterriza en `correr_ciclo`).

## Agentes involucrados

**No lo devolvió el `orquestador`: no se pudo invocar.** De los nueve agentes de
`.claude/agents/` solo **`verificador-de-api`** está cargado como tipo de agente
en la sesión del 14/10. Los otros ocho existen en disco y no se pueden ejecutar
—*"código construido no es código que corre"*, §6, aplicado a los agentes—.
Esta tabla es el plan hecho a mano, y lo declara.

| Agente | Para qué | Estado |
|---|---|---|
| `orquestador` | Clasificar el cambio y dar este plan | **no se pudo invocar** (`Agent type 'orquestador' not found`). Plan hecho a mano |
| `arquitecto-dexter` | ¿Reusa `CASO_REQUIERE_VISITA` y `clasificacion_de_trabajo` o duplica? | **no disponible**. Hecho a mano: las dos piezas existen y se reusan |
| `verificador-de-api` | **Se saltea**: no entra ningún filtro, endpoint ni parámetro nuevo. `diagnosticar_servicio` ya está verificado en vivo | se saltea, con motivo |
| `revisor-de-pii` | La descripción del ticket llega al modelo: de 300 tickets reales, **136** traían un documento embebido (§5) | **no disponible, y es el que más se necesita.** Ver Bloqueo B2 |
| `auditor-de-frontera` | El paso a Despacho **produce un efecto**: pasa por el techo, el interruptor, la idempotencia | **no disponible.** Ver Bloqueo B2 |
| `corredor-de-evaluacion` | **Se saltea**: el Supervisor no usa el prompt ni el catálogo del motor; `cli/evaluar.py` no alcanza su camino | se saltea, con motivo |
| `auditor-independiente` | El hueco que quien construyó no puede ver. El 14/10 habría encontrado que ocho pruebas medían el contador | **no disponible.** Ver Bloqueo B2 |
| `guardia-de-config` / `guardia-de-release` | **Se saltean mientras no haya deploy**: este objetivo no pushea | se saltean, con motivo |

## Bloqueos

**B1 · El mecanismo de puertas no funciona, y es el mismo que este objetivo
necesita.** El 14/10 el cierre automático de desincronizados cerró **1 de 27**
con las tres puertas abiertas y verificadas en producción: interruptor `activo`
(22/09), techo de la empresa en **nivel 3** (08/10, con motivo), tarea
`cerrar_desincronizados_con_diagnostico` **activa** (09/10, pedida con la frase
*"cierra los pendiente por revision que esten cerrados en wisphub y abiertos en
dexter"*). Las 27 pendientes tienen el ticket **Cerrado** en WispHub y nivel 1.
La causa **no está encontrada**. Decisión del usuario el 14/10: **se resuelve
primero**, es la Fase 0, y hasta entonces no se construye encima.

**B2 · Ocho de los nueve agentes del repo no se pueden ejecutar.** Para §11.2
este cambio es relevante por tres motivos a la vez (toca el efecto fuera del
sistema, cambia qué dato llega al modelo, y modifica el ciclo), así que exige
`auditor-de-frontera`, `revisor-de-pii` y `auditor-independiente` — los tres no
disponibles. No bloquea arrancar, **sí** bloquea cerrar: o se cargan antes de
2.1, o el cierre declara explícitamente que esos tres pasos se saltearon y por
qué. Un paso se saltea diciéndolo, nunca en silencio.

**B3 · `SPEC/DEXTER_ESTADO_ACTUAL.md` está del 24/09** —20 días— y no menciona
el Supervisor NOC ni Despacho. No es de este objetivo arreglarlo (un solo
escritor: `integrar-centro-mando`), pero significa que **la autoridad del estado
no describe el sistema sobre el que se va a trabajar**.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 14/10/2026 | Ficha abierta. Las cinco reglas decididas y medidas contra la cola real (71 tickets). Alcance acotado: aparece en Despacho, nadie asigna. Fase 0 declarada bloqueante | Todo. Arranca por la causa del 1-de-27 | — |
