# Gate G3 — las 36 acciones de legado

```
BASE       98fa785
VEREDICTO  G3 ROJO — no se puede cerrar todavía, y el camino peligroso está abierto
ALCANCE    auditoría del mecanismo. Sin tocar producción.
FECHA      20/09/2026
```

## Lo que el contrato ya decidió

§11.4 fija la política, y no hay nada que discutir ahí:

```
obsoletas o de prueba   → cancelada, con evento y motivo
todavía necesarias      → NO se aprueban tal cual: se vuelven a proponer desde
                          el contexto actual (con conversation_id) y pasan por
                          la revalidación de §3.7
ninguna                 se ejecuta automáticamente, ni por aprobación, ni por
                        reconciliador, ni por migración (X24)
```

Lo que falta no es la decisión: es que el sistema permita ejecutarla.

## Bloqueo 1 — el camino peligroso está abierto HOY

`POST /acciones/propuestas/<id>/aprobar` (`api.py:5534`) hace, en este orden:

1. lee la acción,
2. comprueba **sólo** que esté `pendiente`,
3. **ejecuta la escritura real contra la API externa**,
4. la marca `aprobada`.

**No valida `conversation_id`** — y no podría: la columna no existe en
`acciones_propuestas` (llega en B5). Así que las 36 se pueden aprobar y
ejecutar hoy mismo desde ese endpoint.

Y ejecutar una de ellas es peor de lo que parece:

```
34 create_ticket   crearían tickets reales en WispHub por problemas de hace más
                   de 7 días. Con Q2 en rojo no hay forma de detectar que el
                   ticket ya existía ni de deshacerlo: es exactamente el caso de
                   las dos visitas técnicas al mismo cliente.
 2 promise_payment ejecutarían una promesa de pago con la fecha límite vencida.
```

Ninguna llevaría revalidación, porque §3.7 todavía no existe: es B5. Se
ejecutarían con los argumentos congelados de hace más de una semana.

## Bloqueo 2 — nadie puede revisarlas

G3 dice «una persona revisa las 36». **No hay pantalla**: cero referencias a
`acciones/propuestas` en todo el frontend. El endpoint de lectura existe
(`GET /acciones/propuestas`) y nada lo consume.

Sin superficie, la revisión humana que el gate exige no se puede hacer — ni
siquiera para decidir cuál cancelar.

## Bloqueo 3 — `cancelada` no existe como estado declarado

La columna `estado` es **texto libre**: no tiene `check`, y su comentario dice
`-- pendiente|aprobada|rechazada`. Así que `cancelada` se puede escribir sin
migración… y también se puede escribir cualquier otra cosa.

Hoy lo más cercano es `rechazada` con `motivo_rechazo`. **Funcionalmente es
seguro** —no ejecuta nada— pero pierde la distinción que el contrato quiere:
rechazada es «alguien la evaluó y dijo que no»; cancelada es «quedó obsoleta».
En un registro que existe para auditar, no es lo mismo.

Tampoco hay evento: §11.4 pide «`cancelada`, con evento y motivo», y
`acciones_propuestas` no escribe en `relevo_eventos`.

## Bloqueo 4 — los datos están en producción

Las 36 filas viven en la base de producción. No se consultaron: no se conecta
producción desde acá. La clasificación de abajo es **por tipo**, con lo ya
medido (A5), no por inspección de cada fila.

## Propuesta de reconciliación

**Ninguna se aprueba.** Ni las que parezcan vigentes: el contrato es explícito
en que una acción todavía necesaria se vuelve a proponer, no se aprueba tal
cual. Aprobar es ejecutar, y ejecutar con argumentos de hace 7+ días sin
revalidación es lo que X24 prohíbe.

| Clase | Qué se propone | Por qué |
|---|---|---|
| 34 `create_ticket` | **cancelar todas** | Con Q2 rojo, crear el ticket hoy es irreversible y sin forma de detectar duplicado. Si el problema sigue vivo, la conversación actual lo vuelve a proponer con `conversation_id`. Un ticket de más cuesta una visita; uno de menos, una queja que ya existe en la conversación. |
| 2 `promise_payment` | **cancelar, y mirar antes si el cliente pagó** | Una promesa con fecha límite vencida no se ejecuta. Pero son dos: revisarlas a mano es barato, y si alguna sigue en pie se propone de nuevo. |

El orden importa: **primero cerrar el camino de ejecución, después cancelar.**
Cancelar 36 filas mientras el endpoint sigue permitiendo aprobar no elimina el
riesgo, sólo lo reduce.

## Lo que hay que construir antes de poder cerrar G3

```
1. Que aprobar RECHACE una acción de legado
   Sin conversation_id (o con un marcador equivalente mientras la columna no
   exista), el endpoint responde 409 y no ejecuta nada. Es la traducción
   literal de X24 y no depende de B5.

2. Estado 'cancelada' declarado
   Con su check, o al menos con la constante en un solo lugar. Y el evento con
   motivo que §11.4 pide.

3. Una superficie para revisarlas
   Puede ser mínima: 36 filas, tipo, resumen, antigüedad y un botón de
   cancelar. Sin botón de aprobar.
```

Los tres son chicos. Ninguno necesita B5 ni migración de `conversation_id`.

## G3: ROJO

No por lo que falta decidir —el contrato ya lo decidió— sino porque **el
mecanismo permite hoy exactamente lo que el gate existe para impedir**, y
porque no hay superficie para hacer la revisión que exige.

Y conviene decirlo con precisión: G3 bloquea B5, pero el **bloqueo 1 no puede
esperar a B5**. Mientras el endpoint de aprobar no distinga una acción de
legado, cualquiera con acceso al motor puede crear 34 tickets con 34 peticiones.
