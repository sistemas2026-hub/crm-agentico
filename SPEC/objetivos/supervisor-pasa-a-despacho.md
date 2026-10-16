# Objetivo · El Supervisor pasa a Despacho según las cinco reglas

> Abierto el 14/10/2026. **Retomado el 16/10/2026** con `/objetivo`. Estado:
> **abierto** — el mecanismo está construido y corre solo en producción; faltan
> dos defectos medidos y la auditoría que nunca corrió sobre él.

## Qué significa terminado

Un ticket de soporte técnico u operativo aparece en la pantalla de Despacho
**sin que una persona acepte la propuesta**, cuando una de las cinco reglas lo
habilita — y los casos que ninguna regla habilita siguen esperando a una
persona, **con el motivo escrito en la propuesta**, visible para quien la abre.

Agregado el 16/10/2026, por lo que midió ese día: **ninguna propuesta se queda
sin evaluar** porque otras más viejas ocupan su lugar, y **una falla de servicio
no pasa con una medición vieja**.

**Hasta dónde llega, decidido el 14/10/2026:** el Supervisor acepta su propia
propuesta y el caso entra a la cola de Despacho. **No crea la orden de trabajo
y no asigna técnico ni fecha**: eso lo sigue haciendo el despachador. Nadie sale
a la calle por decisión de la IA, y ese límite es el que hace reversible todo lo
demás — un caso mal pasado ensucia una cola; una cuadrilla mal mandada son dos
horas de alguien.

## Dónde estamos, medido el 16/10/2026 en producción

Lo midió una persona con comandos de solo lectura en el contenedor del backend,
sobre la organización **Rapilink** (`8a0a07ac…`; "Rapilink Telecomunicaciones",
`d6f49f55…`, no tiene propuestas), y con el log del `celery-worker`.

**Ya corre solo, sin botón.** Las tres puertas están abiertas:

```
A delegadas: ['pasar_a_despacho_segun_las_reglas',
              'cerrar_desincronizados_con_diagnostico',
              'revisar_solo_con_cada_actualizacion']
B techo: {'puede': True, 'efectivo': 3, 'motivo': ''}
16:07 UTC  ciclo_del_supervisor ... {'empresas': 1, ...}
16:08 UTC  Supervisor: paso a Despacho · pasaron=0 · se quedaron=60 · fallaron=0
```

**Pasó cero, y con las reglas vigentes era la respuesta correcta.** De las 65
lecturas pendientes, ninguna califica:

| Grupo y medición | n | Lo que dice la regla |
|---|---|---|
| Falla de servicio, equipo **en línea y sano** | 33 | Contradice el reclamo: persona |
| Falla de servicio que no se pudo medir (`onu_no_vinculada` 4, `serial_desactualizado` 3) | 7 | Sin dato no es sano: persona |
| Sin grupo: el modelo no supo clasificar | 10 | Persona |
| Obra de red o trabajo pedido, confianza media o baja | 9 | Sin medición se exige alta: persona |
| Página bloqueada, o ni cliente ni red | 6 | Siempre persona |

Y las lecturas son **frescas**: 55 de 65 tienen menos de 24 h, y ninguna más de
3 días. Volver a medir no habría cambiado el resultado de ese día.

**Los dos defectos que sí encontró la medición:**

1. **El tope deja propuestas sin evaluar.** La fase mira las 60 más viejas
   (`TOPE_PASO_A_DESPACHO`, `supervisor.py`, `.order_by("created_at")[:60]`) y
   había **65**. Las que nunca califican ocupan la ventana cada hora, así que
   una falla **nueva** confirmada por la medición —justo la que tiene que pasar
   sola— entra última y no se evalúa hasta que salgan otras: días, por la
   vigencia de 7. Y no hay otro camino: `pasar_si_corresponde` tiene **un solo
   llamador**, esa fase.
2. **El motivo no queda escrito.** Por qué se quedó cada propuesta sale solo
   **sumado** en una línea del log del worker. En el panel, una propuesta
   revisada a las 11:07 se ve igual que una que nadie miró, y por eso parece
   que el Supervisor no revisa. La definición de terminado lo pedía desde el
   14/10.

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

**Lo que esta decisión revierte, a propósito.** `models.py`, sobre la señal
que sale de leer el reclamo, dice: *"una labor que salió del texto queda fuera
del reparto, porque mandar una cuadrilla a manejar hasta una casa por lo que
decía una frase es pedirle a alguien que confíe en lo que nadie verificó"*. Los
grupos 2 y 3 pasan exactamente así. El usuario lo decidió sabiéndolo, el
14/10/2026, y lo que lo hace tolerable es el límite de alcance de arriba: pasar
a la cola no es mandar a nadie.

## Decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 14/10 | Las cinco reglas, y el límite: entra a la cola, nadie asigna | Ver arriba |
| 14/10 | Sin medición (grupos 2 y 3) se exige confianza **alta** en la lectura | Lo único entre el caso y una frase ambigua |
| 16/10 | **La falla con el equipo en línea y sano sigue yendo a una persona** (33 de 40 fallas ese día) | Decidido por el usuario con el número a la vista. La red no es el problema; puede ser el WiFi, el router, o que ya se resolvió. No se manda a nadie sin confirmar |
| 16/10 | **La confianza exigida sigue en alta** (9 se quedaron por media o baja) | Decidido por el usuario. Bajarla haría pasar entre 4 y 8 casos más ese día |
| 16/10 | **El tope acota cuántas pasan por vuelta, no cuántas se miran** | Tomada al encuadrar. Evaluar es barato (lee evidencia guardada, sin red); lo que hay que acotar es el efecto: si una regla se equivoca, que el daño de una vuelta tenga techo |
| 16/10 | **Una falla de servicio pasa solo con una medición de menos de 72 h** (`HORAS_LECTURA_FRESCA`, la misma que exige el cierre) | Tomada al encuadrar, y es fail-closed: hoy `de_la_propuesta` decide con la última lectura guardada sin mirar su hora, y la fase mira primero las más viejas. Achica la autonomía, no la agranda. Si el usuario la objeta, se saca |

## Criterios de aceptación

### Fase 0 · El cierre que no cerraba — superada por los hechos

La atacó `ae4488ba` (14/10 12:35, *"Los 23 desincronizados que el proveedor ya
cerró se cierran, y no de a tres"*), que nombra la causa —tres rejas, la
tercera escondida por un `continue` sin log— y declara sus mutaciones. El "1 de
27" de esta ficha se midió 20 minutos después de ese commit, probablemente
antes de que se desplegara (inferido). El 16/10 el log de las :07 corre la fase
de cierre (`cerrados=0 no_evaluados={} no_cerrados={}`) y quedan como mucho 5
propuestas pendientes fuera de los tres tipos de ticket. **No se pegó evidencia
formal de 0.1 a 0.3**: queda dicho, no se reabre sin una medición que la
contradiga.

### Fase 1 · Las cinco reglas — construida y desplegada

`b3e4abf2`, `fbe730e4`, `76509cf6`, `cb0dfb6b`, `972eba4d`, `3eb647f9`,
`c5cf8f52`, `e0663595` (14 y 15/10), con sus pruebas (`test_las_cinco_reglas.py`,
`test_el_paso_es_su_propia_fase.py`, `test_el_pase_no_se_confunde_con_un_cierre.py`)
y las mutaciones declaradas en cada commit. El 15/10 se midió `pasaron=0 →
pasaron=3`. Corre solo desde que se delegaron las tres tareas (medido 16/10).

### Fase 2 · Lo que midió el 16/10

Comando y salida pegada, nunca resumida. Pruebas sobre **Postgres real**: receta
en la memoria `pytest-backend-desde-worktree` (Postgres efímero en la red del
compose y contenedor de un solo uso con el worktree montado; `--reuse-db` para
correr mutaciones en serie).

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 2.1 | Un archivo nuevo de pruebas en `operaciones/tests/` → `N passed, 0 failed` | Salida pegada **con la línea de comando** y `TEST_DATABASE_URL`. Cubre, con un caso de control por cada caso afuera: **(a)** con `TOPE_PASO_A_DESPACHO + 5` lecturas pendientes que no califican y **una nueva** con falla confirmada por la medición y fresca, la fase **acepta la nueva** (estado `ACEPTADA`, `revisado_por` nulo, auditoría con `tarea=pasar_a_despacho_segun_las_reglas`); **(b)** si califican más que el tope, pasan como mucho el tope en una vuelta y el resto en la siguiente; **(c)** una lectura que se queda lleva escrito el motivo de la última revisión y cuándo, y `GET` del detalle de la propuesta lo devuelve; **(d)** una segunda vuelta con el mismo veredicto no escribe nada nuevo; **(e)** una falla confirmada con medición de más de 72 h no pasa, y el motivo lo dice; **(f)** los contrafácticos de las decisiones: equipo en línea y sano no pasa, confianza media en obra de red o trabajo pedido no pasa, grupos 4 y 5 no pasan |
| 2.2 | Cinco mutaciones, cada una con al menos una prueba en rojo | Salida pegada por mutación, y restaurar después de cada una: volver a evaluar solo las del tope más viejas → (a); quitar el tope de pases → (b); no escribir el motivo → (c); escribirlo siempre → (d); quitar el control de las 72 h → (e) |
| 2.3 | Regresión de la zona en verde | `pytest` sobre `operaciones/tests/test_las_cinco_reglas.py test_el_paso_es_su_propia_fase.py test_el_pase_no_se_confunde_con_un_cierre.py test_tareas_delegadas.py test_ciclo_periodico.py test_el_supervisor_retira_lo_ajeno.py test_el_supervisor_lee_su_area_y_no_la_ajena.py` y `campo/tests/test_el_supervisor_llena_la_cola.py test_despacho_pantalla.py test_ficha_despachable.py` → `N passed, 0 failed`, salida pegada |
| 2.4 | `ruff check` sobre los archivos tocados no suma avisos respecto de origin | Conteo por archivo pegado, base contra cambio. `ruff check operaciones/` entero tiene 218 avisos preexistentes: no es el criterio |
| 2.5 | `git diff --name-only origin/fix/integracion-wisphub` solo muestra `django-crm/backend/operaciones/`, esta ficha y `SPEC/auditorias/` | Salida pegada |
| 2.6 | `auditor-de-frontera` y `revisor-de-pii` en paralelo, después `auditor-independiente`, sobre **todo el camino del paso**: lo desplegado (`b3e4abf2`…`e0663595`) más lo nuevo. Hallazgos cerrados o anotados con motivo en `SPEC/auditorias/PASO-A-DESPACHO.md` | Sus informes en la conversación. Cierra el B2 de esta ficha |
| 2.7 | La bitácora tiene la fila del día con el hash, y `git diff --cached --name-only` pegado antes del commit | |
| 2.8 | **En producción, por una persona, fuera del `/goal`:** tras el deploy, la línea `paso a Despacho` del worker a la :07 dice `se quedaron=` igual al total de lecturas pendientes (el 16/10: 65, no 60), y una propuesta pendiente muestra su motivo en `/supervisor-noc` | Log y captura de la persona |

## Restricciones

Las permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es **deploy a producción**.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF.
- **NO cargar config ni migrar contra producción.** Leer producción sí, y solo
  leer, y lo hace una persona.
- **NO correr los 56 casos dorados** — no aplica a este cambio.
- **Stage por rutas explícitas**: nunca `git add .`, `git add -A`, `commit -a`,
  `git add SPEC/`.
- **No amend.** No mocks productivos.

Las propias de este objetivo:

- **NO crear la orden de trabajo ni asignar técnico o fecha.**
- **NO tocar las cinco reglas ni sus umbrales** (`decidir`,
  `CONFIANZA_EXIGIDA_SIN_MEDICION`, `SIEMPRE_UNA_PERSONA`,
  `SIN_CONDICION_DE_MEDICION`): decisiones del 14 y del 16/10.
- **NO sumar tipos de propuesta al paso automático**: sigue siendo solo
  `TICKET_SIN_DIAGNOSTICO`.
- **NO volver a medir equipos desde la fase de paso**: ninguna llamada nueva al
  motor. Medido el 16/10: 55 de 65 lecturas tenían menos de 24 h.
- **El tope acota los pases por vuelta, no las propuestas que se miran.**
- **El motivo se escribe solo cuando cambia el veredicto**: sesenta filas por
  hora repitiendo lo mismo entierran lo que cambió.
- **El motivo lleva texto fijo y técnico** (el `porque` de `decidir` y la hora),
  nunca el asunto, la descripción ni el nombre del cliente.
- **NO tocar `nucleo/` ni `django-crm/frontend/`.** Si el motivo escrito no se
  ve en el panel sin tocar el frontend, se dice al cerrar y queda para otra
  ficha: no hay agente para ese módulo.
- **NO tocar `cierre_de_caso.py`** sin una prueba que muera al revertirla.
- **NO afirmar sobre contadores del informe** como criterio de que algo
  funciona: el 14/10 ocho pruebas estuvieron en verde con el síntoma vivo por
  exactamente eso.

## Qué NO hacer

- **No asignar cuadrilla ni fecha.** El despachador reparte.
- **No mandar a Despacho la falla con el equipo sano**, ni bajar la confianza
  exigida: decididos el 16/10 con el número a la vista.
- **No vincular ONUs ni corregir seriales desde acá.** Las 13 lecturas que no
  se pudieron medir (`onu_no_vinculada`, `serial_desactualizado`) son un dato
  que falta en WispHub o SmartOLT; el motor ya tiene `cli/proponer_sn_onu.py` y
  `cli/aplicar_sn_onu.py` para eso, y es trabajo de operación.
- **No automatizar `CASO_REQUIERE_VISITA` ni `CASO_ANTIGUO`.** Aceptar un caso
  antiguo no manda nada a Despacho; la visita no trae grupo y abriría un atajo
  a los grupos 4 y 5. Si se quiere, es otra decisión con su medición.
- **No tocar el historial de señal de SmartOLT** (descartado el 13/10).
- **No clasificar por el título del ticket** ni separar grupos por
  `external_service_id` (medido el 14/10: no separa nada).
- **No construir un segundo ciclo**: `test_m09l_ciclo_integrado.py` lo guarda.

## Agentes involucrados

Lo devolvió el `orquestador` el 16/10/2026: el pedido literal ("que lo haga
automático, sin botón") **ya estaba cumplido** y no exigía código; lo que
queda es relevante por §11.2 porque cambia un efecto autónomo vivo.

| Agente | Para qué | Estado |
|---|---|---|
| `orquestador` | Clasificar y planear | corrió el 16/10 |
| `arquitecto-dexter` | Dónde vive el motivo escrito (¿evidencia de la propuesta o campo propio?) y cómo se evalúan todas sin que el tope muerda | pendiente |
| implementación | Sesión principal | pendiente |
| `auditor-de-frontera` | Todo el camino del paso, lo desplegado y lo nuevo: otro llamador que acepte sin persona, la frescura, la reversibilidad (hoy una `ACEPTADA` no se puede sacar de la cola desde la pantalla) | pendiente; nunca corrió sobre lo desplegado |
| `revisor-de-pii` | La descripción del ticket va al modelo; qué copian el comentario de la aceptación, el motivo nuevo y el log | pendiente; nunca corrió sobre lo desplegado |
| `auditor-independiente` | El hueco que quien construyó no ve | pendiente |
| `guardia-de-release` | Antes del push: push = deploy | pendiente |
| `verificador-de-api` | — | se saltea: ningún filtro, endpoint ni parámetro nuevo |
| `corredor-de-evaluacion` | — | se saltea: el Supervisor no usa el prompt ni el catálogo del motor |
| `guardia-de-config` | — | se saltea: no se toca `tenant_config` ni ningún YAML |

## Bloqueos

Ninguno impide arrancar.

- **B1** (el cierre que no cerraba): superado, ver Fase 0.
- **B2** (los agentes no cargaban el 14/10): el 16/10 cargaron el
  `orquestador` y, en el objetivo hermano, `arquitecto-dexter`,
  `auditor-de-frontera`, `revisor-de-pii`, `auditor-independiente` y
  `guardia-de-release`. Lo que queda de B2 es que esos tres auditores **nunca
  miraron el paso ya desplegado**, y eso es el criterio 2.6.
- **B3** (`SPEC/DEXTER_ESTADO_ACTUAL.md` viejo): sigue. Un solo escritor,
  `integrar-centro-mando`: se le entrega hash y una línea.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 14/10/2026 | Ficha abierta. Las cinco reglas decididas y medidas contra la cola real (71 tickets). Alcance acotado: aparece en Despacho, nadie asigna. Fase 0 declarada bloqueante | Todo. Arranca por la causa del 1-de-27 | — |
| 14 y 15/10/2026 | Fase 0 atacada y Fase 1 construida y desplegada, sin actualizar esta ficha | — | `ae4488ba`, `b3e4abf2`…`e0663595` |
| 16/10/2026 | Retomada con `/objetivo`. Medido en producción: corre solo, las tres puertas abiertas, 0 pasaron de 65 y era correcto por las reglas. Dos defectos encontrados (tope que tapa, motivo no escrito). Decisiones del usuario: equipo sano a persona, confianza alta | Fase 2 entera | — |
