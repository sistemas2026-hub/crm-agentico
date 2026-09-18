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
| Escalada + controles de relevo | ⬜ **0A.3, el próximo** | `[id]/+page.svelte` ~1364–1580 |
| Contexto (`<aside>`) | ⬜ 0A.4 | ~1983–2302 |
| Compositor (`.pie`) | ⬜ 0A.5, el último | ~1592–1965 |

`[id]/+page.svelte`: 4036 → 3638 → **3514 líneas**.

Los rangos son orientativos: se corren en cada extracción. Confirmarlos contra el marcado antes de
cortar, nunca contra esta tabla.

**Los dos componentes extraídos son presentacionales.** Reciben props y avisan por callbacks; el
estado, los fetches, la navegación y las mutaciones se quedan en `[id]/+page.svelte`. La única
excepción deliberada es el scroll del hilo, que vive donde vive el elemento que scrollea (ver el
contrato de `forzarAlFinal` más abajo).

No convertir un componente en controlador «para que sea autónomo»: la página es la que sabe de rutas
y de red, y es donde el próximo que lea el código va a buscar esa lógica.

## Orden acordado

```
0A.1 MessageThread   ✅ cerrado   7a41bdc
0A.2 Header          ✅ cerrado   edcfd12
0A.3 Escalada + relevo   ← el próximo
0A.4 Contexto
0A.5 Compositor      ← último, es el de mayor riesgo
```

### Lo que 0A.3 no puede hacer

Es la extracción más delicada de la fase, porque ahí están **Intervenir, Tomar, Soltar y
Reasignar**, y con ellos los roles, el 409, el dueño durable, el `relevo_version` y los estados de
carga.

**Los botones pueden mudarse; ni una decisión de B3.3b, B3.4 o B3.5 puede mudarse con ellos.** La
verdad la fija `control_efectivo()` en el motor y la proyección de bandas, no la pantalla. Si al
cortar aparece la tentación de recalcular en el componente quién controla la conversación o si
alguien puede tomarla, la frontera está mal trazada: esos valores llegan como props ya decididos.

Concretamente, se conservan sin tocar: que un 409 relea el dueño en vez de pisarlo, que solo un
ADMIN vea Reasignar, que el motivo sea obligatorio, que Soltar sea solo del dueño, y que la pantalla
espere la confirmación del backend antes de cambiar la propiedad.

El compositor va al final a propósito: `MediaRecorder`, cronómetro, object URLs, drag & drop,
clipboard, ventana de 24 h con su propio `setInterval(15 s)`, plantillas y audio. No hay premio por
apurarlo.

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
- `.adjunto-otro` — definido y nunca usado, desde antes. Se dejó en el padre para no convertirlo en
  un warning nuevo.
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
| warnings | 23 (eran 22 antes de 0A.1; el nuevo es `.ventana-cerrada button`). Sin cambio en 0A.2 |
| vitest | 17 failed \| 7 passed (24) · 63 failed \| 261 passed (324) |

Los fallos de vitest son el baseline histórico del CRM v2, ajenos a la Bandeja.

**Cómo usar esta tabla:** una diferencia respecto de estos números es una regresión del incremento
en curso, no ruido. Un error nuevo dentro de `conversaciones/` bloquea el incremento.
