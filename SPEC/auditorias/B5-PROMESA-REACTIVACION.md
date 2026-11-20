# Promesa de pago con reactivación — el mecanismo, cerrado

```
BASE       a17dd36 → (este commit)
VEREDICTO  mecanismo completo: política al proponer, revalidación al aprobar,
           confirmación por relectura. NO habilitado.
FECHA      21/09/2026
ALCANCE    código y pruebas. Sin tocar `tenant_config`, sin producción, sin push.
```

## Por qué existe esta acción aparte

Es la misma API que `agregar_promesa_pago` con `accion=1`. Va aparte porque
quien aprueba tiene que estar aprobando **«promesa + reactivar»**, no una
promesa a secas con una opción escondida. Una herramienta por efecto.

El origen fue un defecto real: `accion` la elegía el modelo, y el resumen que
lee quien aprueba no la nombraba. Se podía autorizar la reconexión de un
cliente suspendido sin que nada lo dijera.

## Las tres barreras, y qué mira cada una

```
al PROPONER     política determinista    ¿corresponde ahora?
al APROBAR      la misma política, de    ¿sigue correspondiendo? Entre las dos
                nuevo, releyendo todo    cosas pasa tiempo y el mundo se mueve
después         relectura del cliente    ¿el efecto ocurrió de verdad?
```

Ninguna reemplaza a las otras. La primera evita molestar a una persona con algo
que no procede; la segunda evita ejecutar sobre un mundo que ya cambió; la
tercera evita decir «se hizo» apoyándose en un 2xx.

## La política

`nucleo/facturacion/promesas.py`. **Función pura**: recibe hechos ya leídos y
devuelve uno de tres desenlaces. No habla con nadie, y hay dos aserciones que
lo fijan — ni `requests` ni `status_code` aparecen en el módulo.

```
elegible              se comprobó todo y se cumple
no_elegible           se comprobó y no se cumple  → revisión humana
no_se_pudo_comprobar  falta un dato               → NO se propone
```

Siete guardas: suspendido · una sola factura pendiente · vencida · plazo ≤ tope
· monto ≤ tope · espaciado desde la última promesa de Dexter. Cada una con su
motivo propio: «no elegible» a secas obliga a quien lo lee a abrir el código.

**Distingue AUSENTE de `None`** en el historial. `None` dice «consulté y no
hay»; ausente dice «no pude consultar». Tratarlos igual haría que una base
caída pareciera un cliente limpio.

## Los valores no se inventan

`dias_maximos_promesa`, `monto_maximo_promesa` y `dias_entre_promesas` nacen en
`None`. Son decisiones **comerciales**: cuántos días de gracia da un ISP no lo
puede decidir la plataforma. Sin ellos, `faltan_valores()` lo declara y la
acción no se ofrece.

**Rapilink no los cargó**, así que hoy la política devuelve `politica_sin_cargar`
y no se propone nada. Es el estado correcto, no un pendiente.

## Cómo se engancha sin que el motor conozca al tenant

La herramienta lo declara en el catálogo:

```yaml
politica:
  nombre: promesa_reactivacion
  lecturas: {factura: ..., cliente: ..., facturas: ...}
```

La **regla** es de plataforma y se elige por nombre; las **lecturas** son del
tenant. Si una falta o no es de sólo lectura, no se propone — misma regla que
§3.7 (X17): una comprobación declarada que no puede correr nunca autoriza nada.

**Aditivo e inerte:** sin `politica` declarada todo sigue igual.

La cadena empieza por la **factura**, no por el cliente: es lo único que trae
la propuesta del modelo. De ahí sale el slug —el objeto `cliente` de una
factura no trae `id_servicio`, medido— y con ese slug se piden estado y
facturas. Nunca por `id_servicio`: ese filtro está **medido como ignorado** y
devolvería las facturas de todos.

## La confirmación

Un 201 dice que el pedido se aceptó. Lo único que prueba el efecto es releer al
cliente. La respuesta distingue **tres hechos** y no los colapsa:

```
ok: true             el sistema externo aceptó el pedido
confirmado: true     además se releyó y el servicio está Activo
confirmado: false    se releyó y NO está  → no afirmar la reactivación
confirmado: null     no se pudo releer    → ni afirmarlo ni negarlo
```

**Máximo un POST por acción aprobada.** WispHub no permite consultar promesas
ni recuperarlas por referencia, así que un segundo intento no se podría
reconciliar con el primero. Misma regla que Q2 para `crear_ticket`. La garantía
la da la reserva condicionada de B5 (§9.3 paso 1), no algo nuevo.

Y la relectura confirma **el estado del servicio**, no que la promesa haya
quedado registrada. Eso último no se puede confirmar por ninguna vía.

## Tests

`tests/test_promesa_reactivacion.py`, sin red y sin base. Catorce secciones.

**Mutaciones: 20 probadas, 20 rojas** — 12 sobre la política y el productor,
8 sobre la revalidación y la confirmación.

### Tres mutaciones salieron verdes, y las tres eran el mismo error mío

Las tres pasaban porque yo afirmaba sobre el **texto del archivo** en vez de
sobre lo que las funciones devuelven. Es exactamente lo que CLAUDE.md documenta
—«afirmar sobre el efecto, nunca sobre la presencia del mecanismo»— y lo cometí
tres veces en la misma fase.

```
quitar el 'if' que corta la propuesta       → el test seguía verde
apagar la confirmación entera del endpoint  → el árbol de sintaxis ve la
                                              llamada aunque esté MUERTA
revalidar sin los argumentos de la acción   → la función real no se ejercitaba
```

Se corrigieron extrayendo `_salida_ejecutada_ok` y `_confirmar_efecto` del
endpoint —para poder ejecutarlas sin montar Flask— y espiando
`guardar_accion_propuesta` y `politicas.evaluar` con control positivo.

La lección concreta: **una prueba sobre el árbol de sintaxis demuestra que el
código está, no que se alcance.** Para lo segundo hay que ejecutarlo.

## BLOQUEOS

```
la herramienta NO se habilita   Rapilink no cargó su política, y falta decidir
                                si §3.7 se relaja explícitamente o la acción
                                queda deshabilitada

el punto ciego, permanente      WispHub no permite consultar promesas vigentes.
                                El espaciado sólo ve las que registró Dexter;
                                una cargada a mano en el panel es invisible y
                                ninguna guarda la va a ver. Por eso
                                `requiere_aprobacion_humana` nace en true y ahí
                                se queda: la persona que aprueba es la única
                                cobertura de ese hueco.

deuda anotada                   'Suspendido' y 'pendiente' son vocabulario del
                                proveedor viviendo en nucleo/. Con otro sistema
                                de facturación hay que moverlas a config.
```
