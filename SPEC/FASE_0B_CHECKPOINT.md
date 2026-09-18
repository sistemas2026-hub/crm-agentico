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
```

Nada de esto está pusheado.

## Estado

```
0B.0  Guarda de ordenar()       ✅ cerrado   0a809d0
0B.1  QueueTabs + QueueSearch   ← el próximo
0B.2  QueueFilters              pendiente
0B.3  QueueEmptyState           pendiente
0B.4  ConversationRow           pendiente — auditoría previa OBLIGATORIA
0B.5  ConversationList          pendiente
```

`+layout.svelte`: 1193 → **1093 líneas**.

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

**No alcanza con mirar el delta de warnings.** Y ojo con el efecto secundario: cuando `.cuando` viaje
a `ConversationRow`, la interpolación se va con él. El layout **recupera** la vista y aparecerán
warnings de CSS muerto preexistente — eso **no será una regresión** —, mientras el componente que la
reciba hereda la ceguera.

**`.activa` significa dos cosas:** `.fila.activa` es la conversación seleccionada; `<span
class="activa">` es el punto de actividad reciente. Mismo nombre, dos propósitos, y viajan juntos.

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
| `ordenElegido` | se escribe en dos sitios y **no se lee en ninguno**. No eliminar, no reinterpretar |
| `tramoEspera` | el texto de la fila muestra `esperando_desde` (B3.5) pero el **color** sale de `escalada_en ?? actualizado_en`. Pueden discrepar. Preexistente |
| `.marca` · `.marca::before` | CSS muerto, invisible para `pnpm check` por lo de arriba |
| `.activa` | dos significados |
| `quien` · `esTelefono` · `esUuid` | duplicados con `ConversationHeader` desde 0A.2 |

Los helpers son el caso tentador: 0B.4 los va a necesitar y unificarlos en `formato.js` parecería
natural. **No se hace.** Es otro refactor transversal justo mientras se desarma la cola, y durante la
Fase 0 preferimos una duplicación conocida a un diff más ancho.

## Baseline de regresión

| Chequeo | Valor esperado |
|---|---|
| `pnpm check` | 2 errores, ambos en `(no-layout)/org/`; **0 en `conversaciones/`** |
| warnings | **24** |
| vitest | 17 failed \| 9 passed (26) · **63 failed** \| 298 passed (361) |
| guardas 0B.0 | 20/20 |
| guardas D29 | 17/17 |

Lo que se compara es el número de **fallos: 63**, y los mismos 17 archivos. Los pasados suben al
agregar guardas y eso es lo esperado.

**Mutaciones corridas en 0B.0**, las dos detectadas y **revertidas**:

```
peso() gana sobre porBanda()        →  12 de 20 fallan
porBanda deja de comparar bandas    →  10 de 20 fallan
```

**Diferencia visual:** *no detectada* mediante equivalencia de marcado/CSS y chequeos estáticos;
comparación por píxel no ejecutada.

## Qué se queda en el layout, pase lo que pase

Los dos `$effect`, `visibles` y toda la cadena de filtrado, el import de `ordenar`, `.mesa`,
`.columna`, el media query, y el `{#key abierta}`.

Cuando 0B cierre, se termina la preparación estructural y **la Fase 1 empieza a cambiar visualmente
la Bandeja**. Hasta entonces: nada de Tailwind, tokens, colores, badges, textos ni estados nuevos.
