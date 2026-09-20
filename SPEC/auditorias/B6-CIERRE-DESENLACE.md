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

La transición cierra la conversación de Dexter y nada más. Hay una aserción que
lo mide —ninguna sincronización nueva— y otra que comprueba que no hay una
llamada a la cola escondida en el cuerpo.

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

**Mutaciones: 10 probadas, 10 rojas.** Entre ellas: el catálogo acepta
cualquier código; un desconocido cae a `otro`; el cierre manual sin código usa
`otro`; un automático guarda el desenlace que le manden; el plazo lo deja en
NULL; T15a/T15b dejan de mirar `atendida_manual`; también se cancelan las
`ejecutando`; cerrar una de legado la adopta.

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
T17 «cerrar también caso y ticket»  NO implementado. Las filas cerrar_caso /
                                    cerrar_ticket no tienen ejecutor (B4), y
                                    encolarlas hoy daría una fallida_definitiva
                                    en cada cierre sobre un caso que el camino
                                    en línea de hoy SÍ cierra: una alarma falsa.
                                    No se agregó una bandera que no hace nada.

completar el desenlace después      §3.5 dice que los cierres por el cliente y
                                    por inactividad dejan NULL «y se completan
                                    después si una persona revisa». Esa
                                    completada NO tiene transición en §6, ni
                                    tipo de evento en §3.3, ni precondición.
                                    NO se inventó.

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
