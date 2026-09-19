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
```

Nada de esto está pusheado.

## Estado

```
1.1  Foundation visual        ✅ cerrada   cdeb69e
1.2  Cola Stitch              ← el próximo
1.3  Thread / autores         pendiente
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

## Los 18 tokens

```
superficies   --bandeja-canvas #f8fafc · --bandeja-superficie #ffffff
              --bandeja-superficie-suave #f1f5f9
líneas        --bandeja-borde #e2e8f0 · --bandeja-borde-fuerte #cbd5e1
texto         --bandeja-texto #0f172a · --bandeja-texto-2 #64748b
              --bandeja-texto-3 #94a3b8
quién actúa   --bandeja-ia #7c3aed · --bandeja-humano #2563eb · --bandeja-navy #1e3a8a
estados       --bandeja-ok #059669 · --bandeja-aviso #d97706
              --bandeja-error #dc2626 · --bandeja-nota #b45309
forma         --bandeja-radio-sm 4px · --bandeja-radio 6px · --bandeja-esp 4px
tipografía    --bandeja-sans (Geist) · --bandeja-mono (JetBrains Mono)
```

**Un sistema chico y suficiente.** No agregar tokens antes de necesitarlos: ochenta tokens sin
consumidor son ochenta decisiones que nadie tomó mirando una pantalla.

Los semánticos salen de la misma familia Tailwind que la paleta canónica, no elegidos a ojo. Radios
de 4 y 6 px **sin sombras**: lo que separa es el borde, la superficie y el espacio.

## IA y humano

```
IA      → violeta  #7C3AED
humano  → azul     #2563EB
```

**El color no puede ser la única señal.** Un 8% de la gente no distingue esos dos tonos, y un punto
de color sin palabra no dice *qué* pasó. Los componentes que los consuman deben sumar rótulo, texto o
iconografía. En 1.1 sólo quedaron definidos; los consumidores llegan en 1.3 y siguientes.

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
1.1  →  sin screenshot
```

Renderizar la Bandeja con datos exige `PRIVATE_ASISTENTE_URL`, que apunta al motor de producción, y
**no se conecta producción para obtener evidencia estética**. No es un fallo del corte: es una
restricción respetada.

Para 1.2 —que cambia composición, jerarquía, spacing, filas y badges— **sí hace falta evidencia
visual**, si existe una forma segura de conseguirla. Una alternativa sin tocar producción: levantar
el dev server *sin* esas variables, con lo que la Bandeja renderiza su estado de error dentro de
`.mesa.bandeja` y se ven canvas, tipografía y bordes estructurales.
