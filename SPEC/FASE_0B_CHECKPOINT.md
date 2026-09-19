# Fase 0B — checkpoint

Componentizar la **cola**: `routes/(app)/conversaciones/+layout.svelte`, **sin cambiar ni un píxel ni
una conducta**. La Fase 0A cerró la conversación y está en
[`FASE_0A_CHECKPOINT.md`](FASE_0A_CHECKPOINT.md) — ese documento no se sigue editando. El diseño
congelado está en [`BANDEJA_STITCH_REFERENCIAS.md`](BANDEJA_STITCH_REFERENCIAS.md) y **solo se
consulta para decidir dónde cortar**.

Vale la misma regla:

```
componentizar  ≠  limpiar  ≠  rediseñar  ≠  modificar funcionalidad
```

## Base

```
4ea9fc0  cierre de la Fase 0A + D29
0a809d0  0B.0 — guarda del orden operacional
256c244  checkpoint Fase 0B
dc587a3  0B.1 — QueueTabs + QueueSearch
73c2b42  checkpoint con 0B.1
76f54f9  0B.2 — QueueFilters
5e913e3  checkpoint con 0B.2
5df9c57  0B.3 — QueueEmptyState
28d2f7e  checkpoint con 0B.3
b340071  0B.4 — ConversationRow
```

Nada de esto está pusheado.

## Estado

```
0B.0  Guarda de ordenar()       ✅ cerrado   0a809d0
0B.1  QueueTabs + QueueSearch   ✅ cerrado   dc587a3
0B.2  QueueFilters              ✅ cerrado   76f54f9
0B.3  QueueEmptyState           ✅ cerrado   5df9c57
0B.4A Auditoría de Row          ✅ cerrada
0B.4B ConversationRow           ✅ cerrado   b340071
0B.5  ConversationList          ← el último
```

`+layout.svelte`: 1193 → 1093 → 949 → 813 → 790 → **395 líneas**.

```
lib/conversaciones/cola/
  ordenamiento.js         133   el orden, con su guarda (0B.0)
  ordenamiento.test.js    287
  QueueTabs.svelte        119   nav.tabs   + 8 reglas
  QueueSearch.svelte       77   label.buscar + 5 reglas
  QueueFilters.svelte     210   .controles + .motivos + 10 reglas
  QueueEmptyState.svelte   62   los tres huecos + 1 regla
  ConversationRow.svelte  478   el <a class="fila"> entero + 27 reglas
```

**478 líneas no son motivo para volver a partirlo.** El tamaño no es el criterio; la frontera sí. No
fragmentarlo antes del rediseño salvo necesidad funcional real.

### Decisiones de frontera tomadas en 0B.1

**`filtro` y `vista` no son el mismo concepto**, aunque los nombres se parezcan:

```
filtro   la pestaña seleccionada      → QueueTabs
vista    el filtro de CANAL           → QueueFilters (0B.2)
```

**`irA()` se queda íntegra en el layout.** Hace tres cosas a la vez y ése es justamente el motivo:

```js
filtro = id;
ordenElegido = false;
orden = ORDEN_POR_PESTANA[id] ?? 'actividad';
```

Ese acople es del dueño de la lista, no de una barra de botones. **No dividirla ni reinterpretarla
durante la Fase 0B.** `QueueTabs` sólo llama `onIr(t.id)`.

**`busqueda` sigue siendo estado del layout**, con `bind:`. El componente no implementa ningún
filtrado: **`visibles` sigue siendo la única autoridad**.

**Ninguno de los dos hijos tiene ciclo de vida:**

```
QueueTabs     0 fetch · 0 invalidate · 0 setInterval · 0 $effect
QueueSearch   0 fetch · 0 invalidate · 0 setInterval · 0 $effect
```

**El renombre al cruzar la frontera.** El marcado movido conservaba `onclick={() => irA(t.id)}` e
`irA` ya no existía en el componente — lo cazó `pnpm check` como error, no como warning. Es el mismo
caso que `forzarAlFinal` en 0A.1: la misma función, invocada por el nombre de su prop. **Correr el
check antes de mirar cualquier otra cosa**, porque un callback mal cableado es un error de tipos y
sale en la primera pasada.

### Decisiones de frontera tomadas en 0B.2

**`VISTAS` viaja al componente; `ORDENES` no.** No es un capricho:

```
ORDEN_POR_PESTANA = { 'por-atender': 'recomendado', … }   ← se queda en el layout
ORDENES           = [{ id: 'recomendado', … }]            ← los mismos ids
```

Si `ORDENES` viviera en `QueueFilters`, esa correspondencia quedaría repartida en dos archivos **sin
nada que la mantenga junta**: el día que alguien renombre un id, la pestaña abriría con un orden
inexistente y el `?? 'actividad'` lo taparía en silencio. Por eso se declara al lado de su mapa y
**llega como prop**. `VISTAS` sí se va: ningún otro lugar la usa.

**No mover `ORDENES` al hijo durante la Fase 0B.**

**`ordenElegido` NO está muerto — se corrige la clasificación de la auditoría previa.** El marcado lo
escribe de verdad:

```js
onchange={() => (ordenElegido = true)}
```

Significa «el orden lo eligió una persona», y es lo que hace que `irA()` no lo pise al cambiar de
pestaña. Sigue congelado igual —**no eliminar, no reinterpretar, no simplificar**— pero ya no debe
describirse como estado muerto.

**`QueueFilters` sólo modifica valores.** `motivos`, `motivosVisibles` y el `$effect` que despliega
los chips cuando el motivo activo queda escondido **se quedan en el layout**; el hijo los dibuja, no
los calcula. `visibles` sigue siendo la única autoridad y **no migra a componentes durante 0B**.

`motivoLabel` se pasa como prop en vez de duplicarse: también lo usa `.motivo-fila`, en la fila.

```
QueueFilters   0 fetch · 0 invalidate · 0 setInterval · 0 $effect · 0 porBanda · 0 peso
```

### Decisiones de frontera tomadas en 0B.3

**El layout decide la variante; el componente la presenta.** Las tres condiciones siguen
literalmente en `+layout.svelte`:

```
data.error
conversaciones.length === 0
visibles.length === 0
```

`QueueEmptyState` **no inspecciona ninguna colección** ni decide nada de la cola.

**Los tres estados no se fusionan.** Se parecen lo suficiente como para que alguien lo intente:

```
error              algo se rompió; quien atiende no sabe qué hay
sin-datos          la bandeja está vacía de verdad
sin-coincidencias  hay conversaciones, pero los filtros las escondieron
```

Sólo la tercera tiene como salida «cambiá el filtro», y por eso es la única con texto distinto según
haya o no una búsqueda escrita. **No hay estado de carga, y no hay que inventarlo:** la cola llega ya
cargada desde el `load`.

**`busqueda` se pasa únicamente para resolver ese texto.** No implica mover filtrado al componente.

**`.hueco` viajó completo** — sus tres consumidores estaban en el bloque. **`.lista` se queda en el
layout**: envuelve también el `{#each}` de las filas, así que no es del estado vacío aunque lo
contenga.

Cuidado repetible: la palabra `hueco` aparece dos veces más en el layout, **dentro de comentarios**
de `a.fila`. Un `grep` crudo las cuenta como consumidores.

**Los imports que salieron son consecuencia mecánica, no limpieza:** `EmptyState`, `TriangleAlert`,
`MessagesSquare` y `Search` quedaron sin consumidores al mover el bloque. **`Search` es el caso
ilustrativo** — en 0B.1 se quedó en el layout *precisamente* porque lo usaba este `EmptyState`; al
irse el bloque, dejó de usarlo nadie. La regla `.hueco` salió por lo mismo.

Ahí es donde la tercera guarda hizo trabajo real: `pnpm check` no avisa de imports ni constantes que
se quedan sin uso.

### Decisiones de frontera tomadas en 0B.4

**La interfaz, y por qué `c` va entero:**

```svelte
<ConversationRow {c} {abierta} {ahora} {tramoEspera} {motivoLabel} />
```

La fila consume quince campos de la conversación. Convertirlos en quince props sería inventar una API
en una fase que promete equivalencia, y cada campo nuevo obligaría a tocar dos archivos. **No
desarmar `c` durante la Fase 0.**

**El reloj sigue siendo del layout** — un solo `setInterval(20 s)`. `ConversationRow` no crea timers.

**`ahora` cruza la frontera, igual que `ultimoVisto` en 0A.1**, y con el mismo peligro: si la prop no
quedara conectada reactivamente, el punto «Activa» se congelaría **en silencio** — no es un error de
tipos ni un warning de CSS, y ninguna guarda lo vería. Se verificó **compilando el componente**:

```js
const estaActiva = (c) => … ahora() - new Date(…) < …
var d_10 = $.derived(() => estaActiva($$props.c));
$.if(node_12, …)
```

`ahora()` **con paréntesis** es un getter de señal: la lectura se rastrea, y la llamada vive dentro de
un `$.derived` envuelto en `$.if`. Al avanzar el reloj, el bloque se reevalúa.

**Helpers que viajaron** (exclusivos de la fila): `quien`, `esTelefono`, `esUuid`, `estaActiva`,
`MINUTOS_ACTIVA`, `canalLabel`, `CANAL_LABEL`, `etiquetaLabel`, `AUTOR`.

**Helpers que se quedaron**, porque tienen consumidores fuera: `tramoEspera` (el contador de críticas
del encabezado) y `motivoLabel` (también `QueueFilters`). Van como props, sin duplicar.
`pendiente` y `resuelta` se importan de `estado.js` en los dos lados.

La duplicación de `quien` / `esTelefono` / `esUuid` con `ConversationHeader` **sigue sin resolverse a
propósito**.

**Cinco imports quedaron huérfanos y salieron:** `Avatar`, `Pill`, `shortAge`, `Phone`, `User`. Otra
vez la tercera guarda: `pnpm check` no los reporta, y `Pill` daba dos hits de los cuales uno era un
comentario de CSS.

**La fila no decide nada:**

```
ConversationRow   0 fetch · 0 invalidate · 0 setInterval · 0 setTimeout
                  0 $effect · 0 onMount · 0 onDestroy · 0 goto · 0 onclick
```

No muestra dueño (D28), `es_legado` sólo pinta una clase y no adopta nada (G8), `banda` /
`esperando_desde` / `motivo_cola` se representan pero no se recalculan (B3.5), y `canal_operativo`
no entra: sigue siendo criterio de `visibles`.

**27 reglas de CSS**, con aserción explícita en el script — aborta si no son exactamente 27, si
alguna trae selectores ajenos o si una media query toca la fila.

Las **cinco reglas de `.activa`** viajaron juntas y conservan sus dos significados:

```
.fila.activa · .fila.pide.activa · .fila.activa .ident   → la conversación abierta
.activa · .activa::before                                 → el punto de «se movió recién»
```

El scope las mantiene separadas del resto, pero **la colisión de nombres es real y ahora convive en
un solo archivo**. No renombrar durante 0B.

`.motivo-fila` está en `ConversationRow`; `.motivo`, en `QueueFilters`. Las tres clases
`espera-fresco` / `espera-viejo` / `espera-critico` son **las tres alcanzables** y siguen asociadas a
`espera-{tramoEspera(c)}`.

**La redundancia de `.avance` se movió tal cual**: hay un guard exterior `{#if c.resumen}` y otro
interior `{#if (c.resumen ?? '').trim()}` cuya rama es inalcanzable. Preexistente, **no corregida a
propósito**.

## Lo que la auditoría previa encontró, y hay que tener presente

**La cola no hace un solo `fetch`.** Todo entra por `+layout.server.js`, que declara
`depends('app:conversaciones')`. Es de solo lectura: no hay ninguna autoridad en el cliente que se
pueda mudar por accidente. Eso hace 0B estructuralmente más simple que 0A — **el único riesgo
funcional real es el orden**, y por eso 0B.0 fue primero.

**Cero selectores agrupados** en el CSS del layout. La trampa que produjo tres regresiones en 0A.4
no existe acá. La de abajo, sí.

## B3.5 / D18 — la autoridad del orden

```
porBanda()   autoridad SIEMPRE que exista proyección
peso()       respaldo histórico, solo con el comportamiento actual
```

**No invertir ese orden.** Basta con que **una** de las dos filas traiga `banda` numérica para que
mande `porBanda` — ésa es la condición real (`typeof a.banda === 'number' || typeof b.banda`), no
que la traigan las dos.

La prueba canónica, en `lib/conversaciones/cola/ordenamiento.test.js`:

```
45 legado (banda 6, esperando entre 30 y 75 días)
 + 1 escalada moderna sin asignar (banda 2, de hace un rato)
 → la moderna primera
```

Está mezclada a propósito en medio de la lista de entrada: si saliera bien por el orden en que
entra, la prueba no probaría nada.

**Orden dentro de una banda:** `esperando_desde` más antiguo primero; sin fecha, al final de **su
propia banda** y no de la lista; dos sin fecha empatan en 0 y conservan el orden de entrada.

**`peso()` sigue vivo a propósito.** Es el respaldo para una respuesta de un motor sin proyección
durante un despliegue. **No eliminarlo, no deprecarlo, no cambiar sus valores durante la Fase 0B.**

**Los tests prueban el código que ordena, no una copia.** `+layout.svelte` importa esas mismas
funciones. Si alguna vez se reimplementa el orden en un componente, la guarda deja de proteger nada.

## CSS — la detección de muerto NO funciona en este archivo

**El hallazgo más importante de la auditoría previa.** Una sola clase interpolada en el marcado:

```
class="cuando v2-num espera-{tramoEspera(c)}"
```

apaga el análisis de selectores sin usar de Svelte **para todo el archivo**. Comprobado con dos
sondas, no deducido:

```
sonda 1  una clase inventada que nadie usa          →  0 warnings
sonda 2  lo mismo, pero neutralizando la interpolación →  5 warnings aparecen
         .clase-inventada · .marca · .marca::before · .cuando.espera-viejo · .cuando.espera-critico
```

Por eso `.marca` lleva quién sabe cuánto muerta sin un solo aviso.

**Consecuencia para cada corte de 0B:** la guarda que atrapó las tres regresiones de 0A.4 **no está
disponible**. El control tiene que ser un inventario bidireccional explícito:

```
por cada clase del marcado   →  localizar su regla efectiva
por cada regla movida        →  comprobar qué consumidores tenía
```

**Resultado en 0B.1, 0B.2 y 0B.3**, que es cómo se ve un corte sano:

```
clases movidas sin regla        0
reglas movidas sin consumidor   0
reglas compartidas              0
media queries compartidas       0
```

Se verifica **en los dos momentos**: antes de mover, con el script abortando por aserción si aparece
cualquiera de los tres casos; y después, por archivo. No hizo falta duplicar ninguna regla, a
diferencia de `.aviso` en 0A.3.

**`.motivo` en 0B.2 — por qué el inventario va por selector y nunca por prefijo:**

```
.motivo       la comparten «Solo escaladas» (.controles) y los chips (.motivos)
              → los dos dentro del bloque, así que la regla viajó entera

.motivo-fila  OTRA clase, vive en a.fila, se queda
```

Un inventario por prefijo se habría llevado `.motivo-fila` con las demás — es el mismo fallo de
`.proceso, .docs` en 0A.4. El patrón que hay que usar es `\.motivo(?![\w-])`.

**No alcanza con mirar el delta de warnings.**

**Lo anticipado ocurrió, y exactamente como se previó.** En 0B.4 la interpolación viajó a
`ConversationRow`, el layout **recuperó** la detección, y aparecieron dos warnings:

```
24  →  26
+layout.svelte  .marca
+layout.svelte  .marca::before
```

**Ninguno más.** Verificado por archivo: el layout pasó de 0 a 2, `ConversationRow` no aparece en la
lista, y ningún otro archivo cambió su conteo. Son CSS muerto preexistente que el punto ciego
tapaba — **no una regresión**. No se limpian.

**El punto ciego ahora lo hereda `ConversationRow`:** allá `svelte-check` tampoco detecta CSS muerto,
porque la interpolación vive en ese archivo. El inventario bidireccional sigue siendo obligatorio
dentro de ese componente, y la ausencia de warnings ahí **no prueba nada**.

**`.activa` significa dos cosas:** `.fila.activa` es la conversación seleccionada; `<span
class="activa">` es el punto de actividad reciente. Mismo nombre, dos propósitos, y viajan juntos.

## Los dos huecos del tooling, y la auditoría mínima que salen de ellos

`pnpm check` tiene **dos puntos ciegos** que en este archivo importan:

```
1.  CSS muerto con una clase interpolada en el marcado   → no lo ve (ver arriba)
2.  constantes JS sin referencias                        → tampoco lo ve
```

El segundo apareció en 0B.2: el primer intento dejó `VISTAS` y `ORDENES` **duplicadas** —copiadas al
componente y todavía declaradas en el layout, ya sin consumidores— y el check pasó limpio. Se
encontró contando referencias a mano.

**La auditoría mínima de cada corte de 0B es, entonces, tres cosas y no una:**

```
1.  pnpm check                          errores de tipos y props mal cruzadas
2.  inventario CSS bidireccional        clase → regla · regla → consumidores
3.  referencias de cada símbolo movido  ¿quedó una copia huérfana del otro lado?
```

Ninguna de las tres cubre a las otras dos. El check es el más rápido y **se corre primero**, porque
un callback mal cableado sale ahí en la primera pasada; las otras dos no las hace ninguna
herramienta.

## Polling — los dos ciclos se quedan en el layout

```
setInterval(8 s)  + visibilitychange + focus  →  invalidate('app:conversaciones')
setInterval(20 s)                             →  'ahora', para que «Activa» se apague solo
```

Los dos con cleanup correcto. El de 8 s **no hace `fetch`: invalida**, y SvelteKit reejecuta el
`load`. Navegar entre conversaciones **no lo reinicia** — el `{#key abierta}` envuelve solo al hijo,
la columna nunca se remonta.

**No deben viajar a ningún componente.** Y verificar en cada corte que no aparezca una segunda
cadena: dos sondeos duplican las llamadas.

`ahora` cruza la frontera hacia la fila (`estaActiva`), igual que `ultimoVisto` en 0A.1. Es un
acoplamiento conocido a resolver explícitamente en 0B.4.

## Canales

```
c.canal_operativo   ← la decisión, la manda el motor (canales.REALES)
CANAL_LABEL         ← presentación, y nada más
```

No hay una lista de canales en el frontend, a propósito. `CANAL_LABEL` tiene dos literales para
rotular; **no puede convertirse en criterio de filtrado**. Si `canal_operativo` falta, no se esconde
nada — mejor de más que ocultar un cliente real.

Una extracción no puede hacer que los canales de prueba reaparezcan en la vista operacional.

## Responsive

Un solo breakpoint: `max-width: 1000px`. La columna pasa a 100% y **desaparece con
`.columna.hay-abierta`** cuando hay conversación abierta; el «volver» es la navegación del navegador.
`.hay-abierta` depende de `abierta`, que sale de `page.params.id`.

**Si `ConversationList` se lleva `.columna`, se lleva el responsive completo.** No aplicar todavía
los mockups responsive de Stitch.

## Deudas que NO se arreglan en la Fase 0B

| | |
|---|---|
| `ordenElegido` | **congelado, pero NO es estado muerto** — la auditoría previa lo clasificó mal y 0B.2 lo corrigió. `onchange` lo pone en `true` al elegir un orden a mano, y eso evita que `irA()` lo pise. No eliminar, no reinterpretar |
| `peso()` | el respaldo pre-D18, vivo a propósito. Ver arriba |
| `tramoEspera` | el texto de la fila muestra `esperando_desde` (B3.5) pero el **color** sale de `escalada_en ?? actualizado_en`. Pueden discrepar. Preexistente |
| `.marca` · `.marca::before` | CSS muerto. Estuvo invisible hasta 0B.4; **desde entonces son los dos warnings del baseline**. Siguen sin limpiarse |
| `.activa` | dos significados |
| `quien` · `esTelefono` · `esUuid` | duplicados con `ConversationHeader` desde 0A.2 |

Los helpers son el caso tentador: 0B.4 los va a necesitar y unificarlos en `formato.js` parecería
natural. **No se hace.** Es otro refactor transversal justo mientras se desarma la cola, y durante la
Fase 0 preferimos una duplicación conocida a un diff más ancho.

## Baseline de regresión

| Chequeo | Valor esperado |
|---|---|
| `pnpm check` | 2 errores, ambos en `(no-layout)/org/`; **0 en `conversaciones/`** |
| warnings, hasta 0B.3 | 24 |
| warnings, **desde 0B.4** | **26** — los dos nuevos son `.marca` y `.marca::before` en el layout |
| vitest | 17 failed \| 9 passed (26) · **63 failed** \| 298 passed (361) |
| guardas 0B.0 | 20/20 |
| guardas D29 | 17/17 |

Lo que se compara es el número de **fallos: 63**, y los mismos 17 archivos. Los pasados suben al
agregar guardas y eso es lo esperado.

**26 es el baseline documentado desde 0B.4**, mientras esas dos deudas sigan ahí. No convertirlo en
permiso genérico: **los warnings se identifican por nombre**. Un tercero, o cualquier otro selector
distinto de esos dos, es una regresión hasta que se demuestre lo contrario.

**Mutaciones corridas en 0B.0**, las dos detectadas y **revertidas**:

```
peso() gana sobre porBanda()        →  12 de 20 fallan
porBanda deja de comparar bandas    →  10 de 20 fallan
```

**Diferencia visual:** *no detectada* mediante equivalencia de marcado/CSS y chequeos estáticos;
comparación por píxel no ejecutada.

## Qué se queda en el layout, pase lo que pase

Los dos `$effect`, `visibles` y toda la cadena de filtrado, el import de `ordenar`, `.mesa`,
`.columna`, `.lista`, el media query, y el `{#key abierta}`.

## Partir 0B.4 en dos funcionó, y conviene recordarlo

`ConversationRow` era el único corte sensible, porque en `a.fila` confluía lo que en los cuatro
anteriores estaba separado: `ahora` cruzando la frontera, nueve helpers, la clase interpolada,
`.activa` con dos sentidos, `.motivo-fila` vecina de `.motivo`, y la navegación.

```
0B.4A   auditoría, sin mover una línea    → predijo los dos warnings, y acertó
0B.4B   extracción                        → mecánica, sin bloqueos
```

**La auditoría previa se pagó sola**: entró sabiendo cuántas reglas mover (27, con aserción), qué
helpers tenían consumidores ocultos, y exactamente qué iba a pasar con los warnings. Para 0B.5 el
corte es chico, pero el orden —mirar antes de mover— es el que quedó demostrado.

Cuando 0B cierre, se termina la preparación estructural y **la Fase 1 empieza a cambiar visualmente
la Bandeja**. Hasta entonces: nada de Tailwind, tokens, colores, badges, textos ni estados nuevos.
