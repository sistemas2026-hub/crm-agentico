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
| 17/10 | **La labor de la jornada es la de la mayoría de los casos de sus zonas ese día**; si una zona tiene de las dos, la segunda cuadrilla de esa zona toma la otra | Decidido por el usuario: la labor es lo que menos se repite (la #1 en 1 de 3 días, la #2 en 0 de 2), y el reparto solo le da a una cuadrilla órdenes de su labor |
| 17/10 | **De grupo a labor: falla de servicio → Correctivo, obra de red → Trabajos, trabajo pedido → Instalación**, como configuración por empresa | Decidido por el usuario (trabajo pedido); los otros dos ya los implica `clasificacion_de_trabajo`. Configuración y no código: en otro ISP un trabajo pedido puede ir a otra labor (CLAUDE.md §3.3) |
| 17/10 | **El Supervisor reajusta la labor de una jornada que armó él mientras no tenga órdenes**; una armada por una persona no la toca nunca | Decidido por el usuario: lo que entra a la tarde con otra labor sale ese día |
| 17/10 | **Una sola regla de armado**: si se enciende el ciclo de la madrugada, usa el mismo constructor; **no se arma con gente ausente** (`DisponibilidadTecnico`); **una cuadrilla sin zonas habituales no se arma**, queda un aviso; **el barrio de cada caso** se pide al motor una sola vez por caso, guardado y con tope por vuelta; **el día es el de la empresa** (`campo.tasks._ahora_local`) | Decisiones técnicas por el informe del `arquitecto-dexter` del 17/10: dos constructores serían dos reglas; el armado actual no mira ausencias; ningún dato guardado tiene el barrio de un caso de Despacho; con la hora del servidor, desde las 19:00 de Bogotá se armaría el día siguiente |
| 17/10 | **La regla para cubrir una zona sale de cómo se arman hoy las jornadas**, no de una regla inventada | El usuario pidió "analiza bien esa ventana de cuadrilla y dime qué se repite" antes de escribir la regla. Para eso, el comando de solo lectura `informe_de_jornadas` (Fase 0) |

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

### Fases siguientes

- **Fase 2 · Las órdenes**: crear la orden de cada caso de la cola de
  Despacho (plantilla por labor, prioridad, fecha de hoy, barrio).
- **Fase 3 · Publicar**: el reparto por el mismo camino que el botón, con
  `auditor-de-frontera`: le llega al técnico.

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

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 17/10/2026, tarde | Ficha abierta con las decisiones del usuario. `informe_de_jornadas` construido: 7 pruebas en verde con superusuario y con un rol que el RLS ata, 3 mutaciones muertas (no filtrar por empresa, comerse un día del rango, contar mal la repetición de zonas), ruff sin avisos (0.1) | Que el usuario lo corra y analizarlo (0.2) | `cf4c0855` |
| 17/10/2026, 15:40 | Guardar la ficha de una cuadrilla ya no borra el líder, el vehículo ni las notas que no se tocaron, y el selector de líder ofrece las cuentas del equipo y siempre el líder actual (B3). 13 pruebas nuevas en verde y 6 mutaciones muertas, entre ellas la que devuelve el defecto; `svelte-check` sin avisos nuevos (86/27, los mismos de antes) | Volver a ponerle el líder a la cuadrilla, y marcar las zonas habituales (B2) | este commit |
