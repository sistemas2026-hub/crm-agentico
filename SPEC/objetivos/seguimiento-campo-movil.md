# Objetivo · El técnico reporta desde el teléfono, en la misma bitácora

> Abierto el 30/09/2026. Estado: **abierto**, sin implementación.

## Qué significa terminado

El técnico registra INICIO, AVANCE, BLOQUEO y CIERRE **desde la aplicación de
campo**, sin señal si hace falta, y esos reportes son los mismos `EventoTrabajo`
que el NOC ve en el CRM. Una sola bitácora, dos puertas.

Nace de una medición: el seguimiento de campo se cerró en producción el
30/09/2026 y **la app no lo conoce**. Sobre sus 66 archivos, las menciones a
`seguimiento`, `inicio_campo`, `avance_campo`, `bloqueo` y `requiere_noc` son
**cero**. Y el técnico es justamente quien está en la calle: hoy los cuatro
momentos solo se pueden reportar desde el CRM, que usa el NOC.

## Lo que YA está construido (medido el 30/09/2026)

Esto se mide antes de planear, y acá cambió el plan dos veces:

| Lo que ya existe | Dónde | Consecuencia |
|---|---|---|
| **El formulario dinámico entiende el vocabulario del backend**: `{id, titulo, tipo, ayuda, reglas:{required, options}}` | `lib/features/ejecucion/campo_del_formulario.dart` | Los cuatro formularios de seguimiento se dibujan **sin un solo cambio**: son el mismo vocabulario de `campo/services/validador.py` |
| `Idempotency-Key` en cuatro lugares y un campo `idempotency_key` por fila | `lib/core/sync/sync_queue_service.dart` | La idempotencia que el endpoint pide ya está resuelta |
| Siete colas con su procesador cada una (`cola_mutaciones`, `cola_movimientos_material`, `cola_incidencias`, `cola_evidencias`, `local_datos_dirty`…) | `lib/core/storage/local_database.dart` | El molde para `cola_seguimiento` está copiado siete veces |
| **Custodia, consumo, devolución y cierre de jornada: 3.290 líneas** | `lib/features/materiales/` y `ejecucion/widgets/consumo_de_material.dart` | **No se construye inventario en la app.** Ya está, y con offline |
| 621 pruebas verdes, `flutter analyze` sin hallazgos | `test/` | Hay red donde apoyarse |

**Conclusión de la medición: esto es mayormente reuso.** Lo caro —formulario
dinámico, cola con idempotencia, base local, sincronización— está hecho. Lo nuevo
es una tabla, su procesador, una pantalla y la barra contextual.

Y un dato que conviene leer antes de tocar `campo_del_formulario.dart`: ese archivo
nació de arreglar **dos lecturas del mismo campo** —el widget aceptaba `clave` o
`id`, la validación de cierre solo `clave`— y el síntoma era que **se podía cerrar
un trabajo con los obligatorios vacíos**. Es el mismo patrón que el
`estado_nuevo`/`nuevo_estado` del CRM, tres días después. Por eso la guarda de
abajo.

## LA DECISIÓN DE ESTE OBJETIVO: el tiempo offline no genera vencimiento

Un reporte creado sin conexión conserva **dos tiempos**, y cada uno gobierna una
cosa distinta:

    capturado_en_dispositivo   ->  reconstruye la HISTORIA
    recibido_en_servidor       ->  gobierna el SEGUIMIENTO operativo

Un AVANCE escrito a las 08:00 y recibido a las 09:47 deja el trabajo **al día a
las 09:47**. No «vencido desde las 08:30».

**Por qué.** El sistema no sabe si el técnico estaba sin señal, en una zona sin
cobertura, con la app cerrada, o si el teléfono sincronizó tarde. La Fase D ya
decidió que sin una señal real de contacto no se distingue «sin señal» de «sin
contacto», y que no se acusa a nadie con información insuficiente. Esto es esa
misma decisión, aplicada al caso que la app va a producir todos los días.

**Lo que el NOC SÍ ve**, porque es un dato y no una acusación:

    08:00  AVANCE · creado en el dispositivo
    09:47  recibido por Dexter
           demora de sincronización: 1h47m

Eso abre una métrica futura —zonas con mala cobertura, tiempos de sincronización,
problemas de la aplicación— **sin contaminar la operación diaria**.

Esta decisión parece chica hoy. En seis meses define si el NOC le cree al sistema:
un tablero que marca en rojo a quien estaba trabajando bien se deja de mirar.

## Decisiones cerradas

**1 · No hay lógica de formularios nueva.** Se reusa
`campo_del_formulario.dart`, el esquema viene del backend, y los campos de cada
momento los declara `WorkTypeVersion`. Si una empresa cambia una medición, no se
publica una app nueva.

**2 · La app no crea una fuente de verdad.** `EventoTrabajo` sigue siendo la
bitácora. La app **genera eventos**, no los interpreta.

**3 · Offline-first.** Cada reporte se guarda local, lleva `Idempotency-Key`, entra
en `cola_seguimiento` y sube cuando haya conexión. Una clave nueva por intento es
un identificador único, **no** una clave idempotente.

**4 · Los dos tiempos son obligatorios.** `capturado_en_dispositivo` y
`recibido_en_servidor`, siempre, con las funciones de arriba.

**5 · El indicador de seguimiento usa la llegada al servidor.** Nunca la hora
declarada por el dispositivo.

**6 · La app no inventa estados.** Consume `estado_operativo`, `estado_validacion`
y los eventos. La barra contextual **se deriva de las transiciones permitidas**, no
de lo que sea cómodo mostrar.

**7 · La guarda de arquitectura, y es la que sostiene todo lo demás:**

> **La app móvil no implementa lógica de negocio de seguimiento.** Si una regla
> pertenece al flujo de campo, vive en el backend y **viaja como dato**.

Motivo medido, dos veces en una semana: cuando dos capas «saben» la misma regla,
una queda atrás y nadie se entera hasta que alguien pierde un dato.

**8 · Los eventos transportan SEMÁNTICA, no presentación.** La API expone
`severidad` con valores controlados —`info`, `atencion`, `problema`— y la
aplicación decide cómo se ve cada uno según sus propias reglas de diseño y
accesibilidad. **No se envían colores, iconos ni referencias visuales desde el
backend.**

Quién es dueño de qué:

| Concepto | Dueño | Motivo |
|---|---|---|
| Qué ocurrió (`bloqueo_campo`, `avance_campo`) | backend | Es el hecho |
| Qué significa operacionalmente (`atencion`) | backend | Es interpretación, y la interpretación es del que sabe |
| Cómo se ve (paleta, iconografía, contraste, modo oscuro) | frontend | Es presentación, y cada plataforma tiene la suya |

Se descartó mandar `color: "warning"` e `icono: "pause"` por una razón concreta:
eso obligaría a **dos frontends a compartir el mismo diccionario visual** —qué es
«warning», qué ícono existe con ese nombre— que es el acoplamiento de `clave/id`
corrido un nivel. Y dejaría un cambio de paleta como cambio de backend.

Hay precedente propio, del 30/09/2026, en la salud del seguimiento del CRM: la
`etiqueta` viaja desde el backend porque **el texto ES el veredicto** («sin
sincronización reciente» ≠ «no reportó»), y el color vive en el frontend porque no
afirma nada sobre el mundo.

**La severidad no describe gravedad absoluta.** No es «problema = evento grave»,
sino **cuánta atención pide ese evento en su contexto**. Un bloqueo puede ser
`atencion` —es una situación pendiente, no un fallo— mientras que una validación
fallida puede ser `problema` porque pide acción ahora. Sin esta distinción, todo
termina en rojo y el rojo deja de significar algo.

## Las tres fases

### Fase 1 · Lectura

Descargar el seguimiento, mostrar la línea de tiempo, los formularios disponibles y
el último reporte. **Sin crear eventos todavía.** Termina cuando el técnico ve en
el teléfono la misma historia que el NOC ve en el CRM.

Su gate, y el punto de los tres primeros es que la app **no conozca** lo que
dibuja:

- [ ] la app renderiza **un tipo de evento que no conoce**;
- [ ] la app renderiza **campos que no conoce**, declarados por el esquema;
- [ ] una **clave extraña** en un campo no rompe la ejecución. Medido el
      30/09/2026: `validar_esquema_plantilla` exige `id` y `tipo` y valida las
      reglas contra lista blanca, pero **no rechaza claves desconocidas**, así que
      un `{"id": "presion", "tipo": "decimal", "unidad": "psi"}` pasa, se dibuja
      como decimal y `unidad` se ignora;
- [ ] **navegar sin red no crea eventos**, y al volver la señal tampoco;
- [ ] la lectura **no modifica datos**: ni una fila, ni una marca de contacto.

La prueba que de verdad decide la fase no es pintar un formulario conocido. Es
declarar en un tipo de trabajo de laboratorio un `avance_campo` con campos que
nadie escribió en Flutter —temperatura del equipo, puerto físico, un selector de
causa, un comentario obligatorio— y que la app los muestre **sin tocar una línea**.
Esa es la promesa entera: *un esquema nuevo no exige una versión móvil nueva*.

### Fase 2 · Escritura offline

Los cuatro momentos, con `cola_seguimiento`, idempotencia y reintentos. Termina
cuando un reporte escrito en modo avión aparece en el CRM al recuperar señal, **una
sola vez**.

### Fase 3 · Integración operativa

La barra contextual derivada de las transiciones, los permisos, la resolución de
bloqueos y los materiales de esa orden (`trabajos/<id>/materiales/`, que existe
desde el 29/09 y la app no usa).

## Criterios de aceptación

Comando y salida, no prosa.

| # | Fase | Evidencia | Cómo se comprueba |
|---|---|---|---|
| 1 | todas | `flutter analyze` → `No issues found!` | salida pegada |
| 2 | todas | `flutter test` verde, con las nuevas | eran 621 |
| 3 | 1 | Los cuatro formularios se dibujan con el widget existente, **sin tocarlo** | `git diff` sobre `campo_del_formulario.dart` vacío |
| 4 | 1 | Un campo que el tipo de trabajo declara y la app no conoce **se dibuja igual** | prueba con un campo inventado en el esquema |
| 5 | 2 | Un reporte en modo avión entra **una sola vez** al recuperar señal | prueba de la cola con la misma clave dos veces → un solo `EventoTrabajo` |
| 6 | 2 | Los dos tiempos llegan al servidor y **no coinciden** | `capturado_en_dispositivo` ≠ `recibido_en_servidor` |
| 7 | 2 | Un reporte capturado hace 50 min y recibido ahora deja el trabajo **al día** | la decisión de arriba, afirmada donde se puede romper |
| 8 | 3 | La barra no ofrece una acción que la máquina niega | prueba sobre el mapa de transiciones, no sobre la pantalla |
| 9 | todas | **Una prueba que atraviesa la cadena real** — app → API → servicio → base | regla de `CLAUDE.md` §6; es la que habría cazado los dos defectos de esta semana |

## Restricciones

- **NO push a `fix/integracion-wisphub`** sin decir la palabra deploy.
- **No tocar `campo_del_formulario.dart`** salvo que la medición demuestre que hace
  falta: es el archivo que ya se desincronizó una vez.
- **No duplicar inventario en la app.** Las 3.290 líneas que hay se reusan.
- No reabrir las once decisiones de
  [seguimiento-campo-por-ticket.md](seguimiento-campo-por-ticket.md).

## Qué NO hacer

- **No implementar reglas de seguimiento en Flutter.** Motivo: decisión 7.
- **No marcar vencido por la hora del dispositivo.** Motivo: la decisión de este
  objetivo.
- **No agregar el heartbeat.** Sigue siendo su propio objetivo: cambia batería,
  consumo y trabajo en segundo plano. Y encenderlo a medias rompería la regla que
  hoy funciona: *si no sé, no afirmo*.
- **No construir el copiloto todavía.** Primero se capturan los hechos; después se
  interpretan. Una IA que recomienda antes de que existan los datos recomienda
  sobre nada.

## Deuda que este objetivo destapa y no resuelve

**Una clave no soportada en un esquema se pierde en silencio.** Hoy
`{"id": "nivel", "tipo": "decimal", "unidad": "dBm"}` se dibuja bien y `unidad` se
descarta sin que nadie avise. Es tolerante para producción y **mudo para quien
configuró**.

No se arregla en Flutter, y no se arregla durante la ejecución: **el técnico no
tiene que enterarse de que alguien configuró mal un esquema**, y menos arriba de un
poste. El lugar correcto es una advertencia **al publicar** un `WorkTypeVersion`:

    Campo "nivel_optico": la propiedad "unidad" no está soportada por el
    renderizador actual.

Advertencia, no bloqueo: un esquema con una clave de más funciona, y negarse a
publicarlo sería peor que ignorarla. Queda anotado acá y **no entra en este
objetivo**.

## Bloqueos

| Qué | Bloquea | Quién decide |
|---|---|---|
| La app integrada (`integracion/app-de-campo`) no está desplegada | que esto llegue a un técnico real | producto |
| El trabajo sin commitear de `C:/wisphub/_wt_campo` (refrescar la ficha del cliente) | nada de este objetivo, pero conviene resolverlo antes de tocar `campo/` | su autor |

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 30/09/2026 | Medido lo que ya existe (formulario dinámico compatible, idempotencia en la cola, 3.290 líneas de materiales). Cerrada la decisión del tiempo offline y las siete invariantes | Fase 1 | — |
