# Fase 0A — checkpoint

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
| Contexto (`<aside>`) | ⬜ **0A.4, el próximo** | `[id]/+page.svelte` |
| Compositor (`.pie`), con `Intervenir` | ⬜ 0A.5, el último | `[id]/+page.svelte` |

`[id]/+page.svelte`: 4036 → 3638 → 3514 → **3102 líneas**.

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
0A.4 Contexto            ← el próximo
0A.5 Compositor      ← último, es el de mayor riesgo (y se lleva Intervenir)
```

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

### Lo que viene, y su riesgo

**0A.4 — Contexto.** Merece auditoría previa como la tuvo 0A.3. Ahí conviven el caso del CRM, la
retención, la traza y la documentación: el riesgo específico es **mezclar el contexto de la
conversación de Dexter con los datos del ticket del CRM**, que D28 manda mantener separados.

**0A.5 — Compositor**, al final a propósito: `MediaRecorder`, cronómetro, object URLs, drag & drop,
clipboard, ventana de 24 h con su propio `setInterval(15 s)`, plantillas, audio — y `Intervenir`. No
hay premio por apurarlo.

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
  verlo y lo reporta como selector sin usar (22 → 23 warnings). La pantalla canónica de Stitch sí
  tiene ahí un botón «Choose Template», así que la Fase 4 probablemente lo reviva.
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
  Unificarlas en `formato.js` es refactor, no movimiento; **no se hizo**. Candidato para 0A.4 o una
  fase posterior.

Esta fase mueve código; no ordena ni limpia. Mezclar refactor con limpieza hace que el diff deje de
poder auditarse.

## Baseline de regresión

| Chequeo | Valor esperado |
|---|---|
| `pnpm check` | 2 errores, ambos en `(no-layout)/org/`; **0 en `conversaciones/`** |
| warnings | **24**. 22 originales + `.ventana-cerrada button` (0A.1) + `.adjunto-otro` (0A.3) |
| vitest | 17 failed \| 7 passed (24) · 63 failed \| 261 passed (324) |

Los fallos de vitest son el baseline histórico del CRM v2, ajenos a la Bandeja.

**Cómo usar esta tabla:** una diferencia respecto de estos números es una regresión del incremento
en curso, no ruido. Un error nuevo dentro de `conversaciones/` bloquea el incremento.
