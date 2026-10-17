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
sin evaluar** porque otras más viejas ocupan su lugar.

**Medido el 16/10/2026 por la tarde:** hoy solo los grupos 2 y 3 (trabajo pedido
y obra de red, con confianza alta) pueden pasar solos. La regla 1 no habilita
nada, porque el clasificador no entiende el equipo que manda el motor y nunca
confirma una falla. Ver la Fase 3.

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
| Falla de servicio que la lectura marcó **en línea y sano** (medido esa misma tarde: la etiqueta **no sale de una medición**, ver Decisiones y Fase 3) | 33 | Contradice el reclamo: persona |
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
| 16/10, tarde | **Lo que cae es el número, no la decisión.** El clasificador lee `estado`, `senal` y `causa_caida`, y el motor manda `onu_status` y `onu_signal*`. Con cualquier dato de SmartOLT, aun un equipo `Offline`, la lectura dice "en línea y sano" sin verificar (el endpoint liviano solo dice `Online` u `Offline`; `LOS` y `Power fail`, que usó la prueba del clasificador, no salen de ahí: lo corrigió el `orquestador` al encuadrar la Fase 3). Los 33 son "SmartOLT contestó algo", y ninguna falla puede pasar sola por la regla 1 | Lo halló `revisor-de-pii` y se verificó por efecto con el clasificador real (salida en `SPEC/auditorias/PASO-A-DESPACHO.md`). La decisión sigue en pie para un equipo sano de verdad. El motivo escrito ya no copia esa frase. Arreglar el clasificador cambia qué pasa solo: es la Fase 3, y la decide el usuario |
| 16/10, tarde | **Fase 3: alcance.** Entran el caso abierto y las fallas medidas, con re-medición. Quedan fuera deshacer un pase, los textos de la pantalla, la privacidad del camino y la relectura | Decidido por el usuario al encuadrar la Fase 3 |
| 16/10, tarde | **Un caso cerrado no pasa, y su propuesta se queda con el motivo escrito.** No se cancela sola | Decidido por el usuario. Cancelarla sería un efecto automático nuevo |
| 16/10, tarde | **Las fallas pendientes se vuelven a medir**, con `diagnosticar` y tope por vuelta | Decidido por el usuario. Se leyeron con el clasificador roto y la lectura no guarda el equipo: sin volver a medir, no cambian |
| 16/10, tarde | **Una caída por `LOS` o `LOF` va a una persona**, con el motivo "falta preguntarle al cliente si el equipo está enchufado y tiene luz". **Cambia la regla 1 del 14/10:** pasa sola solo la señal fuera de rango con el equipo en línea | Decidido por el usuario. La skill `smartolt-api` registra que la operación de Rapilink vio `LOS` seguido en equipos desenchufados, y desde la OLT eso no se distingue de una fibra cortada. Lo trajo el `orquestador` |
| 16/10, tarde | **El rango de señal es el del motor: de -25 a -8 dBm** (guía G-GO-04). Una señal más fuerte que -8 también está fuera de rango | Decidido por el usuario. Ya está escrito en `nucleo/herramientas/diagnostico_servicio.py`; no se agrega una tercera copia. Nunca se probó contra una señal mala real |
| 16/10, tarde | **Se enciende en sombra:** se despliega con la tarea delegada quitada, una vuelta cuenta cuántas pasarían, y con ese número se vuelve a delegar | Decidido por el usuario. Medir antes de decidir: es la primera vez que la regla 1 va a tener efecto |
| 16/10, tarde | **Una copia de WispHub más vieja que `HORAS_LECTURA_FRESCA` (72 h), o sin fecha, no deja pasar** | Derivada del principio fail-closed, no preguntada: con la copia vieja no se sabe si el ticket sigue abierto. Esta vez el 72 mide justo lo que hace falta, la frescura de la copia de WispHub. Se cambia si el usuario lo pide |
| 16/10, tarde | **Se edita `campo/tests/test_el_supervisor_llena_la_cola.py`**, solo ese archivo de pruebas | Decidido por el usuario cuando el `arquitecto-dexter` encontró el choque: fijaba la regla 1 vieja y casos sin copia de WispHub, y 5 de sus 9 pruebas quedaban en rojo con cualquier implementación correcta. El código de `campo/` no se toca |
| 16/10, tarde | **La medición es una fase propia, justo antes del paso** | Derivada del diseño del `arquitecto-dexter`, no preguntada: la lectura sale temprano cuando no hay nada nuevo, que es justo cuando las fallas viejas necesitan medirse. Cumple lo que pedía "en la fase de lectura": nunca en el paso, con tope y sin el modelo |
| 16/10, tarde | **Se mide primero la más nueva; una medición que no se pudo hacer se reintenta una vez por día** | Derivada, no preguntada. La más nueva primero, para que la falla del día pase ese día. Una vez por día porque el proveedor pide no repetir consultas y la propuesta vence a los 7 días. Se cambia si el usuario lo pide |
| 16/10, tarde | **"Cerrado" usa el vocabulario del cierre:** en Dexter `Closed` o `resolved_at`; en WispHub, fuera de la lista blanca `EN_CURSO_EN_PROVEEDOR`. Tampoco pasan un caso inactivo, fusionado o con la última lectura de WispHub con error | Derivada del fail-closed y del vocabulario que ya comparten el cierre y los detectores, para que el paso y el cierre no discrepen sobre el mismo caso. Corrige esta ficha, que decía "la lista de `fuentes_adaptadores`": esa es un literal para contar |
| 16/10, tarde | **Una medición sin causa ni señal, o en línea sin nivel, no es concluyente**: se vuelve a medir al día y su motivo no afirma la caída | Derivada del hallazgo del `auditor-independiente`: un 200 del proveedor sin datos sale del motor como "caído", y quedaba fijo los siete días de la propuesta |
| 16/10, tarde | **La pieza de medición dice cuándo se midió**, en la hora del servidor (UTC) y con su etiqueta | Derivada: el panel no muestra la hora de cada pieza, y una medición vieja se leía como la de hoy. Mostrarla en la hora de cada empresa es del panel, que esta fase no toca |
| 16/10 | **La confianza exigida sigue en alta** (9 se quedaron por media o baja) | Decidido por el usuario. Bajarla haría pasar entre 4 y 8 casos más ese día |
| 16/10 | **El tope acota cuántas pasan por vuelta, no cuántas se miran** | Tomada al encuadrar. Evaluar es barato (lee evidencia guardada, sin red); lo que hay que acotar es el efecto: si una regla se equivoca, que el daño de una vuelta tenga techo |
| 16/10 | **Sin límite de antigüedad para la medición.** Se propuso exigir menos de 72 h y se **descartó** el mismo día, al preguntar el usuario por qué 72 | El 72 de `HORAS_LECTURA_FRESCA` mide otra cosa: cuán vieja puede ser la copia del ticket que trae WispHub (el importador corre cada hora; 72 h sin sincronizar es una sincronización rota). No dice cuánto vale una medición del equipo. Además: las fallas que hacen pasar un caso —fibra cortada, señal débil— no se curan solas; con el tope arreglado una falla confirmada pasa dentro de la hora de su lectura; y si ya se resolvió, el ticket se cierra y el caso sale de la cola, que excluye los cerrados (`despacho_pantalla_views.py`). Medido el 16/10: ninguna lectura de más de 3 días. Se reabre con un caso real de una medición vieja que haya pasado. **Anotado el mismo día por `auditor-de-frontera`:** la última razón es parcial. La cola excluye los casos cerrados en Dexter, no los cerrados en WispHub, y el paso no mira ninguno de los dos. Eso no reabre la antigüedad: es otra condición, y va primera en la Fase 3 |

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
| 2.1 | Un archivo nuevo de pruebas en `operaciones/tests/` → `N passed, 0 failed` | Salida pegada **con la línea de comando** y `TEST_DATABASE_URL`. Cubre, con un caso de control por cada caso afuera: **(a)** con `TOPE_PASO_A_DESPACHO + 5` lecturas pendientes que no califican y **una nueva** con falla confirmada por la medición y fresca, la fase **acepta la nueva** (estado `ACEPTADA`, `revisado_por` nulo, auditoría con `tarea=pasar_a_despacho_segun_las_reglas`), y lo mismo con un trabajo pedido de confianza alta, que es lo único que hoy puede pasar en producción; **(b)** si califican más que el tope, pasan como mucho el tope en una vuelta y el resto en la siguiente; **(c)** una lectura que se queda lleva escrito el motivo de la última revisión y cuándo, y `GET` del detalle de la propuesta lo devuelve; **(d)** una segunda vuelta con el mismo veredicto no escribe nada nuevo; **(e)** los contrafácticos de las decisiones: equipo en línea y sano no pasa, confianza media en obra de red o trabajo pedido no pasa, grupos 4 y 5 no pasan |
| 2.2 | Cuatro mutaciones, cada una con al menos una prueba en rojo | Salida pegada por mutación, y restaurar después de cada una: volver a evaluar solo las del tope más viejas → (a); quitar el tope de pases → (b); no escribir el motivo → (c); escribirlo siempre → (d). Se corrieron nueve: estas cuatro y una por cada hallazgo de las auditorías que se cerró |
| 2.3 | Regresión de la zona en verde | `pytest` sobre `operaciones/tests/test_las_cinco_reglas.py test_el_paso_es_su_propia_fase.py test_el_pase_no_se_confunde_con_un_cierre.py test_tareas_delegadas.py test_ciclo_periodico.py test_el_supervisor_retira_lo_ajeno.py test_el_supervisor_lee_su_area_y_no_la_ajena.py test_clasificacion_de_trabajo.py` (este último porque se tocó el clasificador) y `campo/tests/test_el_supervisor_llena_la_cola.py test_despacho_pantalla.py test_ficha_despachable.py` → `N passed, 0 failed`, salida pegada |
| 2.4 | `ruff check` sobre los archivos tocados no suma avisos respecto de origin | Conteo por archivo pegado, base contra cambio. `ruff check operaciones/` entero tiene 218 avisos preexistentes: no es el criterio |
| 2.5 | `git diff --name-only origin/fix/integracion-wisphub` solo muestra `django-crm/backend/operaciones/`, esta ficha y `SPEC/auditorias/` | Salida pegada |
| 2.6 | `auditor-de-frontera` y `revisor-de-pii` en paralelo, después `auditor-independiente`, sobre **todo el camino del paso**: lo desplegado (`b3e4abf2`…`e0663595`) más lo nuevo. Hallazgos cerrados o anotados con motivo en `SPEC/auditorias/PASO-A-DESPACHO.md` | Sus informes en la conversación. Cierra el B2 de esta ficha |
| 2.7 | La bitácora tiene la fila del día con el hash, y `git diff --cached --name-only` pegado antes del commit | |
| 2.8 | **En producción, por una persona, fuera del `/goal`:** tras el deploy, la línea `paso a Despacho` del worker a la :07 dice `miradas=` igual al total de lecturas pendientes (el 16/10: 65, no 60), `miradas` igual a `pasaron + esperan el tope + se quedaron + fallaron` (sin esa suma, `miradas` se cuenta antes del bucle y no ve si el bucle dejó de evaluar), y `anotaciones fallidas=0`; y una propuesta pendiente muestra su motivo en `/supervisor-noc`, en el detalle, bajo "Hechos observados" | Log y captura de la persona |

### Fase 3 · Que pasen solas las fallas medidas, y nunca un caso cerrado

Encuadrada el 16/10/2026 por la tarde, con `/objetivo`. Siete decisiones, en la
tabla de Decisiones. **Terminado** quiere decir:

- Una falla de servicio con el equipo **en línea y la señal fuera del rango de
  -25 a -8 dBm** pasa sola a Despacho.
- Toda otra falla se queda con una persona, con un motivo que dice qué hacer:
  - sin energía (`dying-gasp`): preguntarle al cliente si tiene luz;
  - pérdida de señal (`LOS`, `LOF`): preguntarle si el equipo está enchufado y
    tiene luz, porque desde la OLT no se distingue de una fibra cortada;
  - en línea y en rango: el reclamo y la medición se contradicen;
  - sin medición posible: por qué no se pudo medir.
- Las fallas pendientes que se leyeron con el clasificador roto se vuelven a
  medir con datos frescos, en una fase propia justo antes del paso y con tope
  por vuelta.
- Ningún caso cerrado en Dexter o en WispHub pasa a Despacho. Su propuesta se
  queda, con el motivo escrito.

**De dónde sale la medición.** De `diagnosticar`, la herramienta del motor que
ya usa el cierre de desincronizados (`operaciones/diagnostico_optico.py`), con
un presupuesto por vuelta. Trae la causa de la caída y el nivel en dBm, con el
vocabulario que `clasificacion_de_trabajo._de_la_prueba` ya espera: no hace
falta una tabla de traducción nueva ni una tercera copia del rango. El endpoint
liviano de `contexto_del_caso` no sirve para esto: solo dice `Online` u
`Offline`, sin causa.

**Qué no cambia.** Los otros llamadores de `clasificar` (la sugerencia de la
pantalla de Despacho, la labor al crear la orden, y `CASO_REQUIERE_VISITA` con
su prioridad) siguen recibiendo lo que reciben hoy. También tienen H-1: quedan
anotados para otra fase.

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 3.1 | Un archivo nuevo de pruebas en `operaciones/tests/` → `N passed, 0 failed` | Salida pegada con la línea de comando y `TEST_DATABASE_URL`. Cada caso con su control. **(a)** Caso cerrado: con `status="Closed"` en Dexter no pasa; con `external_status` fuera de la lista blanca `EN_CURSO_EN_PROVEEDOR` (la del cierre y los detectores) no pasa; con la copia de WispHub más vieja que `HORAS_LECTURA_FRESCA`, o sin fecha, no pasa; abierto y fresco pasa. En los tres primeros queda el motivo escrito. **(b)** Medición, con la salida de `diagnosticar` en su forma real: en línea con -26 dBm pasa, y con -7 dBm también; en línea con -21 dBm no pasa; `dying-gasp` no pasa; `LOS` no pasa; un diagnóstico con error no pasa; cada uno con su motivo. **(c)** Re-medición: una falla pendiente medida con el clasificador roto se vuelve a medir sin llamar al modelo; como mucho el tope por vuelta; una ya medida con `diagnosticar` no se vuelve a medir. **(d)** La fase de paso no llama a ninguna herramienta del motor: solo lee el techo de autonomía, una vez por vuelta. **(e)** El valor inventado `onu_status: "LOS"` de `test_f` y `test_k` se reemplaza por la forma real del endpoint liviano, `Offline` |
| 3.2 | Mutaciones, cada una con al menos una prueba en rojo | Salida pegada por mutación, restaurando después: sin la comprobación de cerrado; la copia vieja de WispHub cuenta como abierta; `LOS` pasa solo; `dying-gasp` pasa solo; el rango invertido; las pendientes viejas no se vuelven a medir; la re-medición sin tope; la re-medición llama al modelo |
| 3.3 | Regresión en verde | La lista de 2.3, más `test_el_paso_mira_todas_y_dice_por_que.py`, las pruebas de `diagnostico_optico` y `campo/tests/test_despacho_api.py` → `N passed`, salida pegada. El rojo conocido de `test_j` se explica con una corrida bajo un rol sin superusuario |
| 3.4 | `ruff` sin avisos nuevos respecto de origin | Conteo por archivo pegado |
| 3.5 | Después de `git fetch`, `git diff --name-only origin/fix/integracion-wisphub...HEAD` muestra solo `django-crm/backend/operaciones/`, esta ficha, `SPEC/auditorias/` y el archivo de pruebas de `campo/` autorizado | Salida pegada. Nada en `nucleo/`, el código de `campo/`, el frontend ni `tenants/` |
| 3.6 | `arquitecto-dexter` antes de implementar; `auditor-de-frontera` y `revisor-de-pii` en paralelo; después `auditor-independiente`. Hallazgos cerrados o anotados en `SPEC/auditorias/PASO-A-DESPACHO-FASE3.md` | Sus informes en la conversación |
| 3.7 | La bitácora tiene la fila con el hash, y `git diff --cached --name-only` pegado antes de cada commit | |
| 3.8 | **En producción, por una persona, fuera del `/goal`.** (1) **Antes del push** se quita la tarea delegada `pasar_a_despacho_segun_las_reglas` desde el chat del Supervisor: el push espera esa confirmación. (2) En las vueltas siguientes, la línea `medicion de fallas` tiene que mostrar `concluyentes` que crecen hasta cubrir las fallas pendientes y `sin presupuesto=0`. Si domina `sin medicion`, el motor o SmartOLT no responden y la sombra no terminó: `medidas` cuenta también lo que no se pudo medir. (3) Abrir dos o tres propuestas medidas y ver que la pieza trae el nivel en dBm: si viene sin número, la lista blanca de la base no deja pasar `senal_dbm` y la regla 1 queda muerta en silencio. (4) Antes de volver a delegar, confirmar que el filtro `id_servicio` de WispHub es exacto (`verificador-de-api`, método del valor imposible): el motor toma el primer resultado. (5) La línea `paso a Despacho` dice en `pasarian por grupo=` cuántas pasarían por grupo. Con esos números se decide volver a delegar, y conviene que la sombra dure pocas horas | Log y capturas de la persona |

**Restricciones propias de la Fase 3:**

- No tocar `nucleo/`, el frontend ni `tenants/`. De `campo/`, solo el archivo
  de pruebas que autorizó el usuario.
- No cambiar lo que reciben los otros llamadores de `clasificar`.
- La medición se pide en su propia fase, justo antes del paso, con tope por
  vuelta: nunca en la fase de paso, y nunca con el modelo.
- No agregar una tercera copia del rango de señal.
- No cancelar propuestas de casos cerrados.
- Siguen las de la Fase 2: no crear órdenes ni asignar técnico o fecha, solo
  `TICKET_SIN_DIAGNOSTICO`, no cambiar la confianza exigida.

**Agentes de la Fase 3**, según el `orquestador`:

| Agente | Para qué | Estado |
|---|---|---|
| `arquitecto-dexter` | Dónde se pide `diagnosticar` y con qué presupuesto; cómo se marcan las lecturas a volver a medir; la regla de "cerrado" reusada | pendiente, antes de implementar |
| `verificador-de-api` | — | se saltea: no entra ningún endpoint, filtro ni parámetro nuevo de SmartOLT. `diagnosticar` ya corre en producción y la skill tiene verificadas sus causas |
| `auditor-de-frontera` | Que el caso cerrado falle cerrado en el único punto del efecto; el tope de la primera vuelta; que `CASO_REQUIERE_VISITA` no gane un camino para aceptarse sola | pendiente |
| `revisor-de-pii` | Qué copia el nuevo motivo (dBm, causa) al comentario de la aceptación, la evidencia y el log | pendiente |
| `auditor-independiente` | El camino entero | pendiente |
| `corredor-de-evaluacion` | — | se saltea: no cambian el prompt, el catálogo ni el modelo |
| `guardia-de-config` | — | se saltea: no se lee configuración nueva |
| `guardia-de-release` | Antes del deploy, si el diseño agrega un campo y una migración | pendiente |

**Bloqueos de la Fase 3:** ninguno impide arrancar. Lo que solo se mide en
producción, y lo hace una persona: si el caso que pasó a las 15:07 del 16/10
sigue abierto, y cuántas propuestas pendientes o aceptadas tienen el caso
cerrado. Sirve como línea de base, no frena el trabajo.

**Queda para después, decidido el 16/10:** deshacer un pase (A-2), los textos de
la pantalla que dicen que todo lo aprobó una persona (A-3), la privacidad del
camino (A-4 a A-7), la relectura que corta en las 60 más viejas (A-8), y H-1 en
los otros llamadores de `clasificar`. El detalle está en
`SPEC/auditorias/PASO-A-DESPACHO.md`.

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
  `SIN_CONDICION_DE_MEDICION`): decisiones del 14 y del 16/10. La regla 1
  cambió en la Fase 3 por decisión del usuario del 16/10: decide la medición
  del equipo, y una caída por LOS/LOF va a una persona. Las otras cuatro
  siguen iguales.
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
  `guardia-de-release`. El resto de B2 se cerró el 16/10: los tres auditores
  miraron el paso entero, lo desplegado y lo nuevo (criterio 2.6).
- **B3** (`SPEC/DEXTER_ESTADO_ACTUAL.md` viejo): sigue. Un solo escritor,
  `integrar-centro-mando`: se le entrega hash y una línea.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 14/10/2026 | Ficha abierta. Las cinco reglas decididas y medidas contra la cola real (71 tickets). Alcance acotado: aparece en Despacho, nadie asigna. Fase 0 declarada bloqueante | Todo. Arranca por la causa del 1-de-27 | — |
| 14 y 15/10/2026 | Fase 0 atacada y Fase 1 construida y desplegada, sin actualizar esta ficha | — | `ae4488ba`, `b3e4abf2`…`e0663595` |
| 16/10/2026 | Retomada con `/objetivo`. Medido en producción: corre solo, las tres puertas abiertas, 0 pasaron de 65 y era correcto por las reglas. Dos defectos encontrados (tope que tapa, motivo no escrito). Decisiones del usuario: equipo sano a persona, confianza alta. Descartada la guarda de 72 h que se había propuesto: el número medía la sincronización con WispHub, no el equipo | Fase 2 entera | — |
| 16/10/2026, tarde | Fase 2 cerrada en código: la fase mira todas las pendientes, el tope acota los pases, y la que se queda lleva escrito por qué y desde cuándo. 23 pruebas en Postgres real, 16 mutaciones muertas, regresión 201 de 202 (el rojo es el rol superusuario: bajo `crm_t` pasan las 44), ruff sin avisos nuevos. Cuatro agentes: 13 hallazgos cerrados y 15 anotados. H-1: el clasificador no entiende el equipo que manda el motor, así que ninguna falla pasa sola, y los "33 sanos" no eran una medición | Push (es deploy: lo decide una persona). El control 2.8 en producción. Decidir la Fase 3. Entregar el hash a `integrar-centro-mando` | `849cd6a5` |
| 16/10/2026, tarde | Fase 2 desplegada a las 14:53 y medida por el usuario en la vuelta de las 15:07: miradas=65, la suma cierra, 0 anotaciones fallidas, pasó 1 (un trabajo pedido con confianza alta). Fase 3 encuadrada con `/objetivo`: siete decisiones, y el `orquestador` corrigió la premisa de `LOS` (el endpoint liviano no trae causa) | Fase 3 entera. El caso que pasó a las 15:07: confirmar que sigue abierto | — |
