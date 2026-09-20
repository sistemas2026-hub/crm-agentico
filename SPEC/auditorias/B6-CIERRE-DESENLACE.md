# B6 — el cierre dice por qué

```
BASE       feature/bandeja-relevo, sobre df13919 (G8)
VEREDICTO  el cierre con desenlace queda cerrado en código. Desbloquea la
           tercera decisión de G8.
FECHA      20/09/2026
ALCANCE    código y pruebas. Producción no se tocó ni se consultó. Sin push.
```

## Lo que no existía

Una conversación se cerraba y de lo que le había pasado al cliente no quedaba
nada. `estado` pasaba a `cerrada` y se acabó: ni si era la ONT, ni si era
facturación, ni si lo había resuelto él solo, ni siquiera **quién** la cerró.
Cincuenta cierres por semana son cincuenta veces que nadie aprende nada, y la
bandeja queda limpia igual.

## El catálogo: dos niveles y una sola razón para que sean dos

`nucleo/relevo/desenlaces.py`.

**Doce códigos de plataforma**, en código, iguales para todo ISP. Cada uno es
también su propia categoría base. **La extensión es por empresa**, desde la
interfaz, y cada código propio declara a qué categoría base pertenece (I16).
`fibra_poste_17` le sirve al jefe de red de esa empresa; para la plataforma es
`red_distribucion`, y así las métricas siguen sumando entre empresas que le
ponen nombres distintos a la misma falla.

La base funciona **sin escribir config** (§3.5). Eso no es comodidad: escribir
`tenant_config` de Rapilink hoy partiría la medición ON vs OFF (Q3). Se
verificó que el YAML vigente sigue cargando con el esquema nuevo y que el
catálogo elegible le queda en 12 sin tocar nada.

**Lo que una empresa no puede hacer**, y falla al *cargar* la config, no de
noche con un cliente esperando:

```
redefinir un código base      'facturacion' significa lo mismo en todas partes
declarar uno sin categoría    no entraría a ninguna métrica y nadie lo notaría
apuntar a una categoría falsa no se corrige "cayendo a otro"
dejar el catálogo vacío       sus operadores no podrían cerrar a mano
```

Ocultar no es borrar: un código oculto sale de lo que se puede **elegir**, lo
ya cerrado con él conserva su categoría, y el cierre por plazo sigue
escribiendo `sin_respuesta_cliente` aunque esté oculto — ahí no hay ninguna
elección que ocultar.

## La transición

`transiciones.cerrar()`. Los cinco caminos de §6 en una sola puerta, y la
regla central escrita como guarda:

```
operador     T17   lo elige una persona. Sin código NO se cierra.
plazo        T16   'sin_respuesta_cliente' fijo. Otro código es un error.
cliente      T15a  NULL. Con 'atendida_manual'.
ia_cliente   T15b  NULL. Sin ella.
inactividad  T18   NULL. La columna lo admite; el productor es de otra fase.
```

**El desenlace no se infiere, nunca.** Deducirlo del veredicto del evaluador
era la tentación obvia —«resuelta» parece un desenlace— y sería falso: que el
cliente diga que ya funciona no dice si era la ONT, el WiFi o un corte de
fibra. Un dato inventado en la tabla que existe para aprender es peor que la
columna vacía. Por eso un código mandado por un camino automático se **rechaza**
en vez de guardarse.

T15a contra T15b se decide con la fila ya bloqueada, leyendo `atendida_manual`.
Es un hecho ya escrito, no una inferencia — y así los tres puntos del motor que
cierran por confirmación no tienen que adivinarlo cada uno por su lado.

### Atómico

Estado de cierre, desenlace, categoría, cancelación de las acciones pendientes
con sus eventos, y el evento `cerrada`: **una transacción** (I12). Probado con
falla inyectada: no queda la conversación cerrada sin que se sepa por qué, ni
una acción cancelada por un cierre que no ocurrió.

### Por qué se guarda la categoría y no sólo el código

Si la categoría se resolviera al **leer**, contra la config de hoy, una empresa
que renombra o retira un código propio reescribiría el pasado: los cierres de
hace tres meses cambiarían de categoría o dejarían de tener ninguna. Es la
misma razón por la que `datos_intencion` guarda lo que había que hacer y no se
reconstruye con la config actual (§3.6). Va en columna propia,
`desenlace_categoria_base`, y en el evento.

### Las acciones vivas se tratan distinto, y la diferencia no es de grado

Una `pendiente` espera a que alguien decida: cerrar la deja sin destinatario,
así que se cancela con su evento. Una `ejecutando` ya salió hacia afuera y su
desenlace lo escribe quien la ejecuta o el reconciliador (T20c); pisarla con
`cancelada` registraría que no se hizo algo que quizá sí se hizo — justo lo que
X21 prohíbe. Queda contada en el evento (`acciones_en_vuelo`), que es lo que
después explica una sincronización `desconocida` en una conversación que ya
nadie mira.

Los cierres **automáticos** no proceden con nada vivo (T15a/T15b/T16/T18, más
la verificación pendiente de D14). El **manual** sí: T17 dice «de inmediato» a
propósito, y una persona que decide cerrar no debería quedar bloqueada por una
propuesta que ella misma está por cancelar.

## Cerrar la conversación NO es cerrar el caso ni el ticket

La transacción cierra la conversación de Dexter y **anota la intención** de
cerrar el caso (§3.6). El pedido HTTP lo hace el reconciliador después, fuera
de la transacción: una TX abierta esperando una operación externa deja la fila
bloqueada y la sesión `idle in transaction` tras el pooler (X23). Hay
aserciones que lo miden.

El ticket de WispHub **no se encola**. Ver «El cierre externo» abajo.

## El cierre externo, auditado contra las APIs reales

El contrato dice «por defecto sí» para «cerrar también caso y ticket» (T17,
P5). Antes de convertir eso en llamadas, se midió qué permite cada API.

### `cerrar_caso` (CRM) — SEGURO, implementado

Se ejercitó el endpoint real:
`django-crm/backend/cases/tests/test_cierre_idempotente.py`, **7 pruebas en
verde** contra Django y PostgreSQL. Las cuatro capacidades existen:

```
escribir     PATCH /api/cases/{id}/ {status: Closed, closed_on}
verificar    GET /api/cases/{id}/ devuelve `status`
repetir      un segundo cierre responde 200, incluso con una regla armada:
             el gate de aprobación mira la TRANSICIÓN (old_status == Closed
             sale temprano), así que una regla nueva no rompe un reintento
rechazo      400 cuando falta una aprobación previa — legítimo y permanente
```

**Y un daño que sólo se ve ejecutándolo**: un PATCH sobre un caso ya cerrado
responde 200 y **reescribe `closed_on`** con la fecha del pedido. Nada falla;
el caso simplemente pasa a decir que se cerró un día en el que no se cerró, y
toda métrica de tiempo de resolución se corre con él.

Por eso el ejecutor **lee primero** y sólo escribe si sigue abierto — mismo
orden que `crear_caso` y por el mismo motivo. Después **relee siempre**: el
código de estado dice que el pedido se aceptó, no que el caso quedó cerrado
(disciplina de D28).

Hace falta una capacidad nueva del tenant, `lee_caso`. **Sin las dos
(`lee_caso` + `cierra_caso`) no se intenta nada**: con la de escribir sola se
podría escribir, que es exactamente lo que corre la fecha.

Un `incierto` aquí vuelve a la cola en vez de quedar `desconocida`, y esa es
toda la diferencia con Q2: aquí **sí hay a quién preguntar**.

### `cerrar_ticket` (WispHub) — NO automatizado

No por falta de tiempo. La única vía verificada para cerrar un ticket
(`POST /api/tickets/{id}/respuesta/`, con `ticket-estado: 4`, verificada en
producción el 28/08/2026) **publica un comentario en el mismo pedido**: cada
reintento le deja al cliente otra copia del texto de cierre en su ticket.

Y leer antes para evitarlo exige saber qué devuelve el GET. Nuestro propio
importador documenta la asimetría: **las lecturas vuelven como etiqueta**
(`"Cerrado"`) **y las escrituras van por código** (`4`)
—`cases/models.py::external_status`—. Ese vocabulario de etiquetas no está
verificado contra la API real, y verificarlo exige credenciales de producción.

Con eso, la regla del brief se aplica sola: **no se automatiza**. El cierre
manual que deja un ticket abierto lo dice en su evento (`ticket_pendiente`),
para que alguien lo vea. Es menos de lo que el contrato pide y más de lo que
había: callarlo dejaría el ticket vivo sin que nadie se entere.

No es lo mismo que Q2, y conviene no mezclarlos: Q2 es sobre **crear** un
ticket que después no se puede encontrar. Aquí el id se conoce; lo que falta es
poder cerrarlo sin escribirle al cliente de más.

## Completar el desenlace después del cierre

`transiciones.completar_desenlace()`. Es la frase de §3.5 que hasta ahora no
tenía transición: los cierres por el cliente y por inactividad dejan NULL «y se
completan después si una persona revisa».

```
sólo sobre NULL        una sola vez. Si ya tiene, 'ya_completado' → 409.
sólo cerradas          una abierta se cierra, no se completa.
operador autenticado   obligatorio, validado.
código visible         del catálogo de hoy; uno oculto se rechaza.
NO reabre              el estado no se toca.
NO cambia quién cerró  la cerró el cliente o el reloj. Completar el código
                       después no convierte a quien revisa en el que cerró, y
                       confundirlo rompe «cuántas cerró el cliente solo».
NO toca nada de afuera escribir un código en una fila no cambia nada en el CRM.
evento propio          'desenlace_completado', en la misma TX. No un segundo
                       'cerrada': dos se leerían como dos cierres.
```

El candado está en el propio UPDATE (`and desenlace_codigo is null`), no en una
lectura previa: dos revisores a la vez son lo normal, y el segundo tiene que
enterarse de que llegó tarde. Probado con dos hilos.

Sobre una conversación de legado escribe el dato pero **no sube la versión ni
deja evento**: adoptar una de versión 0 es una decisión humana explícita y esa
puerta es G8 y ninguna otra (C5, I21). El dato queda igual, que es lo que la
persona vino a dejar.

## La pantalla

`CierrePanel.svelte` reemplaza el `confirm()` de antes. **Ninguna opción viene
elegida**: ni la primera de la lista, ni la última que usó esa persona. Un
valor por defecto convierte cerrar en dos clics y llena la columna con lo que
eligió el formulario.

La lista viene del motor (`GET /conversaciones/desenlaces`), no de un array en
el frontend: una copia se desincroniza el día que una empresa agrega un código
propio. Hay una prueba que verifica que los códigos base **no** están escritos
en el archivo del frontend.

El botón deshabilitado va **con el motivo al lado**. Un botón apagado y mudo es
de las cosas que hacen que alguien recargue la página tres veces antes de
preguntar.

## G8: la tercera decisión

`cerrar_con_desenlace` pasa a `DECISIONES_G8_IMPLEMENTADAS`. Cierra **y**
adopta en la misma escritura: la adopción no es un trámite previo, es lo que
hace que ese cierre quede en el expediente del relevo con quién lo decidió
—lo que §11.2 pide y lo que el botón de siempre no deja, porque sobre una
conversación en versión 0 no escribe ningún evento.

El evento `cerrada` lleva `legado: true` y `g8: cerrar_con_desenlace` junto al
desenlace. Sin esas dos claves nadie podría distinguir, dentro de un año, un
cierre normal de una decisión de la revisión de G8.

`cli/decidir_g8.py` toma `--desenlace` y `--nota`. Si falta o no está en el
catálogo, imprime los códigos válidos y **no sugiere ninguno**.

## Tests

`tests/test_b6_cierre_desenlace.py`, contra PostgreSQL real (`b6_limpia`,
construida desde cero por el ledger: 53 archivos, 0 checksum distinto).

```
el catálogo, I16 y el ocultamiento                    18 aserciones
la config falla cerrado                                2
T17 completo, y los tres rechazos                     19
los cinco caminos y los cinco rechazos                17
acciones vivas y verificación pendiente                9
el cierre no toca los sistemas de afuera               3
atómico, idempotente, concurrente, por empresa        14
legado: se cierra, no se adopta                        3
G8 cerrar_con_desenlace                               10
los CHECK de la base                                   4
```

Más ~45 sobre completar el desenlace (sección 10) y la cola de `cerrar_caso`
en `tests/test_b4_sincronizaciones.py`, y **7 contra el CRM real** en
`django-crm/backend/cases/tests/test_cierre_idempotente.py`.

**Mutaciones: 21 probadas, 21 rojas.** Entre ellas: el catálogo acepta
cualquier código; un desconocido cae a `otro`; el cierre manual sin código usa
`otro`; un automático guarda el desenlace que le manden; el plazo lo deja en
NULL; T15a/T15b dejan de mirar `atendida_manual`; también se cancelan las
`ejecutando`; cerrar una de legado la adopta; completar pisa el desenlace que
ya estaba; completar se apropia del cierre ajeno; el cierre encola
`cerrar_ticket`; `cerrar_caso` escribe sin leer antes; da por bueno sin releer;
se intenta sin la capacidad de leer.

Regresión: **9 de 9** suites del relevo en verde contra la misma base, más la
guarda de arquitectura y el editor de config. Frontend: 242 pruebas en verde,
15 nuevas.

### Dos cosas que encontraron las mutaciones, y una que encontró la regresión

1. Dos de las diez mutaciones salieron **verdes** en la primera pasada. Una era
   código redundante (dos comprobaciones para el mismo efecto); la otra, un
   hueco real: nada probaba que un código **oculto** no se pudiera elegir al
   cerrar. Se agregó la aserción y la mutación quedó roja.

2. La regresión destapó un sustituto de prueba que quedó desfasado desde B5:
   `guardar_accion_propuesta` devuelve `(id, ya_existia)` desde T12 y el
   reemplazo de `test_relevo_efectos.py` devolvía sólo el id. El test venía
   fallando y no era de B6.

3. **Sexta vez el mismo patrón propio**: la aserción de G8 «ningún módulo del
   motor llama a la adopción» buscaba la cadena en el archivo entero, y se puso
   roja por un docstring nuevo que dice —justamente— que cerrar una de legado
   NO la adopta. Reescrita sobre el árbol de sintaxis: mide llamadas, no
   menciones.

## BLOQUEOS

```
cerrar_ticket (WispHub)             NO automatizado, con la razón medida
                                    arriba: la única vía verificada publica un
                                    comentario en cada intento, y el GET
                                    devuelve etiquetas cuyo vocabulario no está
                                    verificado. Queda visible en el evento.
                                    Para levantarlo hace falta, contra la API
                                    real y con el método del valor imposible:
                                    (1) qué devuelve GET /api/tickets/{id}/ en
                                    el campo estado, y (2) si existe alguna vía
                                    de cierre que no publique un comentario.

lee_caso                            capacidad NUEVA del tenant. Sin ella (y sin
                                    cierra_caso) la cola no cierra casos: queda
                                    'fallida_definitiva' con su código, visible.
                                    Declararla en el catálogo es trabajo de G7,
                                    que ahora tiene CINCO capacidades, no cuatro.

pantalla para completar             el endpoint y el proxy existen y están
                                    probados; no hay todavía una vista que liste
                                    las cerradas sin desenlace para revisarlas.

T18 (inactividad)                   la columna lo admite y la transición lo
                                    acepta, pero el productor sigue siendo el
                                    cierre por resumen de db.py. Fuera del
                                    alcance de B6 según la hoja de ruta.

resolver_estado_externo (G8)        sigue bloqueada: B4 sin productor y
                                    cerrar_ticket bloqueado por Q2.

svelte-check                        no se corrió: con Docker arriba en Windows
                                    rompe el frontend, y no hay contenedor del
                                    frontend levantado para hacerlo por dentro.
```
