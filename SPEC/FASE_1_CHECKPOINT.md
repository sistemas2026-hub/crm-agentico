# Fase 1 — checkpoint visual

Aplicar el diseño congelado en [`BANDEJA_STITCH_REFERENCIAS.md`](BANDEJA_STITCH_REFERENCIAS.md) a la
Bandeja. **Esta fase sí cambia píxeles** — es lo primero que se ve después de toda la Fase 0.

La Fase 0 cerró la estructura y está en [`FASE_0A_CHECKPOINT.md`](FASE_0A_CHECKPOINT.md) y
[`FASE_0B_CHECKPOINT.md`](FASE_0B_CHECKPOINT.md); esos documentos ya no se editan.

```
Stitch manda visualmente.  Dexter manda funcionalmente.
```

Cuando el diseño y el contrato se contradigan, **gana el contrato**. Y si Stitch muestra un dato que
Dexter no tiene, **no se inventa**.

## Base

```
3545ccd  cierre de la Fase 0
cdeb69e  1.1 — foundation visual
ade3bdf  checkpoint Fase 1
9875e34  1.2 — cola Stitch
8910a88  checkpoint con 1.2
4a701cd  1.3A — D30, el hilo proyecta origen y autor
```

Nada de esto está pusheado.

## Estado

```
1.1  Foundation visual        ✅ cerrada   cdeb69e
1.2  Cola Stitch              ✅ cerrada   9875e34
1.3A D30 · read-side          ✅ cerrada   4a701cd
1.3B Thread / autores         ← el próximo, ya desbloqueado
1.4  Header · Handoff · Composer   pendiente
1.5  Case + Tools             pendiente
1.6  Activity                 pendiente
1.7  Customer                 pendiente
1.8  Network                  pendiente
1.9  Branding                 pendiente
```

## El scope: `.bandeja`

```
lib/conversaciones/estilos/bandeja.css   →  importado en conversaciones/+layout.svelte
<div class="mesa bandeja">               →  el único consumidor
```

`.mesa` ya envolvía las tres columnas **y** el `{@render children()}` de la conversación abierta, así
que cubre la Bandeja entera **sin agregar un nodo al DOM**. Es el mismo patrón que `v2.css` usa con
`.v2-root`, un nivel más adentro.

```
selectores de bandeja.css fuera de .bandeja   0
consumidores de .bandeja                      1
```

**`PageHeader` queda fuera de la frontera, a propósito:** está sobre la mesa, es cromo del CRM, y su
rediseño es de una fase posterior.

## Los tokens

```
superficies   --bandeja-canvas #f8fafc · --bandeja-superficie #ffffff
              --bandeja-superficie-suave #f1f5f9
líneas        --bandeja-borde #e2e8f0 · --bandeja-borde-fuerte #cbd5e1
texto         --bandeja-texto #0f172a · --bandeja-texto-2 #64748b
              --bandeja-texto-3 #94a3b8
quién actúa   --bandeja-ia #7c3aed · --bandeja-humano #2563eb · --bandeja-navy #1e3a8a
estados       --bandeja-ok #059669 · --bandeja-aviso #92400e
              --bandeja-error #dc2626 · --bandeja-nota #92400e
fondos        --bandeja-ia-fondo #f5f3ff · --bandeja-ia-borde #ddd6fe
              --bandeja-humano-fondo #eff6ff · --bandeja-humano-borde #bfdbfe
              --bandeja-aviso-fondo #fffbeb · --bandeja-aviso-borde #fde68a
              --bandeja-error-fondo #fef2f2 · --bandeja-error-borde #fecaca
              --bandeja-nota-fondo #fef3c7
forma         --bandeja-radio-sm 4px · --bandeja-radio 6px · --bandeja-esp 4px
tipografía    --bandeja-sans (Geist) · --bandeja-mono (JetBrains Mono)
```

**Un sistema chico y suficiente.** No agregar tokens antes de necesitarlos: ochenta tokens sin
consumidor son ochenta decisiones que nadie tomó mirando una pantalla.

**Los valores salen del `tailwind.config` del HTML canónico**, leído en 1.2. En 1.1 los semánticos se
eligieron «por familia Tailwind» porque la fuente no era accesible todavía, y uno salió mal — ver la
corrección abajo. Radios de 4 y 6 px **sin sombras**: lo que separa es el borde, la superficie y el
espacio.

## IA y humano

```
IA      → violeta  #7C3AED
humano  → azul     #2563EB
```

**El color no puede ser la única señal.** Un 8% de la gente no distingue esos dos tonos, y un punto
de color sin palabra no dice *qué* pasó. Los componentes que los consuman deben sumar rótulo, texto o
iconografía. En 1.1 sólo quedaron definidos; los consumidores llegan en 1.3 y siguientes.

## 1.2 — la cola

### `get_screen` volvió a funcionar

El SPEC de Stitch decía que fallaba con «invalid argument». **En esta sesión respondió**, y las seis
referencias de cola se leyeron directamente del HTML canónico:

```
AI Handling            1714196c413f403f9aa69f3145d0c50a
Human Assigned to Me   c427b43a84534a489891f111217439a4
Other operator         a845526e367544578d2991da3ee24df9
Legacy                 64cfb00cd593478a87a0408e5465f04c
Customer replied       23bdda329b764e56b0f80aeb7edbc3c4
Queue States           9b5e969b91ca4558b28c615b52a5e410
```

Esa nota del SPEC describía **una limitación observada entonces, que ya no es cierta**. Tampoco
asumir que va a funcionar siempre: si vuelve a fallar, se reporta y no se infiere.

**Eso corrigió un token de 1.1**, porque el `tailwind.config` estaba en el HTML:

```
--bandeja-aviso   #d97706  →  #92400E
```

**No reabre 1.1**: la fuente canónica no estaba disponible durante esa fase. Se incorporaron además
`aiLight #F5F3FF`, `aiBorder #DDD6FE` y `amberBg #FEF3C7`, más los pares de fondo y filete de error y
humano.

### El mapeo banda → distintivo

```
1 cliente_espera       Cliente respondió    rojo
2 sin_asignar          Sin asignar          ámbar
3 revisar_evaluacion   Falta revisar        gris
4 interno_pendiente    Pendiente interno    ámbar
5 en_curso             En atención          azul
6 legado               Legado · revisar     gris
sin banda + ia         La atiende la IA     violeta
```

**La fila no calcula nada**: toma `c.banda_nombre` y le pone palabras y color. Cero score, cero
reorden, cero `.sort()`.

**Valor de banda desconocido → fallback neutro**: `BANDAS[c.banda_nombre]` cae en `undefined` y no se
dibuja distintivo. Nunca etiquetar con uno de los seis conocidos algo que el motor no dijo.

El distintivo violeta **siempre lleva su texto**. Ningún estado se comunica sólo por color.

### El dueño

```
c.asignada_a  ←  asignada_a_nombre  ←  la asignación durable de Dexter
```

**Nunca el `assignee_id` del CRM** (D28). Tres casos:

```
sin asignar (banda 2)      «Sin asignar», ámbar
asignada                   el nombre durable, azul con punto
legada sin asignación      «Sin dueño en Dexter», apagado
```

El tercero equivale al `[NO DEXTER OWNER]` del diseño, y decirlo con todas las letras es parte de G8.

**Su condición real es `!c.asignada_a && c.es_legado`** — la rama es el `else` de `asignada_a`. Está
escrito en el marcado: si alguien reordena las ramas, una legada **con** dueño diría «sin dueño», y
sería una afirmación falsa en silencio.

### Lo que el diseño muestra y Dexter no implementó

| | por qué |
|---|---|
| `Plan 500M · Belgrano` | no está en la proyección de cola; el SPEC lo marca «read live, not stored» |
| `Owner: Ana P. **(you)**` | **gap real.** El dato existe en `locals.user` y `[id]/+page.server.js` ya lo expone como `yo`, pero `conversaciones/+layout.server.js` **no lo proyecta a la cola**. Implementarlo pide tocar el `load`, fuera del alcance de 1.2 |
| `Show all` · `Clear search` · `Reset filters` | escribirían en los filtros del layout: comportamiento nuevo, no pintura |
| panel offline / retry | la cola no detecta offline. No hay dato |

El `(you)` **queda como gap para una fase posterior**, no como olvido. Es un cambio chico en el
`load`, pero es una decisión de alcance, no de implementación.

Y siguen prohibidos los mocks: AI Confidence, ids de diagnóstico, SLA, telemetría.

### Estado del puente tras 1.2

```
ConversationList    v2:  0    bandeja:  1
QueueFilters        v2:  0    bandeja: 14
QueueSearch         v2:  0    bandeja:  7
QueueTabs           v2:  1    bandeja:  6
ConversationRow     v2: 17    bandeja: 28
QueueEmptyState     v2:  0    bandeja:  0
```

**El puente sigue en pie.** Las 17 de `ConversationRow` son los semánticos `ember/clay/rust/moss`, y
se migran mirando cada consumidor — no por parecido de color.


## 1.3A — D30, el hilo no sabía quién había escrito

La auditoría previa de 1.3 encontró un bloqueo **antes de tocar un píxel**, y parar fue lo correcto.

### La causa

`mensajes_de()` —la única función que sirve el hilo a la pantalla— devolvía `rol` pero **no `origen`
ni `autor_nombre`**, aunque las dos columnas existen y son durables desde B2.

`rol` no alcanza, porque el contrato admite tres orígenes bajo el mismo:

```
assistant  →  {ia, sistema, humano}
```

Así que **una respuesta escrita por una persona llegaba indistinguible de una de la IA**, y
`burbujaClase()` —que clasifica sólo por `rol`— las dibujaba iguales. Las filas históricas, también.

La interfaz venía afirmando «esto lo dijo Dexter» sobre mensajes que no sabía quién había escrito.

### La matriz durable

```
rol=user       origen=cliente   →  Cliente
rol=assistant  origen=ia        →  Dexter IA
rol=assistant  origen=humano    →  Humano, con autor_nombre cuando exista
rol=assistant  origen=sistema   →  Sistema
rol=nota       origen=humano    →  Nota interna, con autor_nombre
               origen=NULL      →  histórico sin atribución verificable
```

**`origen` NULL no se rellena**: ni por rol, ni por contenido, ni por quién controla hoy la
conversación. Son las filas anteriores al registro de origen, y afirmar quién escribió algo que no
sabemos es peor que no decirlo.

### El cambio y la cadena

Una línea de SQL: `m.origen, m.autor_nombre`. **Sin migración, sin backfill, sin escritura.**

```
mensajes_de() → dict(f) → jsonify(resultado) → +page.server.js → data.mensajes → MessageThread
```

Todas las capas posteriores son **pass-through**: ninguna elimina, renombra ni normaliza. Por eso dos
columnas bastaron y no hizo falta tocar ningún loader.

### Las guardas, y lo que cada una puede

`tests/test_origen_en_el_hilo.py` — **18/18, sin base.** Sustituye `db.sesion` por un doble que
devuelve filas preparadas.

Cubre los cinco orígenes, el NULL histórico, que **dos filas con el mismo `rol` queden distinguidas
por su origen**, y que `autor_nombre` ausente no rompa nada.

**Limitación honesta del harness: el doble no ejecuta expresiones SQL.** Por eso hay dos clases de
aserción, y **ninguna demuestra lo de la otra**:

```
sobre las filas     el NULL llega como None y el dato viaja
sobre el SELECT     no hay coalesce ni case/when sobre m.origen
```

Se vio en las mutaciones:

```
coalesce(m.origen,'ia')  →  la atrapó la ESTRUCTURAL; la comportamental siguió
                            pasando, porque el doble no evalúa el coalesce
quitar m.autor_nombre    →  la atrapó la del SELECT
```

**Esto no es una prueba de integración contra PostgreSQL.** Lo que necesita un motor de verdad —el
CHECK de la columna— ya vive en `tests/test_origen_mensajes_base.py`.

### Las diferencias, con precisión

```
read-side   la respuesta de mensajes incorpora dos campos durables
escritura   ninguna
visual      ninguna todavía: el dato llega y nadie lo lee aún
```

**No decir «diferencias funcionales: ninguna»**: el contrato de la API sí se enriqueció.

`autor_nombre` viaja sólo en la respuesta autenticada que la UI ya consume. **No se agregó a logs,
trazas, excepciones ni telemetría** (D19/D20/D23).


## El puente `--v2-*` — transitorio, y con un orden para retirarlo

La Bandeja consume hoy **~190 usos de `--v2-*`** en ocho componentes. Como las custom properties
heredan, redefinirlos dentro de `.bandeja` los cambia para todo el subárbol **sin tocar un solo
componente**:

| | antes | después |
|---|---|---|
| `--v2-paper` | `#fafaf9` | `#f8fafc` |
| `--v2-card` | `#ffffff` | `#ffffff` |
| `--v2-ink` | `#1c1917` | `#0f172a` |
| `--v2-slate` | `#78716c` | `#64748b` |
| `--v2-line` | `#e7e5e4` | `#e2e8f0` |
| `--v2-line-soft` | `#f5f5f4` | `#f1f5f9` |
| `--v2-hover` | `rgba(28,25,23,.025)` | `rgba(15,23,42,.03)` |
| `--v2-sans` | Inter | **Geist**, Inter, … |

**Esto es un PUENTE DE COMPATIBILIDAD, no arquitectura.** Existe para que los componentes que ya
estaban adopten la foundation sin una migración masiva en un solo diff.

**El orden para desarmarlo, que no se puede invertir:**

```
1.  cada fase visual migra SUS consumidores a --bandeja-*
2.  después se comprueba que no quede ninguna referencia
3.  recién entonces se evalúa retirar el puente
```

**No retirar los alias antes del paso 2.** «Ya tenemos los tokens nuevos, saco los viejos» deja sin
color a todo componente que todavía no se migró, y `pnpm check` no lo avisa: una variable inexistente
no es un error, simplemente no pinta.

Y **no hacer limpieza global de tokens durante las fases de rediseño**: mezclar limpieza con rediseño
vuelve el diff tan inauditable como mezclarla con componentización.

## Los cuatro semánticos que NO se remapearon

```
ember   lo que pide una acción
clay    lo que está en curso
rust    lo vencido, lo destructivo
moss    lo resuelto
```

No son superficie: son **significado**. Cambiarles el valor sin decidir antes su equivalente en el
lenguaje nuevo sería mover semántica de contrabando dentro de un cambio de pintura.

**Se resuelven en la fase de su pantalla, revisando consumidor por consumidor** — nunca de un
plumazo global.

## Tipografía

**Geist y JetBrains Mono ya se cargaban** en `app.html`, con el comentario «Geist (kept for
back-compat)». La Fase 1.1 **no agregó** dependencias, `@font-face` ni links externos. Geist es la
sans de la Bandeja; mono queda para lo que se lee como dato: números, ids, contadores.

## Modo oscuro

```
html:not(.dark) .bandeja   →  la foundation nueva
.dark                      →  la Bandeja sigue como estaba
```

**No existe referencia oscura en el diseño congelado**, y v2 sí tiene su propia paleta para `.dark`.
Inventar una traducción sería adivinar. No es deuda bloqueante: es una decisión explícita por
ausencia de referencia.

## Deuda preexistente: cinco variables fantasma

Las usa la Bandeja y **ninguna está declarada en `v2.css`** — funcionan por su fallback literal:

```
--v2-surface       #fff       CasePanel
--v2-border        #e5e5e5    CasePanel · MessageThread
--v2-tinta-suave   #5c5850    ConversationRow
--v2-hueso         #f1efe9    ConversationRow
--v2-accent        #2563eb    MessageThread
```

**No corregir ahora.** Y ojo con la última: que su fallback coincida con el azul humano de Stitch
**no la convierte en el token de «humano»**. Hay que mirar qué hace su consumidor cuando llegue su
fase.

## Las deudas de la Fase 0 siguen intactas

```
.marca · .marca::before       CSS muerto; los dos warnings del baseline
.activa                       dos significados dentro de ConversationRow
quien · esTelefono · esUuid   duplicados con ConversationHeader
.avance                       guard interior inalcanzable
tramoEspera                   el color sale de escalada_en, el texto de esperando_desde
peso() · ordenElegido         congelados
```

**La Fase 1 tampoco es una limpieza general.**

## Contratos funcionales que el rediseño no toca

```
B3.5 manda en la cola — el frontend no inventa prioridad, ni score, ni SLA.
owner de la conversación = la asignación durable de Dexter, nunca el del ticket del CRM (D28).
Mostrar una conversación legada no la adopta ni toca relevo_version (G8).
El sondeo y el ciclo de vida no se duplican.
Los recursos del compositor se sueltan al desmontar (D29).
```

Y **nada de los mocks**: ni AI Confidence, ni prioridad 87, ni SLA, ni diagnósticos, temperaturas,
voltajes, firmwares, OLT/slot/port, operadores, teléfonos o documentos inventados.

## Baseline

| Chequeo | Valor esperado |
|---|---|
| `pnpm check` | 2 errores en `(no-layout)/org/`; **0 en `conversaciones/`** |
| warnings | **26** — los dos conocidos son `.marca` y `.marca::before` en `+layout.svelte` |
| vitest | 17 failed \| 9 passed (26) · **63 failed** \| 298 passed (361) |
| guardas 0B.0 | 20/20 |
| guardas D29 | 17/17 |

**Los warnings se identifican por nombre, no por conteo.** Un tercero es una regresión hasta que se
demuestre lo contrario.

## Evidencia visual

```
referencias Stitch  →  comparadas por HTML canónico (1.2)
screenshot local    →  no obtenido
```

Renderizar la Bandeja con datos exige `PRIVATE_ASISTENTE_URL`, que apunta al motor de producción, y
**no se conecta producción para obtener evidencia estética**. No es un fallo: es una restricción
respetada.

Desde 1.2 hay algo mejor que un screenshot: **el HTML canónico se compara directamente**. Eso da los
valores exactos —tokens, tamaños, clases— en vez de un parecido a ojo, y fue lo que detectó el token
mal elegido en 1.1 y el `[NO DEXTER OWNER]` que la primera lectura no tenía.

Para 1.2 —que cambia composición, jerarquía, spacing, filas y badges— **sí hace falta evidencia
visual**, si existe una forma segura de conseguirla. Una alternativa sin tocar producción: levantar
el dev server *sin* esas variables, con lo que la Bandeja renderiza su estado de error dentro de
`.mesa.bandeja` y se ven canvas, tipografía y bordes estructurales.
