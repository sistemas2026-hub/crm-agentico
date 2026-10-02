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
- [ ] una **clave extraña** en un campo no rompe la ejecución. Medido: el
      backend no rechaza claves desconocidas y la app **lee las de presentación**
      (`unidad`, `ayuda`, `referencia`), así que
      `{"id": "presion", "tipo": "decimal", "unidad": "psi"}` se dibuja **con su
      unidad**. Lo que hay que probar es el caso contrario: una clave que nadie
      usa —`color_del_borde`— tampoco rompe nada;
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

**Construida el 02/10/2026.** `flutter analyze` → `No issues found!`,
`flutter test` → **697 pruebas en verde** (eran 621 al abrir la ficha); las 25
nuevas viven en `test/resolucion_de_bloqueo_test.dart` y
`test/materiales_de_la_orden_test.dart`, y las cuatro mutaciones que las
atacan —frontera de `requiere_noc` invertida, `que_se_hizo` vacío aceptado,
`null` tratado como «no se usó nada», cantidad cruda— se ponen en **rojo**.

Dos decisiones de esta fase:

**Quién resuelve un bloqueo desde el teléfono.** El backend deja que lo haga el
técnico asignado. La frontera que puso la app es otra: **resuelve solo cuando el
bloqueo NO requiere al NOC.** La pregunta que importa no es si *puede* sino si
*sabe qué se hizo* —`que_se_hizo` es obligatorio del otro lado y existe para
responder «¿por qué este trabajo tardó tres días?»—. Si coordinación gestionó un
permiso municipal, el técnico escribiría «ya puedo entrar», que no es qué se
hizo, y el campo quedaría inservible justo para su única pregunta. Cuando
requiere NOC la pantalla no esconde el botón en silencio: dice que lo destraba el
NOC o coordinación, porque alguien parado en la calle necesita saber qué espera.

**La resolución viaja por la MISMA cola** que un avance, con otra ruta y otro
cuerpo. Es algo que se escribió en la calle y tiene que subir: duplicar la
maquinaria de reintentos e idempotencia para un solo caso serían dos lugares
donde arreglar el mismo defecto. El orden ya estaba resuelto —la cola respeta
`created_at`—, así que una resolución nunca sube antes del bloqueo que resuelve.
Un **409** («ya no hay bloqueo abierto») cierra la fila en vez de reintentar:
alguien lo resolvió primero, y lo que el técnico quería ya ocurrió.

**Lo que NO tiene prueba automática, y hay que decirlo.** El tratamiento de
códigos de `_subirResolucion` (409 / 422 / 404) no está cubierto:
`SyncQueueService` construye su `ApiClient` como campo fijo y no se puede falsear
sin refactorizarlo —la Fase 2 tampoco cubrió su camino de subida, por lo mismo—.
Se verifica contra el backend de laboratorio, no en `flutter test`. Es
exactamente el criterio 9 de la tabla de abajo, que **sigue abierto**.

### La corrida en el emulador (02/10/2026)

El objetivo no se da por cerrado con `flutter test`: la regla de `CLAUDE.md` §6
pide una pasada por la **cadena real**, y es la que encontró lo único que las
698 pruebas no veían.

**Cómo se montó.** El backend del laboratorio servía el worktree de inventario,
que **no tiene** estos endpoints; con él la app habría ido a 404 y la pantalla
habría dicho «no disponible» —exactamente lo mismo que dice cuando no hay señal—.
Se levantó un segundo contenedor con el código de esta rama contra la **misma**
base (las 18 migraciones de `campo` ya estaban aplicadas, así que `migrate` no
tocó nada), y la app se compiló con `--dart-define=BACKEND_URL=http://10.0.2.2:8003`.

**Qué se ejecutó, en orden, y qué devolvió el servidor:**

```
GET  /trabajos/<id>/materiales/    200   100 m reservados · 37,5 m + 1 ONT usados
GET  /trabajos/<id>/seguimiento/   200   sin reportes todavía
POST /trabajos/<id>/seguimiento/   201   AVANCE  — sin INICIO previo, aceptado
POST /trabajos/<id>/seguimiento/   201   BLOQUEO — detiene el trabajo
POST /trabajos/<id>/bloqueo/resolver/  200
```

Y en la base, después:

```
estado de la orden: en_sitio
bloqueo | requiere_noc: False | detuvo: True | estado anterior: en_sitio
        | resuelto_en: True | que_se_hizo: El cliente volvio y abrio la casa
eventos: avance_campo, bloqueo_campo, bloqueo_detuvo_el_trabajo,
         bloqueo_libero_el_trabajo, bloqueo_resuelto
```

La orden volvió a `en_sitio` **porque el bloqueo lo guardó al abrirse**, no
porque nadie lo dedujera. Con eso el **criterio 9 queda cumplido**.

Tres cosas se vieron funcionando que ninguna prueba unitaria afirma del todo: el
formulario salió del **respaldo genérico** (el tipo de trabajo del laboratorio no
declara momentos) y aun así se dibujó completo; el material apareció separado en
sus bloques **sin sumarse**; y la salida del bloqueo se ofreció porque
`requiere_noc` era `false`.

**El defecto que encontró la corrida.** Se escribió un BLOQUEO, se tocó «Cerrar
intervención» **sin guardar**, y el motivo del bloqueo apareció dentro de «¿Qué
se hizo para resolverlo?», listo para mandarse como respuesta a otra pregunta.
Los dos formularios declaran un campo con el mismo `id`, así que para Flutter
eran el mismo widget y le reusó el estado. Arreglado con una `ValueKey` por
momento, con prueba que lo reproduce y verificación en negativo (quitar la clave
la pone en rojo).

**Lo que se vio y NO se tocó.** Una fila dice `1 unidades`: el texto de la unidad
sale del catálogo del tenant, y la app lo dibuja como está. Singularizarlo en
código sería que la aplicación adivine gramática española sobre un campo libre
que cada empresa escribe a su manera — por §3.3 eso es un dato de la empresa, y
se corrige en el catálogo, no acá.

## Criterios de aceptación

Comando y salida, no prosa.

| # | Fase | Evidencia | Cómo se comprueba |
|---|---|---|---|
| 1 | todas | `flutter analyze` → `No issues found!` | salida pegada |
| 2 | todas | `flutter test` verde, con las nuevas | eran 621 · **medido 697 el 02/10** |
| 3 | 1 | Los cuatro formularios se dibujan con el widget existente, **sin tocarlo** | `git diff` sobre `campo_del_formulario.dart` vacío |
| 4 | 1 | Un campo que el tipo de trabajo declara y la app no conoce **se dibuja igual** | prueba con un campo inventado en el esquema |
| 5 | 2 | Un reporte en modo avión entra **una sola vez** al recuperar señal | prueba de la cola con la misma clave dos veces → un solo `EventoTrabajo` |
| 6 | 2 | Los dos tiempos llegan al servidor y **no coinciden** | `capturado_en_dispositivo` ≠ `recibido_en_servidor` |
| 7 | 2 | Un reporte capturado hace 50 min y recibido ahora deja el trabajo **al día** | la decisión de arriba, afirmada donde se puede romper |
| 8 | 3 | La barra no ofrece una acción que la máquina niega | prueba sobre el mapa de transiciones, no sobre la pantalla |
| 9 | todas | **Una prueba que atraviesa la cadena real** — app → API → servicio → base | **CUMPLIDO 02/10/2026**: corrida en el emulador contra el backend de esta rama, con las salidas pegadas arriba. Encontró un defecto que las 698 pruebas no veían |

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

## Una deuda que se anotó mal, y se corrige acá

El 30/09 se escribió que una clave no soportada —`{"id": "nivel", "tipo":
"decimal", "unidad": "dBm"}`— **se perdía en silencio**. Medido el 01/10 sobre
`campo_del_formulario.dart`: **es falso.** `desdeEsquema` lee `campo['unidad']`
directamente, igual que `ayuda` y `referencia`, así que la app la usa y la muestra.

Y el diseño ya tenía pensado el criterio, escrito en ese archivo:

> «La referencia viaja FUERA de `reglas` a propósito: `reglas` es el vocabulario
> cerrado que valida el backend, y esto no valida nada.»

O sea que la división está hecha y es la correcta:

    reglas.*        lo que el BACKEND valida (vocabulario cerrado)
    unidad, ayuda   lo que solo sirve para PRESENTAR (claves sueltas del campo)
    referencia

Que el validador no rechace claves desconocidas **no es un descuido: es lo que
permite que la presentación evolucione sin tocar el validador.** La advertencia al
publicar que se había propuesto resolvería un problema que no existe, y encima
ensuciaría ese mecanismo.

Lo que queda, y es mucho más chico: una clave con un typo —`unidadd`— sí se pierde
sin aviso. Eso vale una advertencia al publicar algún día, pero es un error de
tipeo, no una pérdida de información declarada.

## Bloqueos

| Qué | Bloquea | Quién decide |
|---|---|---|
| La app integrada (`integracion/app-de-campo`) no está desplegada | que esto llegue a un técnico real | producto |
| El trabajo sin commitear de `C:/wisphub/_wt_campo` (refrescar la ficha del cliente) | nada de este objetivo, pero conviene resolverlo antes de tocar `campo/` | su autor |

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 30/09/2026 | Medido lo que ya existe (formulario dinámico compatible, idempotencia en la cola, 3.290 líneas de materiales). Cerrada la decisión del tiempo offline y las siete invariantes | Fase 1 | — |
