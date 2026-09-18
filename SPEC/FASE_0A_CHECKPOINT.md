# Fase 0A — checkpoint

> **Estado: ✅ CERRADA** (0A.1 … 0A.5). `[id]/+page.svelte`: **4036 → 1665 líneas**.
> Lo siguiente **no** es el rediseño: es **D29**, en su propia pista funcional. Ver el final.

Componentizar `[id]/+page.svelte` **sin cambiar ni un píxel ni una conducta**.
Cirugía estructural primero, pintura después. El diseño congelado está en
[`BANDEJA_STITCH_REFERENCIAS.md`](BANDEJA_STITCH_REFERENCIAS.md) y **solo se consulta para decidir
dónde cortar**, nunca para copiar HTML, Tailwind, colores ni textos.

## La regla

```
componentizar  ≠  limpiar  ≠  rediseñar  ≠  modificar funcionalidad
```

Las cuatro cosas son deseables y **ninguna se hace junto con otra**. Un diff que mueve código se
puede auditar leyendo qué se borró de un lado y apareció idéntico del otro; uno que además limpia y
además rediseña, no. Por eso las deudas de más abajo se anotan y se dejan quietas.

## Base

```
eb5b4bf  B3.5 / D18 cerrado
4c8113d  SPEC Stitch congelado
7a41bdc  0A.1 — MessageThread extraído
145de9c  checkpoint Fase 0A
edcfd12  0A.2 — ConversationHeader extraído
3cf03d5  checkpoint con 0A.2
aa96916  0A.3 — EscalationSummary + HandoffControls
71a8b49  checkpoint con 0A.3
0aa283e  0A.4 — los cuatro paneles de contexto
2cdcf44  checkpoint con 0A.4
8ab8bb3  micro-fix: el Cancelar de la grabación recupera .reiniciar-discreto
2ae5241  0A.5 — MessageComposer  ← cierra la Fase 0A
521f128  checkpoint final de la Fase 0A
450d4e4  D29 — el micrófono se suelta al salir de la conversación
```

Nada de esto está pusheado.

## Estado

| Bloque | Estado | Dónde está hoy |
|---|---|---|
| `MessageThread` | ✅ **0A.1 cerrado** | `lib/conversaciones/messages/MessageThread.svelte` |
| `formato.js` (helpers puros) | ✅ 0A.1 | `lib/conversaciones/formato.js` |
| `ConversationHeader` | ✅ **0A.2 cerrado** | `lib/conversaciones/conversation/ConversationHeader.svelte` |
| Polling de 5 s | ✅ sigue **único y en el padre** | `[id]/+page.svelte` |
| Autoscroll | ✅ vive en `MessageThread` | — |
| `EscalationSummary` | ✅ **0A.3 cerrado** | `lib/conversaciones/conversation/EscalationSummary.svelte` |
| `HandoffControls` | ✅ **0A.3 cerrado** | `lib/conversaciones/conversation/HandoffControls.svelte` |
| `CasePanel` · `RetentionToggle` · `TracePanel` · `DocumentationPanel` | ✅ **0A.4 cerrado** | `lib/conversaciones/context/` |
| Cáscara del contexto: `<aside>`, overlay, `contextoAbierto` | ✅ se queda en la página, a propósito | `[id]/+page.svelte` |
| `MessageComposer` (`.pie`), con el botón `Intervenir` | ✅ **0A.5 cerrado** | `lib/conversaciones/composer/MessageComposer.svelte` |
| `MediaRecorder`, cronómetro, object URLs, ventana 24 h, `intervenir()`, los 6 envíos | ✅ se quedan en la página, a propósito | `[id]/+page.svelte` |

`[id]/+page.svelte`: 4036 → 3638 → 3514 → 3102 → 2467 → **1665 líneas**.

### Arquitectura final de la Fase 0A

```
routes/(app)/conversaciones/[id]/+page.svelte   1665   estado · red · lifecycle · autoridad

lib/conversaciones/
  formato.js                                       72   helpers puros
  grabacion.js                                    213   el micrófono (D29, no es un componente)
  messages/MessageThread.svelte                   395   + el scroll del hilo
  conversation/ConversationHeader.svelte          170
  conversation/EscalationSummary.svelte           180
  conversation/HandoffControls.svelte             347
  composer/MessageComposer.svelte                 963
  context/CasePanel.svelte                        207
  context/RetentionToggle.svelte                  120
  context/TracePanel.svelte                       305
  context/DocumentationPanel.svelte               189
```

Los rangos son orientativos: se corren en cada extracción. Confirmarlos contra el marcado antes de
cortar, nunca contra esta tabla.

**Todos los componentes extraídos son presentacionales.** Reciben props y avisan por callbacks; el
estado, los fetches, la navegación y las mutaciones se quedan en `[id]/+page.svelte`. La única
excepción deliberada es el scroll del hilo, que vive donde vive el elemento que scrollea (ver el
contrato de `forzarAlFinal` más abajo).

No convertir un componente en controlador «para que sea autónomo»: la página es la que sabe de rutas
y de red, y es donde el próximo que lea el código va a buscar esa lógica.

## Orden acordado

```
0A.1 MessageThread   ✅ cerrado   7a41bdc
0A.2 Header          ✅ cerrado   edcfd12
0A.3 Escalada+relevo ✅ cerrado   aa96916
0A.4 Contexto        ✅ cerrado   0aa283e
0A.5 Compositor      ✅ cerrado   2ae5241   (se llevó el botón Intervenir)

FASE 0A            ✅ CERRADA
```

Lo que sigue, en este orden y no en otro:

```
D29        ✅ cerrado   450d4e4
FASE 0B    ← el próximo: componentizar la cola, +layout.svelte, ~1193 líneas
FASE 1     ← recién ahí, el rediseño visual con los tokens de Stitch
```

**D29 fue antes de 0B**: dejar el micrófono potencialmente abierto al abandonar una conversación
pesaba más que seguir componentizando la cola.

### La regla de autoridad, que vale para todo lo que queda

**Los botones pueden mudarse; ninguna decisión de B3.3b, B3.4 o B3.5 puede mudarse con ellos.** La
verdad la fija `control_efectivo()` en el motor, la asignación durable y la proyección de bandas — no
la pantalla. Si al cortar aparece la tentación de recalcular en el componente quién controla la
conversación o si alguien puede tomarla, **la frontera está mal trazada**.

`HandoffControls`, cerrado en 0A.3, es el ejemplo de cómo queda: **no hace `fetch`, no calcula
control, ni dueño, ni permiso ADMIN, ni legado, ni banda**. Todo eso llega como props ya resueltas.

Se conservan sin tocar: que un 409 relea el dueño en vez de pisarlo —y que eso siga resuelto en la
página—, que solo un ADMIN vea Reasignar, que el motivo sea obligatorio, que Soltar sea solo del
dueño, y que la pantalla espere la confirmación del backend antes de cambiar la propiedad.

**D28:** el dueño que se muestra para el relevo es la **asignación durable de Dexter**. El caso y el
ticket del CRM siguen siendo otra cosa, en su propio bloque. Nunca se usa el dueño del ticket para
decidir un control de relevo.

### Decisiones de frontera tomadas en 0A.3

**`Intervenir` NO se extrajo.** Vive dentro de `.compositor-nota`, pegado al motivo por el que el
compositor está bloqueado: «la atiende la IA → si querés escribir, Intervenir». Sacarlo de ahí sería
reestructurar el DOM, no mover código. **Viaja con `MessageComposer` en 0A.5.** Es una decisión
deliberada de frontera, no trabajo pendiente que se olvidó.

**`marcarAtendida()` sigue siendo UNA sola función** en la página, para Tomar y para Soltar. Son el
mismo gesto en dos sentidos; tener dos botones obligaría a mirar cuál está activo para saber quién la
tiene. **No partirla en `tomar()` / `soltar()` durante la Fase 0**: se vería más prolijo y cambiaría
la conducta.

**«Marcar como resuelta» quedó dentro de `HandoffControls`** porque está físicamente en ese bloque.
Cerrar una conversación **no es relevo** — su ubicación conceptual se reconsidera en la fase visual,
no ahora.

### Decisiones de frontera tomadas en 0A.4

**La cáscara del contexto se queda en la página.** El overlay `.info-fondo` **no está dentro del
`<aside>`**: son dos hermanos coordinados por `contextoAbierto`. Así que se extrajo el contenido y la
cáscara —`<aside class="info">`, el overlay, el botón Cerrar, el CSS `.info*` y sus media queries—
sigue en `[id]/+page.svelte`.

Los cuatro componentes de `context/` **representan contenido; no abren ni cierran el panel**. Nada
del responsive se partió y `ConversationHeader`, que dispara la apertura, no se tocó.

**Dos «Asignado a» que no son el mismo (D28):**

```
CasePanel        → caso.assignee_id, owners del CRM, action="?/asignar"
                   = dueño del TICKET del CRM

HandoffControls  → asignadaA
                   = dueño durable de la CONVERSACIÓN en Dexter
```

**No son intercambiables.** Nunca usar `caso.assignee_id` para el relevo ni para la cola. Están en
componentes distintos a propósito y **D28 sigue reservado para B4**.

**El `use:enhance` del formulario del CRM** se movió intacto con su formulario, incluido el
`bind:this={formularioAsignar}` que la página usa para dispararlo. Ese flujo no se reinterpreta
durante la Fase 0.

**Los cuatro componentes tienen 0 `fetch()`.** Red, mutaciones y derivados siguen en la página.

**La traza no gana nada durante la Fase 0:** ni AI Confidence, ni scores, ni diagnósticos
inventados, ni datos del mock de Stitch.

### Decisiones de frontera tomadas en 0A.5

Era el corte de mayor riesgo: ahí conviven `MediaRecorder`, el cronómetro, blobs y object URLs,
drag & drop, clipboard, adjuntos, plantillas, la ventana de WhatsApp con su `setInterval(15 s)` y
`Intervenir`. Se resolvió con una auditoría del ciclo de vida **antes** de mover una línea, y la
frontera quedó trazada así:

```
MessageComposer  =  presentación
[id]/+page.svelte =  lifecycle + red + recursos + autoridad
```

Verificado por conteo, y es la forma de comprobarlo de nuevo si alguien duda:

| | `MessageComposer` | `[id]/+page.svelte` |
|---|---|---|
| `fetch(` | **0** | 16 |
| `MediaRecorder` / `getUserMedia` | **0** | 3 / 1 |
| `setInterval` / `setTimeout` | **0** | 3 |
| `createObjectURL` / `revokeObjectURL` | **0** | 1 / 2 |
| `addEventListener` | **0** | sí |
| `$effect` | **0** | 4 |

Los cuatro efectos que quedan son los mismos cuatro de antes: límites de media, sondeo de 5 s,
resincronización de `ventanaBase` y el `tic` de 15 s. **La única mención de `MediaRecorder` en el
componente está en su comentario de cabecera**, explicando por qué no está ahí.

**Por qué el compositor no se lleva su propio ciclo de vida, aunque sería lo prolijo.** Porque hoy
esos recursos **no se liberan al desmontar** (D29, más abajo). Mover el dueño ahora cambiaría cuándo
nacen y mueren, que es exactamente lo que la Fase 0 promete no cambiar: se arreglaría un bug real
dentro de un commit que declara no alterar conducta, y la equivalencia dejaría de ser auditable.

**24 props, 9 `bind:` y 16 callbacks son deliberados.** Esa interfaz solo se achica moviendo
comportamiento, y mover comportamiento es justo lo que esta fase no hace. **No «optimizarla» sin una
fase explícita que lo autorice.**

**`Intervenir`: el botón viajó, la función no.** `intervenir()` y la decisión durable siguen en la
página. El componente recibe `bloqueadoPorIA` **ya resuelto** y **nunca calcula `control_efectivo`**
(B3.3b).

**El scroll conserva sus dos caminos distintos. No unificarlos:**

```
plantilla        → sondeo → hiloRef.alFinal(true)
humano/cliente   → push   → hiloRef.forzarAlFinal(mensajes.length)
```

Una plantilla enviada no vuelve en la respuesta inmediata, así que hay que sondear; un mensaje
humano o del cliente se agrega al arreglo, y `forzarAlFinal` además avanza `ultimoVisto` — el
acoplamiento que 0A.1 tuvo que exportar a propósito (ver el contrato más abajo).

### El ritmo, que se ganó con errores

**Una extracción por vez**, y entre cada una: `pnpm check` → vitest → revisar el diff. Se llegó a
este ritmo después de que una sola extracción produjera **dos errores propios**, los dos cazados por
guardas y no por la lectura previa.

## El contrato que no hay que «simplificar»

```
MessageThread.forzarAlFinal(n)
```

En orden:

1. **Quien atiende puede haber subido a leer mensajes viejos.** El autoscroll solo sigue al que ya
   estaba mirando el final; si alguien está releyendo algo de hace dos semanas, un mensaje nuevo no
   puede arrastrarlo al fondo.
2. **Pero al enviar una respuesta hay que mostrarla igual.** Ahí la intención es evidente: quien
   acaba de apretar Enviar quiere ver lo que mandó, haya estado donde haya estado.
3. **`forzarAlFinal(n)` da por vistos los `n` mensajes ANTES de que corra el efecto de autoscroll**,
   y recién entonces baja. Así el efecto no vuelve a decidir por su cuenta.
4. **Simplificarlo a un `alFinal()` pelado deja el mensaje enviado fuera del viewport**: el efecto
   corre después, evalúa que quien mira no estaba al final, y cancela el scroll.

Antes esto era `ultimoVisto = mensajes.length` escrito desde la página, porque las dos mitades
vivían en el mismo archivo. Esa asignación cruzaba la frontera del componente; ahora es una llamada
con nombre.

Lo encontró `pnpm check`, no la inspección previa — que es exactamente por qué la Fase 0 va antes
del rediseño: un acoplamiento así, mezclado con quinientos cambios visuales, se depura mucho peor.

## Cómo mover CSS sin romperlo

Dos cosas aprendidas en 0A.2, las dos con costo:

**1. Anclar contra contenido, no contra sintaxis.** El parche comprobaba que el bloque a mover
terminara en `}` — y un `}` cierra cualquier cosa. Resultado: al sacar `.contexto-toggle` de su
`@media (max-width: 1240px)` se fue también la línea que abría el media query, y `.info`,
`.info.abierto` y `.info-cerrar` quedaron huérfanas con una llave suelta. Lo cantó `pnpm check`.
Las aserciones de anclaje tienen que nombrar el selector o el comentario, nunca un signo.

**2. Una regla agrupada no puede quedarse entera de un solo lado.** Svelte scopea los estilos por
componente: si `A, B, C { … }` mezcla un selector del hijo con dos del padre, hay que separarla.
Separar no cambia lo calculado —misma declaración, mismos elementos— pero conviene anotarlo en el
CSS de los dos lados para que nadie lo lea como una divergencia.

Regla general: si un selector es compartido o dudoso, **se queda en el padre**. Es preferible un CSS
temporalmente menos prolijo que un cambio de especificidad.

**3. La excepción, cuando dejarlo en el padre cambiaría la apariencia.** En 0A.3 aparecieron dos
clases usadas por tres zonas a la vez, y ahí la regla anterior se da vuelta: como Svelte scopea,
dejarlas solo en el padre habría dejado **sin estilo** el marcado mudado. Entonces se **copian
verbatim** y se mantienen las dos:

```
.aviso      padre → el error de «Reiniciar (prueba)»
            hijo  → el banner de escalada

.aviso-mal  padre → el error de Intervenir (sigue en el compositor)
            hijo  → los errores de atender, resolver y reasignar
```

Condiciones: copia literal, sin renombrar, sin convertir valores a variables, sin `:global()`, sin
tocar especificidad, y **sin borrar la copia que el otro lado todavía necesita**. Cada copia lleva el
comentario que la marca como temporal.

**Se consolidan en la Fase 1**, que es la pasada de tokens y estilos — **no en 0A.4 ni en 0A.5**.
Cuando 0A.5 extraiga el compositor puede aparecer una tercera copia de `.aviso-mal`; también se deja.

Para decidir qué reglas mover, **no elegir rangos de línea a mano**: recorrer el bloque `<style>`
balanceando llaves y quedarse con las reglas cuyo selector coincide con el conjunto buscado. Para
cada `@media`, comprobar si contiene **solo** reglas de ese conjunto —entonces se mueve entero— o si
está mezclado —entonces hay que decidir regla por regla—. Un script de veinte líneas hace esto y
evita las dos formas de romperlo descritas arriba.

**4. Clasificar por prefijo del selector NO alcanza.** En 0A.4 falló tres veces, y las tres eran
cambios de apariencia reales:

| Caso | Qué pasó |
|---|---|
| `.proceso, .docs` | Regla **agrupada**. Clasificada por su última línea se fue entera a `DocumentationPanel`, y el `<details class="proceso">` de la traza perdió su padding |
| `.proceso-resumen` | Lo usan los `<summary>` de **los dos** paneles. Hubo que copiarlo, como `.aviso` |
| `.paso-marcado` | La usa `TracePanel`, pero ningún prefijo la capturaba: quedó **huérfana** en la página |

Las tres las delataron warnings nuevos de `pnpm check` — otra razón para mirar el delta de warnings
y no solo el de errores. La verificación obligatoria a partir de 0A.5:

```
por cada clase del marcado movido   →  localizar su regla efectiva
por cada regla movida               →  comprobar qué consumidores tenía
por cada selector agrupado          →  abrirlo y revisar cada selector
```

**5. `pnpm check` avisa de REGLAS SIN CLASE, nunca de CLASES SIN REGLA.** Esa asimetría dejó una
regresión viva cuatro commits:

```
.reiniciar-discreto   la comparten el botón «Reiniciar (prueba)» y el
                      «Cancelar» que aparece mientras se graba una nota de voz
```

0A.2 mudó el encabezado y la regla se fue con él; el `Cancelar`, que seguía en la página, perdió su
`opacity: .62` y su `font-size: 10.8px` desde `edcfd12`. **Ninguna guarda lo vio**: en el componente
la regla sí se usa, así que allá no hay warning; acá la clase quedó huérfana en silencio.
Restaurada verbatim desde `edcfd12^` en `8ab8bb3`, **antes** de tocar el compositor.

Después, en `2ae5241`, la regla **viajó con su botón** al `MessageComposer` y la copia de la página
se fue con ella porque ya no le quedaba ningún consumidor — consecuencia mecánica de la extracción,
no limpieza. `ConversationHeader` conserva la suya. Quedan **dos copias scoped**, a consolidar en la
Fase 1.

Moraleja operativa: revisar el delta de warnings **no alcanza**. Hay que comprobar además que cada
clase del marcado que **se queda** siga teniendo su regla.

## Polling — una sola cadena, en el padre

```
setInterval(5 s)  +  visibilitychange  +  focus
```

Los tres viven en `[id]/+page.svelte` y existen **una sola vez**. `MessageThread` **no sondea**:
recibe el hilo ya armado por props.

Al extraer cualquier bloque nuevo, verificar que no aparezca una segunda cadena. Dos sondeos
simultáneos duplican las llamadas y hacen que los mensajes entren dos veces.

## Deuda anotada, deliberadamente sin tocar

- `.ventana-cerrada button` — CSS muerto preexistente. La frontera nueva hizo que Svelte pudiera
  verlo y lo reporta como selector sin usar (22 → 23 warnings). **En 0A.5 viajó con el compositor y
  sigue muerta allá.** La pantalla canónica de Stitch sí tiene ahí un botón «Choose Template», así
  que la Fase 4 probablemente lo reviva.
- `.adjunto-otro` — definido y nunca usado, desde antes. Se dejó en el padre; en 0A.3 el marcado
  encogió lo suficiente como para que Svelte por fin lo detectara.

**El patrón:** la detección de selectores sin usar de Svelte depende del marcado que le queda al
componente, así que **cada extracción va a destapar más CSS muerto preexistente**. Un warning nuevo
de este tipo no es una regresión — pero hay que identificar el selector exacto y comprobar que
efectivamente ya estaba muerto antes. **No se limpian en Fase 0.**
- `Reiniciar (prueba)` sigue en la barra de la conversación, ahora dentro de `ConversationHeader`,
  **idéntico**: mismo texto, mismo `title`, mismo endpoint. **No se corrige en Fase 0**: esta fase no
  cambia conducta. Queda para la fase funcional, con guarda del lado del servidor.
- `quien()` / `esTelefono()` / `esUuid()` están **duplicados** entre `ConversationHeader` y
  `+layout.svelte` — el comentario original ya decía «mismo criterio que la lista del layout». Es el
  mismo patrón que hizo nacer `estado.js`: dos copias que nadie ve separarse hasta que una cambia.
  Unificarlas en `formato.js` es refactor, no movimiento; **no se hizo** en toda la Fase 0A.
  Candidato natural para la **0B**, que es justo cuando se toca `+layout.svelte`.

Esta fase mueve código; no ordena ni limpia. Mezclar refactor con limpieza hace que el diff deje de
poder auditarse.

## D29 — los recursos del compositor no se liberan al desmontar

```
ESTADO:  ✅ CERRADO en 450d4e4
ORIGEN:  PREEXISTENTE — no lo introdujo la Fase 0A
         no se corrigió en 0A.5, para conservar la equivalencia
```

La página se remonta por conversación (`{#key abierta}`) y **no existe un solo `onDestroy` en el
archivo**. Al cambiar de conversación mientras hay una grabación en curso pueden quedar vivos:

```
- el MediaRecorder, todavía activo;
- los tracks del stream del micrófono, abiertos;
- el cronómetro de 1 s;
- el object URL de un adjunto, sin revocar.
```

El primero es el que importa: **el micrófono puede seguir abierto después de abandonar la pantalla.**

**Es un defecto funcional, no de componentización.** Por eso no entró en el diff de 0A.5: ese commit
declara no alterar conducta, y arreglar esto la altera — para bien, pero dentro de un commit que
dejaría de poder auditarse por equivalencia.

### Cómo quedó cerrado

El micrófono, el `MediaRecorder` y el cronómetro se mudaron a
[`lib/conversaciones/grabacion.js`](../django-crm/frontend/src/lib/conversaciones/grabacion.js), con
**un solo camino de liberación**, y la página lo suelta en un `onDestroy`.

**Por qué un módulo y no el arreglo escrito en la página:** porque en la página **no se puede
probar**. El harness de vitest corre en `node` sin plugin de Svelte —lo dice su propio comentario—,
no compila `.svelte`, y ningún test del repo monta un componente. Un `onDestroy` inline no tendría
ninguna guarda, que es exactamente cómo `.reiniciar-discreto` sobrevivió cuatro commits.

| | |
|---|---|
| carrera de `getUserMedia` | ✅ cubierta — `soltada` se relee **después** del `await`; el stream que llega tarde se detiene y no se construye recorder |
| grabación ya activa | ✅ cubierta — `onstop` se desarma **antes** de parar: desmontar no es terminar de grabar |
| cronómetro | ✅ cubierto — `clearInterval` + `null`, verificado por ausencia de tics posteriores |
| object URL | ✅ cubierto — ver la cadena abajo |
| cleanup idempotente | ✅ — `stop()` sólo si `state !== 'inactive'`; soltar dos veces, tras cancelar, o sin haber grabado nunca |
| camino normal del audio | ✅ preservado — `parar()` sigue armando el adjunto |
| cancelación manual | ✅ preservada — y además deja la sesión lista para volver a grabar |
| mutación | ✅ tres, las tres detectadas y revertidas |

**La cadena del object URL**, porque el inventario de recursos puede confundir:

```
onDestroy(() => soltarRecursosDelCompositor({ sesion: voz, adjunto }))
  → revocar  (parámetro por omisión, en grabacion.js)
  → URL.revokeObjectURL(adjunto.url)
```

Es local con certeza: **`adjunto.url` tiene una sola asignación en todo el archivo** y siempre sale
de `createObjectURL`. Los medios que llegan en el hilo son otra cosa y no pasan por ahí. Las otras
dos llamadas a `revokeObjectURL` que quedan en la página son las preexistentes de `tomarArchivo` y
`quitarAdjunto`.

**Una sesión por página, nunca una global.** El único binding a nivel de módulo es `const FORMATOS`;
todo lo mutable vive dentro de `sesionDeGrabacion()`. Si `soltada` fuera del módulo, irse de una
conversación dejaría a la siguiente sin poder grabar nunca más. Importar el módulo tampoco evalúa
`navigator`, `window` ni `MediaRecorder`: se consultan dentro de las operaciones, así que es seguro
en SSR. Las dos cosas tienen guarda.

**Las tres mutaciones**, que es lo que prueba que las guardas sirven:

```
anular la protección de la carrera  →  falla 1 test, exactamente ese
mover `soltada` al módulo           →  fallan 9, incluida su guarda propia
quitar el default de `revocar`      →  falla 1, exactamente ese
```

La tercera existe porque la primera versión de ese test **inyectaba** `revocar` y por eso no
protegía el camino real. Inyectar la dependencia que se quiere verificar deja la prueba verde
mientras el código de producción se rompe.

**Límite conocido:** que el `onDestroy` llame a `soltarRecursosDelCompositor` está verificado **por
lectura, no por prueba** — el harness no compila `.svelte`. Es el único eslabón sin guarda, y se
cierra el día que exista un harness de componentes.

**De paso, la misma clase de fuga:** si `new MediaRecorder(...)` falla *después* de que
`getUserMedia` entregó el flujo, el micrófono quedaba abierto. Ahora el `catch` cierra los tracks.

## Baseline de regresión

| Chequeo | Valor esperado |
|---|---|
| `pnpm check` | 2 errores, ambos en `(no-layout)/org/`; **0 en `conversaciones/`** |
| warnings | **24**. 22 originales + `.ventana-cerrada button` (0A.1) + `.adjunto-otro` (0A.3). Sin cambio en 0A.4 ni en 0A.5 |
| vitest, hasta 0A.5 | 17 failed \| 7 passed (24) · 63 failed \| 261 passed (324) |
| vitest, desde D29 | 17 failed \| 8 passed (25) · **63 failed** \| 278 passed (341) |

Los fallos de vitest son el baseline histórico del CRM v2, ajenos a la Bandeja. **Lo que se compara
es el número de FALLOS: 63, y los mismos 17 archivos.** Los pasados suben cuando se agregan guardas
—D29 sumó 17— y eso es lo esperado, no una desviación.

**Cómo usar esta tabla:** una diferencia respecto de estos números es una regresión del incremento
en curso, no ruido. Un error nuevo dentro de `conversaciones/` bloquea el incremento.

**Diferencia visual acumulada de la Fase 0A:** *no detectada* mediante equivalencia de marcado/CSS y
chequeos estáticos; **comparación por píxel no ejecutada**. La frase importa: no es lo mismo que
«ninguna».
