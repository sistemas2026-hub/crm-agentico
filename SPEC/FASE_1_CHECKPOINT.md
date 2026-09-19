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
07c73fa  checkpoint con D30
610a19b  1.3B — autores en el hilo
9ae12f5  checkpoint con 1.3B
2a2497d  1.4B.1 — tokens + retiro del reset de prueba
2383224  checkpoint con 1.4B.1
cfc82c6  1.4B.2a — plantillas en la ventana cerrada
f5b657a  checkpoint con 1.4B.2a
16ab44e  1.4B.2b-i — control en el Header + conflictos 409
a916410  checkpoint con 1.4B.2b-i
8dafad4  1.4B.2b-ii(a) — ownership del handoff
fb93ddf  corrige los comentarios de .aviso
```

Nada de esto está pusheado.

## Estado

```
1.1  Foundation visual        ✅ cerrada   cdeb69e
1.2  Cola Stitch              ✅ cerrada   9875e34
1.3A D30 · read-side          ✅ cerrada   4a701cd
1.3B Thread / autores         ✅ cerrada   610a19b
1.4A · 1.4A.2  auditorías      ✅ cerradas
1.4B.1 tokens + reset          ✅ cerrada   2a2497d
1.4B.2a WA cerrada + plantillas ✅ cerrada   cfc82c6
1.4B.2b-i  IA controla + 409    ✅ cerrada   16ab44e
1.4B.2b-ii(a) ownership · 3 estados  ✅ cerrada   8dafad4
1.4B.2b-ii(b) ADMIN reasigna         ← el próximo
1.4B.2b-iii   WA abierta · por cerrar   pendiente
   **1.4B.2 NO está cerrada.**
1.4C  T6 · Return to AI        🔒 pendiente, fuera de 1.4B
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


## 1.3B — quién escribió cada cosa

### La clasificación canónica

```
rol=nota                      →  Nota interna          + autor si consta
origen ausente / null         →  Origen no registrado
user      + cliente           →  Cliente
assistant + ia                →  Dexter IA
assistant + humano            →  autor_nombre, o «Atención humana»
assistant + sistema           →  Sistema
cualquier otra combinación    →  Origen no registrado
```

**La regla de fondo: el rol por sí solo NO atribuye autoría.** La única excepción es `nota`, y sólo
porque ahí el rol identifica *qué tipo de elemento* es, no quién lo escribió.

Un origen suelto tampoco alcanza: `cliente` bajo rol `assistant`, o `ia` bajo rol `user`, son estados
que el motor no produce. Tratarlos como válidos sería inventar una lectura de datos inconsistentes.

Vive en `formato.js::autorDe(m)` — función pura, testeable sin montar Svelte.

### El defecto propio, encontrado en la auditoría antes de commitear

La primera versión decía:

```js
if (origen === 'cliente' || rol === 'user')
```

Ese `||` **reintroducía por la puerta lateral justo lo que D30 vino a eliminar**: un `user` histórico
sin origen registrado salía afirmado como Cliente.

**Nunca estuvo en producción** — se corrigió antes del commit. **No es una regresión.**

Y lo que importa para la próxima vez: **los trece tests originales pasaban con el código malo**,
porque ninguno probaba `user` con un origen que no fuera `cliente`. Cada caso alimentaba la
combinación coherente. Es el patrón que el repo ya tiene documentado — *un caso dorado que usa la
frase que sí funciona no prueba nada sobre la que falla*.

**Los cuatro casos que faltaban son negativos:**

```
user + NULL              no es Cliente
user + origen futuro     no es Cliente
assistant + cliente      neutro
user + ia                neutro
```

Ahora la guarda del NULL va **primera**, antes de cualquier identidad, y las tres salidas neutras son
**una única constante congelada** para que no puedan divergir.

### El histórico y el humano

`origen` NULL **no se rellena**: ni por rol, ni por contenido, ni por quién controla hoy la
conversación. Cero backfill.

```
origen=humano + autor_nombre   →  el nombre real
origen=humano sin nombre       →  «Atención humana»
```

**Nunca como autor histórico**: el dueño actual, el `assignee` del CRM o el control actual. Pueden no
ser quien escribió.

### El lenguaje visual

```
IA       violeta + etiqueta         Humano   azul + nombre o etiqueta
Nota     ámbar + «Nota interna»     Sistema  neutral
NULL     neutral                    Cliente  estructura diferenciada, sin rótulo
```

**Ninguna identidad depende únicamente del color.** El rótulo va siempre con palabra; el punto es
refuerzo. Un 8% de la gente no distingue violeta de azul, y un punto sin texto no dice *qué* pasó.

Sistema y «sin registro» quedan en gris **a propósito**: ninguno de los dos es alguien con quien se
pueda hablar, y el segundo además es la admisión de que no sabemos. Un color propio le daría una
identidad que justamente no tiene.

El cliente no lleva rótulo: su burbuja ya está del otro lado y es el único que no puede confundirse
con nadie.

### Lo que no se tocó

`forzarAlFinal(n)` y `alFinal(true)` siguen siendo caminos distintos. Cero timers, observers,
`$effect` u `onMount` nuevos. Adjuntos, `estado_entrega`, `error_entrega` y timestamps intactos.

**CSS conocido, sin limpiar:**

```
a-cliente    marcador semántico deliberado, sin regla propia
entrega-*    clases históricas; sólo .entrega y .entrega-leido tienen regla
```

### Mutaciones

```
todo assistant → IA                 →  9 de 13 fallan
rol=user → Cliente sin mirar origen →  3 de 17 fallan, justo los que faltaban
```

Las dos revertidas.


## 1.4 — el centro operativo

### T6 está FUERA de 1.4B, y no es un olvido

El motor **sí** sabe devolver el control a la IA (`transiciones.py::devolver_a_ia()`, evento
`devuelta_a_ia`). **La UI no lo expone**, y el contrato dice por qué:

> **C9** — «Que G9 esté verde no activa T6: T6 entra con el control durable, en su fase.»

**Los cuatro estados de Stitch NO son los cuatro pasos de Dexter.** Esto hay que leerlo antes de
diseñar nada de T6:

```
Stitch                          Dexter (contrato T6)
A  IDLE                         (estado previo, no un paso)
B  IN PROGRESS · MUTEX LOCK     comprime intención + solicitud + aceptación
C  CONFIRMED · «Handoff logged» ≠ receipt durable del proveedor
D  «Reverted safely»            Dexter distingue «falló» de «no se sabe» (§3.6)
```

`MUTEX LOCK` y «syncing thread lock state» son **vocabulario del mock**: Dexter no tiene un mutex de
hilo. Y la tarjeta D afirma que volvió a humano — una afirmación fuerte que el estado `desconocida`
no permite hacer.

**Eso es 1.4C**, con su propia fase funcional.

### Lo que las seis referencias pedían ya existía

Ninguna de las seis pide capacidad nueva. `Reassign` coincide al pie de la letra con C16 («Reason ·
Required — stored in the audit trail»), el 409 con «the view has been refreshed with the current
owner», y `WA closed` con las plantillas que el Composer ya tiene.

**Se confirma la predicción del checkpoint de 0A**: `.ventana-cerrada button` estaba anotada como CSS
muerto con la nota «la Fase 4 probablemente lo reviva». Es exacto — recupera consumidor en 1.4B.2.

### 1.4B.1 — los tokens, y por qué no fue mecánico

```
Header      4 → 0        Handoff    16 → 0        Composer   58 → 1
```

**`ember` significaba tres cosas distintas** en el Composer:

```
.ventana-avisa · .plantilla-inadecuada    ember-soft → aviso    (avisos de verdad)
.compositor.arrastrando · .soltar-aca
                        · .accion-icono:focus  ember → humano   (gestos de una persona)
```

Un `ember → aviso` mecánico habría pintado de ámbar el arrastre y el foco. `clay` sí era siempre el
modo nota → `--bandeja-nota`; `rust` → error; `moss` → ok.

**El único `--v2-*` que queda es `var(--v2-fs)`**: la métrica del tamaño base de tipografía, no un
color. **No se inventó un equivalente** para llegar a cero — un token sin significado sería peor que
la referencia.

### El reset de prueba: sale de la UI, no del backend

```
botón + prop + regla · estado · reiniciarConversacion() · cableado   →  retirados
endpoint DELETE y backend                                            →  intactos
```

Cero consumidores y cero tests dependientes tras el retiro.

**Y una consecuencia que el check cazó:** los warnings subieron a 27 por `.aviso` en el padre —la
regla del mensaje de error del reset, cuyo único consumidor era ése—. Se retiró, y con eso **se cerró
la duplicación que 0A.3 había dejado anotada**: `.aviso` se copió a `HandoffControls` porque el padre
la necesitaba, y ya no. Vuelta a 26.

**No fue limpieza oportunista: el huérfano lo creó este mismo cambio.**

`.reiniciar-discreto` **sobrevive** en el Composer — es el botón Cancelar de la grabación, ahora su
único consumidor. El nombre quedó heredado y sin sentido; **no se renombra**, eso es limpieza. Sus
dos comentarios sí se actualizaron: referenciaban una función que ya no existe.

### Lo que 1.4B.2 tiene pendiente

**Composición, no color.** El layout del Header, el banner de Handoff, el Composer, y la experiencia
real de ventana cerrada con plantillas (`plantillas`, `plantillaElegida`, `valoresPlantilla`,
`enviandoPlantilla`) — de punta a punta, sin inventar HSMs.

Y comparar **estado por estado** contra su referencia: IA controla · humano sin dueño · asignada a mí
· asignada a otro · ADMIN reasigna · 409 tras una carrera.


### 1.4B.2a — la ventana cerrada, y una predicción que se cumple

El problema era de **composición, no de capacidad**. El aviso decía «hay que usar una plantilla
aprobada» y el botón para elegirla estaba en la barra de abajo:

```
[WhatsApp · ventana inactiva]   Ventana cerrada · …   [Elegir plantilla]
```

Si el aviso nombra la salida, la puerta va ahí mismo. No se repite cuando el selector ya está
abierto.

**`.ventana-cerrada button` recuperó consumidor.** Figuraba como regla muerta desde 0A.1, con esta
nota en el checkpoint de la Fase 0:

> «La pantalla canónica de Stitch sí tiene ahí un botón *Choose Template*, así que la Fase 4
> probablemente lo reviva.»

```
pnpm check   26 → 25 warnings TOTALES
delta:       .ventana-cerrada button dejó de estar sin consumidor
```

**25 es el total que reporta `pnpm check`**, no «quedan dos». Las dos deudas conocidas de
`conversaciones/+layout.svelte` —`.marca` y `.marca::before`— siguen ahí, pero no son los únicos
warnings del proyecto.

**Cero lógica nueva:** se reutilizan `plantillas`, `plantillaElegida`, `valoresPlantilla` y
`enviandoPlantilla`, que ya estaban entre las 24 props.

**Tres cosas del diseño que NO se copiaron, y ninguna es funcionalidad faltante:**

```
«1 WhatsApp HSM billing credit»    Dexter no sabe de créditos de Meta
«Variable {{1}} (Customer Name)»   Meta no da etiquetas semánticas; Dexter sabe
                                   CUÁNTAS variables hay, no qué significan
«Meta Approved» por fila           el motor ya filtra a APPROVED: repetirlo N veces
```

### 1.4B.2b — los ocho estados que faltan

```
IA controla · humano sin asignar · asignada a mí · asignada a otro
ADMIN reasigna · 409 · WA abierta · WA por cerrar
```

El Header y el banner de Handoff **no se tocaron** en 1.4B.2a. Cada estado se demuestra contra su
referencia, uno por uno — «se parece» no es evidencia.


### 1.4B.2b-i — quién controla, y el 409 que no era un error

**El Header no decía quién lleva la conversación.** Que la atendiera la IA sólo se deducía del
compositor bloqueado.

```
[● LA ATIENDE LA IA]  violeta      [● HUMANO · Ana Pérez]  azul
                                   [● HUMANO · SIN ASIGNAR]
```

Con la **misma forma que los distintivos de la cola**: es la misma pregunta en dos pantallas.

**`escalada` y `asignadaA` llegan como props**, ya derivadas en la página. El Header **no las
recalcula** — si dedujera el control por su cuenta, dos partes de la pantalla podrían decir cosas
distintas sobre lo mismo. Las props pasan de 4 a 6 por eso.

**El 409 ya estaba bien funcionalmente y se veía como un error.** `conflictoDeAsignacion()` dice
*quién* quedó, no un «falló» genérico. Lo que estaba mal era el tono: rojo, como si quien apretó
hubiera hecho algo malo. No lo hizo — llegó segundo. Ahora es un banner informativo con filete azul.

**Faltaba un caso del contrato.** `legado_sin_relevo` caía al `default`, y **es alcanzable**: sale de
reasignar (`transiciones.py:397`), y esa ruta también usa `conflictoDeAsignacion`. Según C17 una
reasignación deja evento de auditoría y el legado no tiene eventos — hay que adoptarla primero, y eso
es G8:

```
ya_asignada · no_es_suya · control_ia · no_abierta · legado_sin_relevo   → trato explícito
default                                                                  → lo desconocido
```

**Sin test**: `conflictoDeAsignacion()` vive dentro de `+page.svelte` y el harness no compila
`.svelte`. Extraerla sería refactor fuera de alcance. Lo comprobado fue el contrato C17, el backend
(`transiciones.py` y el mensaje de `api.py:6347`) y las dos rutas que la llaman.

**Que el Header muestre «HUMANO · Ana Pérez» NO cierra «asignada a mí» ni «asignada a otro»:** falta
cómo `HandoffControls` presenta permisos y acciones en esos estados.

### 1.4B.2b-ii — los seis que faltan

```
humano sin asignar (completo) · asignada a mí · asignada a otro
ADMIN reasigna · WA abierta · WA por cerrarse
```

El banner de `HandoffControls` sigue sin reestructurar.


### 1.4B.2b-ii(a) — una alarma que estaba siempre encendida

El banner abría con `TriangleAlert` en **los cuatro estados**, incluido «asignada a mí» — que no es
una alerta sino trabajo normal en curso. **Una alarma permanente deja de significar algo**, y entrena
a quien atiende a ignorarla.

```
sin dueño                 TriangleAlert + filete ámbar
con dueño (mía o ajena)   UserCheck, sin filete
```

El ámbar vuelve a decir algo concreto: hay trabajo humano esperando que alguien se lo apropie.

**Los dos dueños eran el mismo concepto y se veían distinto.** «Asignada a mí» y «En atención: X»
responden la misma pregunta; ahora comparten gramática visual y sólo cambia a quién nombran. El azul
marca el único caso sobre el que este operador puede actuar. Es el mismo distintivo que el pie de la
fila en la cola.

**Un defecto de responsive que apareció al verificar:** `.duenio` tenía `white-space: nowrap` **sin
recorte**, así que un nombre largo empujaba los botones fuera de la franja. Se agregó `max-width` con
ellipsis y —lo que lo hace funcionar— **`min-width: 0`**: sin él un hijo flex no achica por debajo de
su contenido y el ellipsis nunca se aplica. El nombre completo sigue en el `title`.

```
sin asignar       sin dueño · Tomar (+ Reasignar si ADMIN)
asignada a mí     dueño azul · Soltar (+ Reasignar si ADMIN)
asignada a otro   dueño gris · NINGUNA acción — sólo Reasignar si ADMIN
```

**Control, ownership y permisos quedan como tres cosas distintas**, que era el objetivo.

**La duplicación de `.aviso` de 0A.3 quedó cerrada.** Su copia del padre se fue en 1.4B.1 al retirar
el reset de prueba, que era su único consumidor. Los dos comentarios que decían «sigue en
+page.svelte, que todavía la necesita» se corrigieron: mandaban a buscar una copia inexistente.

**`ADMIN reasigna` NO está cerrado**: el botón funciona, pero su diálogo no se comparó ni compuso
contra la referencia. Eso es ii(b).


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
| vitest | 17 failed \| 10 passed (27) · **63 failed** \| 315 passed (378) |
| guardas 0B.0 | 20/20 |
| guardas D29 | 17/17 |
| guardas `formato` (1.3B) | 17/17 |
| D30, backend | 18/18 — **se reporta aparte, no se suma a vitest** |

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
