# Objetivo · El Supervisor arma la jornada y reparte el trabajo de Despacho

Abierto el 17/10/2026, después de desplegar la Fase 4 del paso a Despacho
(`SPEC/objetivos/supervisor-pasa-a-despacho.md`). Viene de una ficha de
Despacho donde se leía "Ese día ninguna cuadrilla cubre SOLEDAD. Ninguna
cuadrilla la tiene entre sus zonas".

## Qué significa terminado

En cada vuelta del Supervisor (a las :07), para el mismo día:

1. **Arma la jornada** de las cuadrillas para cubrir las zonas donde hay casos
   en la cola de Despacho, sea SOLEDAD, SABANAGRANDE o la que sea, con la regla
   que salga de cómo se arman hoy (Fase 0).
2. **Crea las órdenes de trabajo** de esos casos.
3. **Publica el reparto**: la orden le aparece al líder de la cuadrilla en la
   aplicación móvil.

Detrás de una tarea delegada propia y primero en sombra, como el paso a
Despacho.

## Decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 17/10 | **El Supervisor publica el reparto solo**, sin que una persona lo mire | Decidido por el usuario. Cambia la decisión "No asignar cuadrilla ni fecha. El despachador reparte" de `supervisor-pasa-a-despacho`. Por eso va detrás de una tarea delegada propia y primero en sombra |
| 17/10 | **En cada vuelta, para el mismo día** | Decidido por el usuario: lo que entra a Despacho a la tarde puede salir ese mismo día |
| 17/10 | **Salen todas las cuadrillas activas, todos los días, cada una con su pareja de siempre** | Decidido por el usuario con el informe a la vista: lo que se repite es la pareja de cada cuadrilla (la #1 y la #2 repiten la gente en todos los días seguidos medidos) |
| 17/10 | **Cada cuadrilla cubre sus zonas habituales, marcadas en Cuadrillas** | Decidido por el usuario: es configuración que una persona marca una vez, no algo que el Supervisor adivine del historial (4 días en 60 no alcanzan) |
| 17/10 | **La labor de la jornada es la de la mayoría de los casos de sus zonas ese día**; ~~si una zona tiene de las dos, la segunda cuadrilla de esa zona toma la otra~~ **Reemplazada el 21/10 por «según la cantidad»** (fila del 21/10) | Decidido por el usuario: la labor es lo que menos se repite (la #1 en 1 de 3 días, la #2 en 0 de 2), y el reparto solo le da a una cuadrilla órdenes de su labor |
| 17/10 | **De grupo a labor: falla de servicio → Correctivo, obra de red → Trabajos, trabajo pedido → Instalación**, como configuración por empresa | Decidido por el usuario (trabajo pedido); los otros dos ya los implica `clasificacion_de_trabajo`. Configuración y no código: en otro ISP un trabajo pedido puede ir a otra labor (CLAUDE.md §3.3) |
| 17/10 | **El Supervisor reajusta la labor de una jornada que armó él mientras no tenga órdenes**; una armada por una persona no la toca nunca | Decidido por el usuario: lo que entra a la tarde con otra labor sale ese día |
| 17/10 | **Una sola regla de armado**: si se enciende el ciclo de la madrugada, usa el mismo constructor; **no se arma con gente ausente** (`DisponibilidadTecnico`); **una cuadrilla sin zonas habituales no se arma**, queda un aviso; **el barrio de cada caso** se pide al motor una sola vez por caso, guardado y con tope por vuelta; **el día es el de la empresa** (`campo.tasks._ahora_local`) | Decisiones técnicas por el informe del `arquitecto-dexter` del 17/10: dos constructores serían dos reglas; el armado actual no mira ausencias; ningún dato guardado tiene el barrio de un caso de Despacho; con la hora del servidor, desde las 19:00 de Bogotá se armaría el día siguiente |
| 17/10 | **La regla para cubrir una zona sale de cómo se arman hoy las jornadas**, no de una regla inventada | El usuario pidió "analiza bien esa ventana de cuadrilla y dime qué se repite" antes de escribir la regla. Para eso, el comando de solo lectura `informe_de_jornadas` (Fase 0) |
| 21/10 | **Fases 2 y 3 se construyen: el Supervisor crea la orden (paso 7) y publica el reparto (paso 9) solo** | Pedido del usuario: «sí, hagamos el paso 7 y 9 automático», después de leer el flujo completo (12 pasos, 3 con persona) |
| 21/10 | **Crea orden para TODOS los casos de la cola de Despacho** | El usuario: «si ya pasaron a despacho están aprobados para campo» |
| 21/10 | **La prioridad la calcula el código** con la creación del ticket, el plazo para cumplir (el de la plantilla del asunto) y el asunto | El usuario: «el supervisor analiza el tiempo de creación, el tiempo para cumplir y el asunto para armar su prioridad». En código y no en el modelo: CLAUDE.md §4 |
| 21/10 | **Publica solo: al técnico le llega la visita** sin que nadie mire | Confirma la decisión del 17/10 |
| 21/10 | **Sin cuadrilla de esa labor/zona ese día, mira las disponibles y arma la jornada** (Fase 1); **con la cuadrilla armada, lee sus datos** | Decidido por el usuario: el paso 7 no inventa cuadrillas, usa el armado |
| 21/10 | **Hora de corte por empresa**, editable en Cuadrillas: antes del corte la orden sale para hoy y se publica; después queda para mañana a primera hora | Elegido por el usuario entre «según hora de corte», «siempre hoy» y «siempre mañana». Configuración y no código (CLAUDE.md §3.3) |
| 21/10 | **Un corte de red es UNA orden por puerto**; los demás casos del puerto quedan atados a ella y no generan visita | Elegido por el usuario; es como ya lo cuenta `demanda_de_despacho` |
| 21/10 | **Cupo lleno: entran hoy las más urgentes; el resto queda creado para mañana, primero en la fila**, y el aviso dice cuántas | Elegido por el usuario entre pasar a mañana, asignar igual o avisar a una persona |
| 21/10 | ~~**El Supervisor puede mover una orden publicada a otra cuadrilla mientras el técnico no la empezó**~~ **Ajustada el mismo día: solo antes de que arranque el día** (la apertura del calendario de la empresa); desde ahí lo publicado queda quieto y lo nuevo se suma | Elegido por el usuario al ver el hueco offline (D.2): un técnico sin señal que ya va en camino perdería la orden al sincronizar |
| 21/10 | **Las instalaciones nuevas se despachan igual**, aunque cuelguen del cliente de instalaciones ficticio. La orden **no copia** la dirección ni el teléfono de ese cliente: sale con lo que trae el ticket y marcada «llamar al cliente para ubicarlo» | Elegido por el usuario contra «dejarlas a una persona». Copiar la ficha del cliente ficticio mandaría al técnico a otra casa |
| 21/10 | **Aviso al teléfono del técnico cada vez que le asignan una visita**, la asigne el Supervisor o una persona (mismo `push_fcm` que las devoluciones) | Elegido por el usuario: hoy la ve recién cuando la app sincroniza |
| 21/10 | **Las cuadrillas de una zona se reparten SEGÚN LA CANTIDAD de casos de cada labor**: cada una se lleva tantos casos como su tope; primero descuentan las que no se tocan; después, de a una, el par (cuadrilla, labor) con más casos sin cubrir, y en empate la que ya tiene o tiene de habitual esa labor. Una labor con pocos casos no se lleva una cuadrilla: esos casos esperan, o los despacha una persona | Elegido por el usuario al ver en la vista previa a Soledad con 27 casos de Soporte en campo y 1 de Trabajos: la regla del 17/10 mandaba una cuadrilla entera a Trabajos por un caso. Lo usa también la madrugada (un solo constructor) |
| 21/10 | **Un feriado no es «cerrado» sin más: se trabaja o no según la cola, y lo propone el Supervisor.** Los feriados del horario de las cuadrillas quedan cerrados por defecto; **el día hábil anterior**, el Supervisor deja en Pendientes una propuesta con los números (casos en Despacho contra lo que sacan las cuadrillas en un día: cuadrillas activas × tope) y **recomienda trabajarlo si la cola supera un día de trabajo** (la cuenta la hace el código). **El horario lo define quien aprueba**: escribiéndolo en la línea del feriado (`AAAA-MM-DD HH:MM-HH:MM Nombre`); sin horario, el feriado sigue cerrado | El usuario: «no todos los festivos se trabaja, así eso se define por cantidad de ticket y eso sí lo propone el supervisor»; anticipación, regla y quién define el horario elegidos por él. Va **antes** de la 2.3: publicar solo en un feriado manda gente a la calle |
| 21/10 | **El Supervisor usa un «Horario de las cuadrillas» propio**, editable en Cuadrillas (días, horas, feriados, zona horaria y la hora de corte), y **no** el horario de atención al cliente. Sin horario de cuadrillas, no arma ni despacha y lo dice | El usuario, al ver el calendario por defecto (UTC, 09–17, sin feriados): «ese horario sería de CRM atención al cliente». Medido en el código: `capacidad.jornada_de` (`operaciones/capacidad.py:197`) lee el calendario por defecto, el mismo que cuenta los objetivos de respuesta de los tickets. Dos usos con horarios distintos no pueden compartir una fila. Va **antes** de la 2.1 |

## Lo que ya existe, medido en el código el 17/10

- **La jornada** (`JornadaDeCuadrilla`): cuadrilla, fecha, labor, zonas, líder
  del día e integrantes (`IntegranteDeJornada`). Se arma a mano en la pestaña
  Cuadrillas.
- **El armado automático** (`jornada_automatica.asegurar_jornadas`, desde
  `campo.tasks.ciclo_de_la_madrugada`): copia la jornada del último día
  trabajado. En Rapilink corre `salteadas=8` cada hora: está apagado.
- **El reparto** (`reparto.proponer`): propone qué orden va a qué cuadrilla
  por zona y labor, sin escribir. Lo publica una persona con
  `RepartoView.post`, que crea las asignaciones; recién ahí le llega al líder
  en el celular (`cuadrillas.destinatarios`).
- **La orden**: la crea una persona desde la ficha de Despacho (plantilla,
  prioridad, fecha y barrio).
- **La cola de Despacho**: `paso_a_despacho.casos_en_despacho`.

## Criterios de aceptación

### Fase 0 · Qué se repite

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 0.1 | `informe_de_jornadas` con sus pruebas en verde, con superusuario y con un rol que el RLS ata, y tres mutaciones muertas | Salida pegada |
| 0.2 | El usuario lo corre en producción (`python manage.py informe_de_jornadas --org <uuid> --dias 60`, desde `/app`) y el análisis queda escrito acá: qué cuadrillas, qué parejas, qué zonas, cuánto se repite el día | La salida y el análisis, en esta ficha |

**0.2 · Medido el 17/10 a las 13:30** (`informe_de_jornadas --dias 60` en
producción): 10 jornadas en 4 días de 60, todos miércoles o jueves.

- **Se repite la pareja**: #1 JAVIER OLIVERA + DORIAN (3 días), #2 JEIDER
  AMELL + ISAIAS MORENO (3), #3 JULIO MORENO + JESUS DAVID (1), #4 TOMAS
  MCAUSLAND + MANUEL GUERRERO (1). Días seguidos con la misma gente: #1 2 de
  3, #2 2 de 2.
- **No se repiten zonas ni labor**: zonas #1 2 de 3, #2 1 de 2; labor #1 1
  de 3, #2 0 de 2.
- **5 de las 10 jornadas no tienen zona**: el reparto no les habría dado
  nada. **Ninguna cuadrilla tiene zonas habituales.** Solo existen dos
  zonas: SOLEDAD (la cubrieron la #1 y la #2, dos días cada una) y
  SABANAGRANDE (la #5, un día).
- **La #5 figura como "Mario + Mario Vasquez"**: parece la misma persona
  cargada dos veces.

### Fase 1 · La jornada del día, sin publicar

En cada vuelta del Supervisor, para el día en curso y por cada cuadrilla
activa sin jornada (lo que armó una persona no se toca):

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1.1 | Arma la jornada con la gente de su última jornada (la pareja) y sus zonas habituales | Prueba en Postgres real |
| 1.2 | La labor es la de la mayoría de los casos de Despacho en sus zonas ese día; sin casos, su labor habitual; dos cuadrillas en una zona con las dos labores se reparten una cada una | Prueba |
| 1.3 | Una cuadrilla sin zonas habituales no se arma a ciegas: queda anotada como "sin zona" para una persona | Prueba |
| 1.4 | Corre dentro de `correr_ciclo` y detrás de su propia tarea delegada; primero en sombra | Prueba de ciclo |
| 1.5 | Mutaciones, regresión, RLS y `auditor-independiente` | Salida pegada |

**Construida en código el 17/10, sin desplegar.** Pasó por
`revisor-de-pii`, `auditor-de-frontera` y `auditor-independiente`; lo que
encontraron está corregido abajo, salvo lo que se lista como pendiente. Lo que
se decidió al construirla, cada cosa con su motivo:

- **La sombra es la tarea sin delegar**, como en el paso a Despacho: el ciclo
  calcula igual y deja en el log del worker `Supervisor: jornadas del dia ·
  sombra (...)` con lo que armaría. Para encenderla: delegar
  `armar_la_jornada_del_dia` desde el chat del Supervisor. **Rapilink ya
  tiene el nivel 3** (lo usa el paso a Despacho): la tarea es la única puerta
  que la mantiene en sombra, y `test_a2` lo fija.
- **Tres puertas**: la tarea (propia), el nivel 3 de la empresa (sale del
  catálogo, no es una copia) y que la empresa esté trabajando. Cualquiera que
  no se pueda leer cuenta como cerrada.
- **El horario se mira todo en el reloj del calendario** (`BusinessCalendar`):
  no arma antes de la apertura ni después del cierre, y si a esa hora el
  calendario ya está en otro día que la empresa, tampoco. La primera versión
  mezclaba los dos relojes y armaba de noche un día terminado (frontera); la
  segunda armaba a las 00:07, y una ausencia cargada esa mañana ya no sacaba
  al líder (independiente). Si las zonas difieren, o las dos son UTC, el
  resumen y el log lo avisan.
- **El barrio de cada caso** va como pieza `localidad_del_cliente` en la
  evidencia de la propuesta aceptada: se pide al motor una vez, con tope de 8
  por vuelta (cada pedido son hasta 30 s). Sin conexión con el motor se deja
  de preguntar en esa vuelta; un caso que falla solo se salta, para no dejar
  a la cola entera detrás de uno roto. Si el motor contesta sin ficha del
  cliente (se tragó un error del ISP), se vuelve a pedir; si el ISP no tiene
  barrio, se guarda vacío y se pide a las 24 h. El motivo guardado es de un
  conjunto cerrado.
- **La labor** sale de la tabla grupo → labor de la empresa (editable en
  Cuadrillas, sección del ciclo de la madrugada). Las visitas que pidió una
  medición (`CASO_REQUIERE_VISITA`, sin lectura del reclamo) cuentan con la
  labor del clasificador medido. **Lo ya despachado no cuenta**: un caso cuya
  orden viva ya tiene a alguien, o ya se completó, no pide cuadrilla.
  Empate: la que ya tiene, después la habitual, después correctivo,
  instalación, trabajos.
- **Dos cuadrillas en una zona**: cada una mira lo que queda sin cubrir. La
  que tiene su habitual sin cubrir se queda con ella solo si lo que deja lo
  puede tomar una que viene detrás; si no, toma la de más casos.
- **Con el líder ausente no se arma**: sin líder no hay a quién entregarle la
  orden (`destinatarios`). Un integrante con ausencia de día completo queda
  afuera; una de media mañana no lo saca.
- **"Tiene órdenes"** = alguien de la jornada tiene una orden ABIERTA
  asignada, se le haya asignado cuando sea. Se vuelve a mirar justo antes de
  escribir el reajuste.
- **`armada_por`** en la jornada, de fábrica PERSONA. Corregirla a mano la
  vuelve de una persona y el Supervisor deja de tocarla, también si la
  corrige mientras él escribe. La tabla de Cuadrillas marca las otras como
  "Armada sola".
- **Auditoría**: armar y reajustar escriben una fila en `Activity`
  (`JornadaDeCuadrilla`, actor vacío = el sistema, con la labor anterior y la
  nueva) en la misma transacción que la jornada.
- **La madrugada usa el mismo constructor**, cuenta con los barrios ya
  guardados sin preguntarle al ISP, y fija el contexto RLS de cada empresa
  (sin él no veía ausencias ni la cola, y su aviso fallaba: pre-existente).
  Cambió su regla: antes copiaba zonas y labor del último día.

**Cómo leer la sombra**: la línea comparable es **la primera después de la
apertura**, que es cuando el modo real arma. Las siguientes vuelven a planear
desde cero, como si nada estuviera armado, y no muestran el congelamiento por
órdenes ni el reajuste (independiente, hallazgo 5).

**B4 · Antes de encender, mirar en producción** (no se puede medir desde acá;
lo corre el usuario, de solo lectura):

- **La zona de la empresa y su calendario.** D-4 midió el 28/09 el calendario
  en UTC, de 09 a 17, con 0 festivos. Así la fase correría de 04:07 a 11:07
  de Bogotá y armaría los festivos. Si `Org.timezone` quedó en UTC, el aviso
  "la empresa y su calendario están en UTC" lo va a decir en cada línea.
- **Que los barrios de la cola tengan zona** (el mapeo de cada zona en
  Cuadrillas): un barrio sin mapear cuenta como "barrio sin zona".
- **Que esté delegada "Revisar solo, una vez por hora"**: sin ella no hay
  vueltas solas, y por lo tanto tampoco línea de sombra.
- **Las órdenes abiertas de cada líder**: si un líder carga órdenes viejas sin
  cerrar, su labor queda congelada desde que se arma.

**Para decidir el usuario** (no se cambió):

- **La madrugada arma con su propio interruptor** (`ConfiguracionDeReparto.
  activo`), sin la tarea ni el nivel. Ya era así antes y hoy está apagada en
  Rapilink. Opciones: que deje de armar (la fase horaria ya lo hace), o que
  pase por las mismas tres puertas.
- **¿La sombra en la pantalla?** Hoy es una línea de log. Mostrar en
  Cuadrillas "lo que armaría el Supervisor hoy" al lado de lo armado haría la
  comparación sin leer logs.

**Límites conocidos**:

- **D5**: `contexto_del_caso` y el interruptor del motor usan `MOTOR_TENANT`
  (rapilink por defecto). Con una segunda empresa, el barrio de sus casos se
  buscaría en el ISP equivocado y su freno sería el de Rapilink.
- **Una jornada ya armada no se desarma** si el líder declara la ausencia
  después de la apertura: importa en la Fase 3.
- **Dos clasificaciones**: la demanda usa el barrio del ISP y la tabla grupo →
  labor; el reparto usa `orden.zona` y la labor del tipo de trabajo. Para la
  Fase 3 tienen que coincidir.
- **El panel de actividad del Supervisor no muestra todavía** las filas de
  jornada (la entidad no está en `ENTIDADES_DEL_SUPERVISOR`).
- **Fuera de este bloque, anterior**: el botón del ciclo (`ciclo_a_pedido`)
  devuelve el resumen entero, que Celery guarda en Redis y escribe en el log
  del worker con datos de cliente de las señales (`revisor-de-pii`, F1).

### Fases siguientes

- **Fase 2 · Las órdenes**: crear la orden de cada caso de la cola de
  Despacho (plantilla por labor, prioridad, fecha de hoy, barrio).
  **La plantilla la elige `plantilla_del_caso`** (20/10/2026, ficha
  `labores-propias-por-empresa.md`, D9–D10): «plantilla por labor» es ambiguo
  apenas una labor tiene dos plantillas, y el usuario decidió que el asunto del
  ticket desempata. **Sin plantilla no se crea la orden**: el caso queda para
  una persona con el motivo que devuelve la función.
- **Fase 3 · Publicar**: el reparto por el mismo camino que el botón, con
  `auditor-de-frontera`: le llega al técnico.

### Fases 2 y 3 · plan del `arquitecto-dexter` (21/10/2026)

| Fase | Qué | Cambia la conducta de | Estimación |
|---|---|---|---|
| **2.0** | `plantilla_del_caso` y Despacho la usa (F2 ampliada de `labores-propias-por-empresa`, criterios 2.10–2.13) | la ficha humana de Despacho (con motivo) | ~1 día |
| **2.1** | Extracciones sin cambio de conducta: `labor_del_caso` (de `demanda_de_despacho`), `orden_desde_el_caso` (de `CrearOrdenView`), una sola «orden viva del caso» (hoy hay 3 copias con 2 definiciones), `plantillas_que_se_ofrecen` a `campo/plantillas.py` | nada | ~1 día |
| **2.2** | El reparto se corrige y `RepartoView.post` se extrae a `campo/reparto.py::publicar` (el botón la usa): inicio real (`iniciada_en`, bajo bloqueo), respeta `programada_para`, ordena por la prioridad, no reasigna a los mismos destinatarios, sube `revision` | **el botón humano**, cada punto dicho | ~1–1,5 días |
| **2.3** | El Supervisor **crea** las órdenes: tarea `crear_las_ordenes_de_despacho` (nivel 3), fase después del armado, una lectura de ficha por caso con tope por vuelta, lock por propuesta, prioridad única (backend, también para la ficha humana), `hora_de_corte` (campo + migración + API + pantalla), corte de red = una orden por puerto con la atadura guardada. Sombra = tarea sin delegar | ninguna hasta delegar | ~2,5–3 días |
| **3.1** | El Supervisor **publica**: tarea `publicar_el_reparto_del_dia` (nivel 3, justificado por escrito), `proponer` → `reparto.publicar(automatico=True)` solo con la empresa trabajando; mover solo si `ASIGNADA` e `iniciada_en` vacío, bajo bloqueo; sobrantes a mañana con aviso | ninguna hasta delegar | ~1,5–2 días |

Total ≈ 7–8,5 días de construcción, más al menos un día hábil de sombra
observada por fase. Sin persona, el actor es `profile=None` con
`automatico=True` explícito (patrón de `revisar`), nunca un usuario «Supervisor».
No se usa `asignar_a_jornada` (la deja como «a mano» para siempre) ni un
`origen_sistema` nuevo.

**Hallazgos que cambian el diseño** (VERIFICADOS en el código por el arquitecto):

- **A.6 · «Empezada» no se mide.** El reparto decide «el técnico la empezó» por
  el evento `trabajo_iniciado`, que **ningún código de producción escribe**;
  `test_reparto.py:252,430` lo fabrican. Lo real es `iniciada_en` (se pone al
  pasar a EN_CAMINO o EN_SITIO).
- **A.7 · Una orden por caso no la garantiza nada**: tres copias de «orden
  viva», dos definiciones, y la restricción única excluye `crm` y `manual`.
- **B.3 · El reparto ignora la prioridad y la fecha**: ordena por
  `orden.created_at` + duración, y no filtra por `programada_para`. Ya pasa con
  el botón humano: una orden para mañana se reparte hoy.
- **D.2 · Hueco offline**: el técnico puede marcar «en camino» sin red; si el
  Supervisor la mueve antes de que sincronice, el teléfono recibe 404.
- **D.5 · `MOTOR_TENANT`**: la ficha del cliente se pide al tenant del proceso,
  y `Org` no tiene campo que la ate a un tenant. Con otra empresa delegando,
  sus órdenes llevarían datos de clientes de Rapilink. Falta configuración.
- **A.5 · No hay push al asignar**: el técnico ve la orden al sincronizar.

**Decisiones tomadas por defecto** (revisables; las que cambian lo que ve el
usuario se le preguntan):

- Sin plazo en la plantilla, la prioridad ordena por antigüedad, después de las
  vencidas. «Creación» = `Case.created_at` (la importación corre cada pocos
  minutos). El asunto solo pesa a través de su plantilla.
- **Una sola regla de prioridad** para todas las órdenes, también las humanas.
- `hora_de_corte`: vacía = la fase no corre; hora:minuto; en el reloj de la
  empresa, como la Fase 1.
- Un caso que no se puede despachar bien (sin ficha, sin barrio, barrio sin
  zona, sin plantilla) **no se crea**: queda para una persona con el motivo.
- Un caso con una orden ya cerrada no recibe una segunda orden automática.
- Corte de red: la atadura se guarda en la propuesta; cerrar en WispHub los
  tickets atados queda para una persona en esta fase (efecto externo).
- El botón Publicar humano sigue y usa la **misma** función.
- D.5: la fase solo corre en la empresa atada al tenant del motor por un campo
  de configuración nuevo; sin el campo, no corre (fail-closed).

## Restricciones

- **NO push** sin decirlo: push a `fix/integracion-wisphub` es deploy a
  producción.
- **Stage por rutas explícitas**, sin `git add .` ni `git add -A`. No amend.
- **Publicar va por el mismo camino que el botón** (`RepartoView` y las
  asignaciones): sin un segundo camino a la aplicación móvil.
- **NO tocar `apps/tecnicos-mobile/`** salvo que la Fase 0 muestre que hace
  falta.

## Qué NO hacer

- No publicar sin la tarea delegada y sin pasar antes por sombra.
- No inventar la cobertura de una zona sin el análisis de la Fase 0.

## Agentes involucrados

| Agente | Cuándo |
|---|---|
| `arquitecto-dexter` | Antes de la Fase 1: dónde vive el armado, y qué es código y qué configuración |
| `auditor-de-frontera` | Publicar es un efecto: le llega al técnico y sale alguien a la calle |
| `revisor-de-pii` | El informe saca nombres de la gente de campo; la orden lleva datos del cliente |
| `auditor-independiente` | Al cerrar cada fase |

## Bloqueos

- **B1**: ~~falta el análisis de qué se repite~~ hecho el 17/10 (0.2).
- **B2**: **ninguna cuadrilla tiene zonas habituales**, y la regla decidida las
  necesita. **Y la pantalla no deja marcarlas** (arquitecto, 17/10: 0 apariciones
  en el frontend; la API las acepta). Primer paso: agregarlas al editor de cada
  cuadrilla. **Hecho en código el 17/10** (el editor trae labor y zonas
  habituales, la tabla avisa "Sin zona"); falta que una persona las marque
  después del deploy. Las marca una persona en Cuadrillas: por lo medido, SOLEDAD en la
  #1 y la #2, y SABANAGRANDE en la #5. Sin eso la Fase 1 arma cuadrillas "sin
  zona", que el reparto no usa.
- **B3**: **una cuadrilla quedó sin líder** (17/10, tarde). Al marcarle las
  zonas, guardar la ficha le borró el líder: el selector ofrecía solo personas
  de campo con la cuenta enlazada —en Rapilink ninguna la tiene—, el líder que
  ya tenía no estaba entre las opciones y volvía como «sin líder». Arreglado en
  código: el selector ofrece también las cuentas del equipo y siempre el líder
  actual, y guardar manda solo lo que se cambió. **Falta volver a ponérselo
  después del deploy**: sin líder, una orden publicada no le llega a nadie
  (`cuadrillas.destinatarios`), así que la Fase 3 lo necesita.
- **B4**: antes de encender la Fase 1, mirar en producción la zona de la
  empresa y la de su calendario (con festivos), el mapeo de barrios a
  zonas, que esté delegada la revisión horaria, y las órdenes abiertas de
  cada líder. Detalle y motivo en la Fase 1, "B4 · Antes de encender".

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 17/10/2026, tarde | Ficha abierta con las decisiones del usuario. `informe_de_jornadas` construido: 7 pruebas en verde con superusuario y con un rol que el RLS ata, 3 mutaciones muertas (no filtrar por empresa, comerse un día del rango, contar mal la repetición de zonas), ruff sin avisos (0.1) | Que el usuario lo corra y analizarlo (0.2) | `cf4c0855` |
| 17/10/2026, 15:40 | Guardar la ficha de una cuadrilla ya no borra el líder, el vehículo ni las notas que no se tocaron, y el selector de líder ofrece las cuentas del equipo y siempre el líder actual (B3). 13 pruebas nuevas en verde y 6 mutaciones muertas, entre ellas la que devuelve el defecto; `svelte-check` sin avisos nuevos (86/27, los mismos de antes) | Volver a ponerle el líder a la cuadrilla, y marcar las zonas habituales (B2) | `e88255db` |
| 17/10/2026, 18:20 | Fase 1 en código, sin desplegar: el Supervisor arma la jornada del día (la pareja de siempre, sus zonas habituales, la labor de la mayoría de los casos de Despacho de esas zonas), en sombra hasta que se delegue la tarea. Pasó por `revisor-de-pii`, `auditor-de-frontera` y `auditor-independiente`, con lo que encontraron corregido. 98 pruebas en verde con el rol de pruebas y con uno que el RLS ata; 40 mutaciones, 38 muertas a la primera y las 2 que sobrevivieron cubiertas con pruebas nuevas; regresión de `campo` y 31 archivos de `operaciones`: 1982 en verde y los mismos 12 rojos previos de origin. Migraciones `campo 0031` (dos columnas con valor de fábrica) y `common 0045` (solo opciones: no toca la base) | B2, B3 y B4 en producción; decidir la madrugada y si la sombra va a la pantalla; Fase 2 | este commit |
| 21/10/2026 | **Fase 2.0 desplegada** (`e7d6250f`, 13:53 Bogotá): `plantilla_del_caso`, una sola regla para la plantilla de un caso, usada por la ficha de Despacho. Detalle y mediciones en la bitácora de `labores-propias-por-empresa.md` | 2.1 en adelante | `e7d6250f` |
| 21/10/2026 | **Horario de las cuadrillas** (decisión del usuario del 21/10). `ConfiguracionDeReparto.calendario_de_cuadrillas` (un `BusinessCalendar` propio, no el por defecto) y `hora_de_corte`, migración `campo 0037` (dos columnas nullables); `campo/horario_de_cuadrillas.py` (leer/guardar entero, validado antes de escribir); `GET/PUT /api/campo/cuadrillas/horario/` (escribir exige gestión); `capacidad.jornada_de` lee el de cuadrillas si existe y, con `solo_de_cuadrillas`, devuelve `SIN_HORARIO_DE_CUADRILLAS`; el armado horario lo exige y lo dice. Sección «Horario de las cuadrillas» en Cuadrillas. Sin el horario, la madrugada y la programación siguen con el por defecto (sin cambio de conducta). Medido: `test_horario_de_cuadrillas` 13 + `test_el_supervisor_arma_la_jornada` 35 = 48 passed; **7 mutaciones, 7 muertas**; vitest de Cuadrillas 27; `svelte-check` 161 = origin; build OK; `makemigrations --check` sin cambios | Regresión `campo operaciones business_hours`; push; que el usuario cargue el horario | este commit |
| 21/10/2026 | **Feriados que se trabajan** (decisión del usuario del 21/10). `ConfiguracionDeReparto.feriados_trabajados` (migración `campo 0038`): una línea `AAAA-MM-DD HH:MM-HH:MM Nombre` abre ese feriado con ese horario, solo en el horario de las cuadrillas. Señal nueva `feriado_por_decidir` (migración `operaciones 0026`, solo opciones), detector `_feriados_por_decidir` en `detectar()`, redacción en `analizar()`, asistente de Programación y **habilidad H-20** registrada con la autorización del usuario (guardas de conteo actualizadas con la nota). Medido: `test_el_supervisor_propone_feriados` 12 y `test_horario_de_cuadrillas` 17 en verde; guardas de habilidades en verde salvo `test_las_diez_senales_del_modelo_tienen_ficha`, que ya fallaba en la base (los detectores de visita y de lectura no tienen ficha); vitest de Cuadrillas 28; `svelte-check` 161 = origin; **8 mutaciones, 8 muertas** | Regresión; push | este commit |
| 21/10/2026 | **Chat del Supervisor en todas sus pestañas** (pedido del usuario): `ChatBurbuja` se monta en `supervisor-noc/+layout.svelte`, una sola vez, y no se corta al cambiar de pestaña. Solo dentro de Supervisor NOC. Medido: vitest 134, `svelte-check` 161 = origin, build OK | Push | `9f6eb8f5` (desplegado 21/10 16:59) |
| 21/10/2026 | **Vista previa del armado** (pedido del usuario: «que arme ahora y muestre solo para yo ver»). `armado_de_jornadas.vista_previa`: el mismo `planear_el_dia` y la misma demanda que la fase horaria, **sin escribir** y **sin preguntarle al motor** (los casos sin barrio se cuentan aparte). `GET /api/operaciones/jornada/vista-previa/?fecha=` (módulo propio, `EsJefeDeOperaciones`); botón «Ver qué armaría el Supervisor» en Cuadrillas → El día. **El Supervisor escribe solo en el chat lo que hay que decidir** (pedido del usuario): `aviso_al_chat.avisar_decisiones` (solo `feriado_por_decidir`; a la conversación más reciente de quien delegó la revisión de cada hora, marcada como la última); enganchado al final de `correr_ciclo`; la burbuja revisa cada 2 min con la pestaña visible y muestra un contador (`lleganNuevos`, anclado en el texto del último mensaje del Supervisor). Medido: 5 pruebas de vista previa + 4 del aviso (incluido el ciclo completo, que no repite el aviso), vitest 143, **8 mutaciones, 8 muertas**, `svelte-check` 161 = origin, build OK | Regresión; push | este commit |
| 21/10/2026, noche | **Lo que mostró la vista previa en producción** (captura del usuario, 22/10 pedido): (1) calculaba el día cargado y no el elegido en la caja → usa la caja; (2) «dejar (misma_labor)» sin traducir → frase; (3) «Quiénes» vacío en las ya armadas → la gente de esa jornada; (4) **el armado intercambiaba labores sin necesidad** (Soledad: la #2 de correctivo a trabajos y la #3 de trabajos a correctivo, mismo resultado) → `_elegir_labores` primero deja con su labor a la ya armada cuya labor todavía tiene casos sin cubrir; (6) **21 casos con barrio sin zona** → la vista previa los nombra (`barrios_sin_zona`, mismo criterio que la demanda). Medido: `test_w` (el caso de Soledad) y `test_vp6`/`test_vp7`, 74 passed; **5 mutaciones, 5 muertas** (una sobrevivió a la primera y originó el caso despachado de `test_vp6`); `svelte-check` 161 = origin; build OK. **Pendiente de decisión del usuario**: 27 casos de correctivo y 1 de trabajos en una zona sacan una cuadrilla entera a trabajos (regla del 17/10) | Regresión; decisión; push | este commit |
| 21/10/2026, noche | **«Según la cantidad»** en `_elegir_labores` (reemplaza la pasada de la fila anterior). Medido: `test_armado_del_dia` 34 passed — las pruebas de la regla vieja (no cruzar por orden alfabético, la segunda toma la otra si hay trabajo, lo que cubre una armada a mano) siguen en verde con la nueva; nuevas `test_w` (27 contra 1), `test_w2` (9 contra 8: una para cada una), `test_w3` (el tope propio cuenta); **6 mutaciones, 6 muertas**, incluida la que vuelve a la regla del 17/10 | Regresión; push | este commit |
| 22/10/2026 | **Fase 2.1: del caso a la orden, una sola traducción** (sin cambio de conducta). Lo que «Despachar» hacía adentro de la vista queda en `campo/services/despacho.py`: `ordenes_vivas_del_caso` (también la usan las dos copias de la ficha de Despacho), `cliente_para_la_orden` (lo escrito gana; si no, la ficha recortada al largo de la columna) y `anotar_labor_sugerida` (solo con ficha, nunca levanta). La labor de un caso en la demanda sale de `armado_de_jornadas.labor_del_caso` (cliente nuevo = instalación, corte de red = obra). Medido: `test_del_caso_a_la_orden` 7 + `test_ldc_la_labor_de_cada_caso` y las de la vista, 253 passed; **6 mutaciones, 6 muertas** (dos sobrevivieron a la primera y originaron `test_ldc`); regresión `campo operaciones business_hours`: 3456 passed, **los mismos 94 rojos de la base, por nombre** | 2.2 (correcciones del reparto); 2.3 (el Supervisor crea las órdenes) | este commit |
