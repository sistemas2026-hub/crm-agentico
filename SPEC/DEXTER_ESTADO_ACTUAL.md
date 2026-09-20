# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Si contradice a una conversación, gana este archivo.

**Un gate no está cerrado hasta que este archivo lo refleje.** Y se poda cuando
se actualiza: una sección que quedó vieja no es inocua — la siguiente sesión la
lee como verdad. La historia detallada vive en `auditorias/`, no acá.

Última actualización: 19/09/2026, al cerrar la Fase 1.

---

## BASE CANÓNICA

```
rama       feature/bandeja-relevo
worktree   C:\tmp\dexter-bandeja
```

Nada pusheado. Sobre `d0d6be9`:

```
04d835e  backend T6, medido contra PostgreSQL 16.14
df7eb7c  checkpoint + esta memoria operativa
d033e58  UI de T6
fa6b91a  cierre de 1.4C + corrección de la lista de warnings
5f30f74  1.5 Case + Tools
178d749  cierre de 1.5
4d73ea8  1.6 Activity
139f8ca  cierre de 1.6
f61fd4d  1.7 Customer
929b86e  cierre de 1.7
4541423  1.8 Network
d5cc765  cierre de 1.8
b7bc9ea  1.9 cierre visual
```

## WORKTREE

Queda **un solo** archivo modificado sin commitear:

```
SPEC/CONTRATO_RELEVO_IA_HUMANO.md   arrastre ajeno sobre G9, sin destino propio
```

No restaurarlo ni borrarlo. Y mientras siga ahí, **stage por rutas explícitas
siempre, también para documentación**: prohibidos `git add .`, `git add -A`,
`commit -a` y **`git add SPEC/`**.

Ese último se coló en el cierre de 1.8 y metió el arrastre en el commit
documental. Un directorio entero es el mismo gesto que un `add .`: basta con que
alguien deje un archivo ajeno adentro. Verificar siempre con
`git diff --cached --name-only` antes de commitear.

## CERRADO

```
Fase 0 (componentización)     ✅
D29 · D30                     ✅
G9 recibo punta a punta       ✅ verde en producción 16/09/2026
Fase 1.1–1.4B (visual)        ✅
FASE 1.4C  backend + UI de T6 ✅
FASE 1.5   Case + Tools       ✅
FASE 1.6   Activity           ✅  el relevo se lee por primera vez
FASE 1.7   Customer           ✅  lo que sabe del cliente, y lo que no
FASE 1.8   Network            ✅  qué se le hizo al equipo, sin botones
FASE 1.9   cierre visual      ✅  utilidades de panel unificadas
FASE 1     Bandeja rediseñada ✅  COMPLETA
```

## ABIERTO al cerrar la Fase 1

```
G6 sobre messages poblada   🔒 gate de DESPLIEGUE. La migración aplica limpia
                               desde cero y el ledger la anota sola, pero no se
                               midió sobre una tabla con datos. No bloquea
                               desarrollo; sí bloquea cualquier push.
QA visual multi-viewport    🔴 NO EJECUTABLE con los medios disponibles, y no
                               por falta de intento: el dev server levanta pero
                               hooks.server.js:373 redirige a /login antes de
                               montar el layout, así que ni el estado de error
                               dentro de .mesa.bandeja se dibuja. Entrar exige
                               un JWT del backend de producción; una ruta de
                               prueba con datos falsos está prohibida.
                               NINGÚN píxel de 1.4C a 1.9 se vio renderizado.
D28                         ⏭ abierto para B4. La pantalla lo MUESTRA (1.5): el
                               dueño del CRM es informativo, el de Dexter manda.
                               No se reconcilian — no comparten identidad de
                               usuario, y por eso se comparan nombres.
hot path ③a/③c              ⏭ idempotencia del outbound automático del canal,
                               retirado y preservado en
                               auditorias/1.4C-hotpath-diferido.md
T7 endpoint                 ⏭ «devolver sin responder»: capacidad distinta, NO
                               el recovery de T6
semánticos ember/clay/      ⏭ resueltos en context/ (1.5); los consumidores de
rust/moss                      otras pantallas, en la fase de cada una
```

## B4 — CERRADO EN CÓDIGO. Falta encenderlo (G7)

```
migración    202609201000_sincronizaciones_externas.sql   aplica limpia
T20          nucleo/relevo/reconciliador.py               la regla de reintento
worker       nucleo/relevo/worker_reconciliador.py        proceso propio, 5 min
ejecutor     nucleo/relevo/efectos_externos.py            crear_caso real
panel        «Sincronización externa», read-only, sin botón de reintentar
commits      b5bfb84 · 62487db
```

**G7 es ahora sólo activar**, y en este orden: declarar `busca_caso` en el
catálogo del tenant → comprobar que funciona → recién entonces
`RECONCILIADOR_HABILITADO=1` y desplegar el servicio. El mecanismo existe entero. El reloj general sigue en ~60 min y **no
se tocó**: el worker tiene interruptor propio, para que encender uno no encienda
el otro por descuido.

Lo que sigue sin conectar, y es deliberado:

```
crear_ticket sin ejecutor      y no lo tendrá mientras Q2 siga rojo. Uno que
                               llegue hoy a la cola termina en
                               fallida_definitiva con 'sin_ejecutor', visible
sólo crear_caso se encola      los otros tres tipos existen en esquema y panel,
                               sin productor
falta declarar `busca_caso`    ningún tenant declara la herramienta de búsqueda.
en el catálogo                 Sin ella todo reintento intentaría crear — no es
                               inseguro (el 400 se maneja) pero conviene tenerla
                               antes de encender el worker
```

## B4 — lo que Q2 ya decidió

```
Q2                    🔴 ROJO, cerrado el 20/09/2026 (auditorias/B4-Q2-WISPHUB.md)
crear_ticket WispHub  NO es reintentable automáticamente: la API no acepta
                      clave de idempotencia, no hay filtro para buscar el
                      ticket, WispHub reescribe el asunto y el histórico se
                      recorta sin rango de fecha (tope 2 meses)
fallo incierto        → estado 'desconocida'. NUNCA se crea otro ticket
                      automáticamente: un ticket pendiente de revisión es
                      preferible a dos visitas técnicas al mismo cliente
crear_caso (CRM)      SÍ reintentable: el nombre incluye el conversation_id y
                      es único por organización; un repetido da 400 y se adopta
```

**La cola de B4 no puede diseñarse homogénea.** Los dos tipos de efecto tienen
estrategias distintas, y `desconocida` deja de ser un caso teórico del esquema
para ser el camino normal de la mitad de la cola. Eso arrastra dos cosas a
decidir antes de escribir la migración: dónde se muestra un pendiente de
revisión en la conversación, y que el reintento automático de `crear_ticket`
**no se escribe**, ni detrás de una bandera.

## G3 — VERDE. El camino de ejecución está cerrado

```
36 acciones de legado en 'pendiente' (34 create_ticket · 2 promise_payment),
sin conversation_id. SIGUEN pendientes: cancelarlas es trabajo de una persona
con la pantalla delante, y ese es el punto.
```

Cerrado en `5055c20` (motor) y `e67875b` (pantalla). Detalle en
`auditorias/G3-CIERRE.md`.

```
1. aprobar responde 409 y no llega al ejecutor. La guarda corre ANTES del
   chequeo de estado y de leer la config.
2. 'cancelada' es estado declarado, con motivo obligatorio y evento durable
   en la misma transacción (I12). Tabla nueva acciones_eventos: el
   conversation_id de relevo_eventos es NOT NULL y estas 36 no tienen.
3. /acciones-legado lista las pendientes. Sin botón de aprobar —ausente, no
   deshabilitado— y sin 'argumentos' (valores reales sin enmascarar).
```

El criterio de legado es **la falta de `conversation_id`**, nunca la edad ni el
tipo. Cuando B5 traiga la columna, la misma función deja pasar las que la
tengan sin tocarla.

**Lo que este gate NO hizo, a propósito:** tocar las 36 filas. El contrato pide
revisión humana una por una, no un `UPDATE` en lote. Las 2 de promesa de pago
quedan para revisión: si el cliente pagó no se puede saber sin consultar
producción, y no se consultó.

Migración `202609201400_acciones_legado.sql` **sin aplicar en producción**.

B5 queda desbloqueado.

## SIGUIENTE GATE

```
Branding   pantalla de ajustes, FUERA de la Fase 1
```

No es la Bandeja: es «Settings · Appearance & Branding», con subida de archivo,
almacenamiento de assets y alcance por organización. Hoy existe `Marca.logo_url`
en el esquema del tenant **sin ningún consumidor**, y nada más. Necesita su
propio scope.

Entrada: `SPEC/FASE_1_CHECKPOINT.md`.

## CONTRATOS CONGELADOS DE ESTA RAMA

No se reauditan sin evidencia nueva.

```
T6 · control = ia     sólo con wamid + estado_entrega='enviado' durables
T6 · sin optimismo    el control cambia sólo con devuelto_al_asistente === true
rechazado             ≠ incierto / sin_id / aceptado_sin_registro
unknown               conserva el control humano y NO ofrece reintentar
clave idempotente     una por intento; viaja con la burbuja junto a la intención
T7                    no es el recovery de T6
D28                   dueño del ticket CRM ≠ dueño durable de Dexter;
                      nombres iguales NO prueban identidad
ficha del cliente     Dexter guarda identidad + equipo y nada más (RNF-01);
                      no se consulta el ISP en vivo desde la Bandeja
acciones sobre el     no se ejecutan desde la Bandeja: reiniciar corta el
equipo                servicio y pasa por la cola con confirmación (PRD §7.4)
ACCION_CONFIRMADA     el equipo hizo lo pedido ≠ el cliente tiene internet
NO_VERIFICABLE        «no se pudo medir» ≠ «se midió y el efecto no está»
el ping               no es veredicto: medido, un equipo sano da 1/3, 2/3 y 3/3
bloqueo               ≠ error: el código frenando la acción es la protección
                      funcionando, y no ensucia la tasa de error
```
