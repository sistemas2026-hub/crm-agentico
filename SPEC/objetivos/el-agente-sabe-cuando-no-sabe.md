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
| 4 | Los 56 casos dorados no empeoran | `py -3.13 cli/evaluar.py rapilink --base`, salida pegada, comparada contra una corrida previa del mismo día (§6: una sola corrida no separa regresión de varianza) |
| 5 | La abstención se MIDE, no se declara | contra el corpus sintético de 20 trampas (12 ambiguas / 8 claras). Hoy da `0 de 12`; terminado es un número distinto de cero, con las 8 claras sin romperse |

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
