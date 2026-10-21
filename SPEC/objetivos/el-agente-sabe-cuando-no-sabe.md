# Objetivo · El agente sabe cuándo no sabe

> Abierto el 20/10/2026. Estado: **abierto**.

## Qué significa terminado

La decisión de escalar deja de ser un sí/no y pasa a declarar **cuánta
confianza tiene**, de modo que «no molesto a nadie» y «no sé si molestar a
alguien» dejen de ser el mismo resultado.

## Por qué este, y por qué primero

El objetivo que lo originó es del usuario, el 20/10/2026, con estas palabras:
*«quiero reemplazar un supervisor humano por un agente de IA»*, con la frontera
en *«que no pida autorización, que solo pida para cosas que no tienen
reversa»*, cobertura **24/7 con el humano como excepción**, y la medición
**en sombra, aprendiendo hasta llegar a ser autónomo**.

De ahí sale una sola pregunta previa a todo lo demás: **si el humano es la
excepción, ¿cómo sabe el agente cuándo invocarlo?**

Hoy no puede decirlo, y no es un fallo de criterio sino de **forma de la
salida**. Medido sobre el código el 20/10/2026:

```
nucleo/seguimiento/escalamiento.py:149
    "escalar": { "type": "boolean", ... }
```

Un booleano no tiene dónde alojar una duda.

Y hay número: la evaluación de Jev/TypeSafe (rama local
`objetivo/decisiones-estructuradas`, `cli/varianza_evaluador.py`, 88 casos × 5
corridas = 440 llamadas) midió que **el evaluador decide distinto con la entrada
idéntica**:

| Campo | Casos que se mueven |
|---|---|
| **`escalar`** — decide si interviene una persona | **6 de 88** |
| `etiqueta` | 8 de 88 |
| `motivo` | 36 de 88 |
| `termino` | 0 de 88 |

Y contra 12 casos escritos a mano como ambiguos: **0 de 12 abstenciones**. El
cero **no es un criterio, es una imposibilidad**: no existe la salida con la
que decir que no sabe.

**El caso peligroso no es el que despierta de más.** Es `escalar: false` con
confianza baja: el agente decide no molestar a nadie y no está seguro. Hoy eso
es indistinguible de un «no» firme, y a las 3 de la mañana nadie lo revisa.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | La decisión declara confianza, con el vocabulario que el sistema YA usa (`alta`/`media`/`baja`, de `operaciones/paso_a_despacho.py:119`) — no una escala nueva | `grep -n '"confianza"' nucleo/seguimiento/escalamiento.py` muestra el campo en el esquema y en `requeridos` |
| 2 | Una guarda que mata la mutación: quitar `confianza` de `requeridos` tiene que poner una prueba en rojo | correr la prueba con la mutación aplicada, y pegar el rojo |
| 3 | `cli/evaluar.py rapilink --humo --base` **no empeora** respecto de la línea base | línea base del 19/10: `8/9 OK (89%)`, con el caso de ventas como rojo conocido. Pegar la salida |
| 4 | El set dorado completo no empeora | `py -3.13 cli/evaluar.py rapilink --base --json <archivo>`, **con `--json`**: sin él la salida se trunca y queda el total sin los casos, que es lo que pasó el 20/10. Son **90 casos, no 56** (medido ese día: `86/90 OK (96%)`); CLAUDE.md todavía dice 56 en varios lugares. Comparado contra una corrida previa del mismo día — §6: una sola corrida no separa regresión de varianza |
| 5 | La abstención se MIDE, no se declara | contra el corpus sintético de 20 trampas (12 ambiguas / 8 claras). Hoy da `0 de 12`; terminado es un número distinto de cero, con las 8 claras sin romperse |


## Lo medido el 20-21/10/2026

### La escalada: el campo se usa

```
cli/medir_abstencion.py rapilink        (corpus sintetico, 20 casos)

  ambiguos  (debia abstenerse)     8 de 12
  claros    (NO debia)             8 de 8
  reparto: alta 11 · media 1 · baja 8
```

Antes era `0 de 12`, y **ese cero era una imposibilidad**: `escalar` era un
booleano y no existía la salida con la que decir «no sé».

**Pero ese número mide una correlación, no lo que el criterio pedía.** El
corpus etiqueta ambigüedad de **ruteo** —sus doce casos listan ÁREAS en
`veredicto.entre`— y `confianza` califica a `escalar`. Que coincida en 8 de 12
dice que la duda sobre la cola arrastra a la de escalar, que es razonable.

### El router: el campo existe y casi no se usa

```
cli/medir_abstencion_del_router.py rapilink   (el turno ENTERO, no el decisor suelto)

  AMBIGUOS (12)
     no derivó  -- preguntó primero       6     <- bien resuelto
     derivó SIN dudar                     6     <- el error caro
     derivó Y dijo que dudaba             0

  CLAROS (8)
     derivó sin dudar                     6     <- lo correcto
     derivó dudando                       0

  reparto de los que derivaron: alta 10 · media 2 · baja 0
```

**El titular «0 de 12» es engañoso y conviene no repetirlo.** El router nunca
dice `baja`, es cierto — pero **en la mitad de los ambiguos no deriva: pregunta
primero**, y eso resuelve la ambigüedad igual de bien o mejor. El número
honesto es **6 bien y 6 mal**.

Los 6 que fallan, con a dónde los mandó:

```
trampa_cancelar_que        -> facturacion_cliente      (el corpus: comercial | facturacion)
trampa_no_me_funciona      -> soporte_tecnico_cliente  (soporte_tecnico | facturacion)  [media]
trampa_es_sobre_el_cobro   -> facturacion_cliente      (facturacion | queja)
trampa_dos_areas_a_la_vez  -> facturacion_cliente      (facturacion | soporte_tecnico)
trampa_suspender_un_mes    -> facturacion_cliente      (comercial | facturacion)        [media]
trampa_mandame_el_recibo   -> facturacion_cliente      (facturacion | queja)
```

**La hipótesis, que es hipótesis y no medición:** pedirle la confianza en la
misma llamada donde se le exige elegir un área empuja hacia la seguridad. Ya
eligió al llamar la herramienta; calificarse bajo después se contradice. En la
escalada no pasa porque «no sé si hace falta una persona» es una respuesta
coherente consigo misma.

**Qué se haría con eso, y por qué todavía no se hizo:** decirle que si fuera a
calificar `baja`, no derive y pregunte — que es lo que ya hace bien la mitad de
las veces. Es barato, pero **cambia conducta en conversaciones reales** (más
preguntas, menos derivaciones) y varios casos dorados afirman `deriva_a`. Pide
su propia medición antes y después, no un cambio al pasar.

### Lo que esto deja dicho sobre el objetivo

El mismo campo, el mismo vocabulario y la misma descripción se usan **en un
lugar sí y en el otro casi no**. Eso es evidencia directa de lo que la
documentación de TypeSafe dice y este proyecto ya tenía escrito con otras
palabras: **la confianza no es permiso para actuar, y tampoco es una propiedad
del modelo — es una propiedad de CÓMO se le pregunta.**


## Lo que NO se toca en el camino

- **La conducta sin la bandera.** El campo se agrega, pero **nada cambia de
  decisión** hasta que alguien lo encienda: mismo patrón que el paso a Despacho
  y que las correcciones del usuario — primero en sombra.
- **El caso de ventas** (`una venta a un prospecto no verifica identidad`):
  decidido el 19/10 dejarlo documentado. Es la línea base, no una regresión.
- **La frontera de los 8 pasos**, el interruptor y el techo. Esto no concede
  autonomía: le da a la decisión una forma de pedir ayuda.
- **Jev.** Entra después y detrás de su gate legal (§5: la autorización de
  tratamiento nombra al proveedor; hay una consulta redactada **sin enviar**).
  Este objetivo es su prerequisito, no su reemplazo: sin un campo donde alojar
  una confianza, la respuesta de Jev no tendría dónde ir.

## Bloqueos

| Qué | Estado |
|---|---|
| El corpus de 20 trampas y `cli/varianza_evaluador.py` | Viven en la rama local `objetivo/decisiones-estructuradas` (tip `ccb08489`, 06/10), que está ~2 semanas detrás. **Se traen los archivos, no se fusiona la rama** |
| Etiquetar 11 casos reales a mano | Necesita una persona. No bloquea este objetivo: el corpus sintético alcanza, y es la única excepción medida al gate legal |
| Enviar la consulta al proveedor (paso 0 de Jev) | Redactada, sin enviar. Bloquea a Jev, **no** a este objetivo |

## Lo que viene después, y en este orden

Del punto de vista dado al usuario el 20/10, y con su razón:

1. **Esta ficha** — la abstención. Prerequisito de todo.
2. **Volver imposibles dos errores, por diseño y no por umbral**: que el agente
   nunca diga una fecha hasta que la orden esté asignada en una jornada
   publicada, y que cerrar siga con puerta humana. Baratos.
3. **Preguntarle al cliente antes de despachar.** Es lo único que gana de
   verdad contra un humano —un supervisor no le puede escribir a 40 clientes,
   un agente sí— y disuelve la tensión entre los dos errores opuestos que el
   usuario pidió evitar a la vez («visita de más» y «cliente sin atender»),
   que por aritmética no se pueden bajar los dos con un umbral.
4. **Recién ahí, subir la autonomía, de noche primero** — donde la alternativa
   hoy no es un supervisor humano: es nadie.

Los pasos 2 y 3 **bajan el costo de equivocarse**, y la autonomía es mucho más
barata de conceder cuando equivocarse cuesta poco.
