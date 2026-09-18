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
```

Nada de esto está pusheado.

## Estado

| Bloque | Estado | Dónde está hoy |
|---|---|---|
| `MessageThread` | ✅ extraído | `lib/conversaciones/messages/MessageThread.svelte` |
| `formato.js` (helpers puros) | ✅ extraído | `lib/conversaciones/formato.js` |
| Polling de 5 s | ✅ sigue **único y en el padre** | `[id]/+page.svelte` |
| Autoscroll | ✅ vive en `MessageThread` | — |
| Header | ⬜ pendiente | `[id]/+page.svelte` ~1439–1486 |
| Escalada + controles de relevo | ⬜ pendiente | ~1488–1704 |
| Contexto (`<aside>`) | ⬜ pendiente | ~2107–2426 |
| Compositor (`.pie`) | ⬜ pendiente | ~1716–2089 |

`[id]/+page.svelte`: 4036 → **3638 líneas**.

## Orden acordado

```
0A.1 MessageThread  ✅
0A.2 Header
0A.3 Escalada + relevo
0A.4 Contexto
0A.5 Compositor      ← último, es el de mayor riesgo
```

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
- `Reiniciar (prueba)` sigue en la barra de la conversación. **No se corrige en Fase 0**: esta fase
  no cambia conducta. Queda para la fase funcional, con guarda del lado del servidor.

Esta fase mueve código; no ordena ni limpia. Mezclar refactor con limpieza hace que el diff deje de
poder auditarse.

## Baseline de regresión

| Chequeo | Valor esperado |
|---|---|
| `pnpm check` | 2 errores, ambos en `(no-layout)/org/`; **0 en `conversaciones/`** |
| warnings | 23 (eran 22 antes de 0A.1; el nuevo es `.ventana-cerrada button`) |
| vitest | 17 failed \| 7 passed (24) · 63 failed \| 261 passed (324) |

Los fallos de vitest son el baseline histórico del CRM v2, ajenos a la Bandeja.

**Cómo usar esta tabla:** una diferencia respecto de estos números es una regresión del incremento
en curso, no ruido. Un error nuevo dentro de `conversaciones/` bloquea el incremento.
