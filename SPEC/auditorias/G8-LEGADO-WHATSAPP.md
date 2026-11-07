# Gate G8 — las conversaciones de legado que quedarían esperando a alguien

```
BASE       a010d47
VEREDICTO  G8 ROJO. La herramienta está lista y probada; las 16 no se revisaron.
FECHA      20/09/2026
ALCANCE    preparación. Producción no se tocó ni se consultó.
```

## Por qué ROJO, y no es una formalidad

Hay **dos** bloqueos, y ninguno se resuelve escribiendo más código.

**1. Los datos están en producción y no hay autorización para leerlos.** Las 16
conversaciones viven ahí. Sin leerlas no hay revisión, y leer producción no
estaba autorizado en este trabajo.

**2. La decisión no es de la IA.** El contrato (§11.2) es literal:

> una persona las revisa **una por una** y decide para cada una: seguir en
> humano, cerrar (con desenlace), resolver el estado externo o volver a la IA.
> **No se ocultan ni se resuelven automáticamente.**

Aun con los datos delante, clasificarlas A/B/C no cerraría G8. El gate pide una
decisión humana por conversación, y esa decisión queda como evento del relevo
(`datos = {"legado": true, "g8": <decision>}`).

Así que lo que se podía hacer hoy era **dejar la revisión lista para que esa
persona la haga**, y eso está hecho.

## La herramienta (`cli/revision_g8.py`)

Solo lectura. No escribe, no adopta, no cierra, no ejecuta nada — y hay
aserciones que lo demuestran, no un comentario que lo promete.

Por cada candidata trae: canal, estado, control y motivo, `tomada_por`,
`caso_id`, si hay ticket, conteo de mensajes, cuántos del cliente quedaron sin
respuesta, y cuántos días lleva esperando.

**No trae el contenido de los mensajes ni `autor_nombre`.** Quien revisa
necesita saber de qué va cada hilo, y para eso está la bandeja: ahí se lee
entero, en contexto, y el acceso queda auditado. Volcar 16 conversaciones de
clientes a un archivo de trabajo es exactamente lo que este proyecto no hace con
los datos de nadie. Hay una prueba que siembra una cédula dentro de un mensaje y
exige que no aparezca en la salida.

### La selección es la misma regla del backfill

```sql
estado = 'abierta' and escalada_a_humano and necesita_atencion_humana
and coalesce(relevo_version, 0) = 0
```

Es §11.2 tal cual. Si la consulta de revisión y la del corte se separaran, se
estaría revisando un conjunto distinto del que el cutover va a producir — y
nadie lo notaría hasta después. Cinco aserciones lo fijan, una por cada
condición.

Los canales de prueba (los 30 de A6) se **separan**, no se mezclan: siguen el
mismo modelo pero su política es otra decisión. Con `--incluir-pruebas` se
cuentan aparte.

## La clasificación A/B/C es una SUGERENCIA

No una decisión. Sirve para ordenar el trabajo de quien revisa, y el criterio no
mira el contenido: mira si adoptarla **afirmaría algo que no se puede
demostrar**, que es el único motivo por el que una adopción automática hace daño.

| | Cuándo | Por qué |
|---|---|---|
| **C** | escalada sin caso ni ticket | El efecto externo se perdió en su momento. Adoptarla dejaría a alguien «a cargo» sin nada del otro lado, y adoptar no lo recupera. |
| **B** | `tomada_por` con un nombre y sin id de usuario | El backfill copiaría el nombre con `asignada_a_usuario_id = NULL`. Es lo que §11.2 permite, pero deja una asignación que no identifica a nadie. Un nombre no prueba identidad (D28). |
| **B** | el cliente escribió después de la última respuesta | Alguien está esperando ahora mismo. |
| **B** | nadie la tomó y lleva 7+ días | Es la situación que G8 existe para mirar. |
| **A** | con caso, sin dueño ambiguo, sin cliente esperando | El legado y el modelo dicen lo mismo. |

## Tests

`tests/test_g8_revision_base.py`, contra PostgreSQL real con conversaciones
**sintéticas** que reproducen cada caso límite.

```
selecciona exactamente lo que el backfill va a tocar   5 aserciones
los canales de prueba se separan                       2
la sugerencia distingue los cinco casos                5
revisar() no cambia UNA SOLA FILA                      retrato antes/después
no sale el contenido, ni la cédula, ni el autor        5
el código no contiene insert/update/delete/alter       4
```

**Mutaciones: 6 probadas, 6 rojas.** Entre ellas: la regla deja de exigir
`abierta`; entran las ya gobernadas; los canales de prueba se mezclan; una
escalada sin caso se da por segura; el informe saca el contenido de los
mensajes.

Un error propio: la aserción «ninguna conversación cambió» comparaba contra un
estado esperado, y contaba también las filas que la propia prueba había sembrado
con `relevo_version = 3`. Reescrita para comparar un retrato de la base **antes
y después** de llamar a `revisar()` — que mide el efecto, no el estado.

## G8: ROJO

```
hecho      la herramienta de revisión, probada, sin PII y sin escrituras
           el criterio de clasificación, con su porqué
           la transición de adopción y el comando que la usa, con evento
           durable — TRES de las cuatro decisiones desde B6; la cuarta
           (resolver_estado_externo) sigue bloqueada
falta      leer las 16 reales (necesita autorización de lectura de producción)
           que una persona decida cada una
           registrar cada decisión como evento del relevo
```

Mientras G8 siga rojo, **no hay corte de control**: B3 lo tiene como gate, y
`relevo_version = 0` no se adopta por un clic ni por un UPDATE anónimo (C5, I21).

## El registro durable de la decision (df13919)

Ya hay donde escribir lo que una persona decida. Antes no lo habia: ninguna
transicion adoptaba una conversacion de legado, y el esquema de eventos no
admitia las claves que §11.2 pide.

`transiciones.adoptar_de_legado()` es la unica via por la que una conversacion
con `relevo_version = 0` entra al modelo fuera de escalar e intervenir (C5,
I21). Transicion y evento en la misma transaccion: si el evento falla, no queda
una conversacion adoptada sin quien ni por que — probado con falla inyectada.

```
seguir_humano   control humano + motivo escalada, asignada_a_nombre = tomada_por
                y asignada_a_usuario_id NULL. Evento escalada.
volver_ia       control ia, banderas de legado apagadas en la misma escritura.
                Evento devuelta_a_ia.
```

Los dos con `datos = {legado: true, g8: <decision>}`. Sin esas claves nadie
podria distinguir, dentro de un año, una escalada real de una adopcion
administrativa.

**El id del usuario queda NULL a proposito.** `tomada_por` es un nombre, y un
nombre no prueba identidad: inventar el id le atribuiria a una persona concreta
una conversacion que quiza no es suya — el mismo error que D28 existe para no
cometer. Es lo que §11.2 manda.

### cerrar_con_desenlace: desbloqueada por B6 (20/09/2026)

B6 trajo las columnas de cierre y el catalogo de desenlaces, asi que la tercera
decision ya se puede registrar. Cierra **y** adopta en la misma escritura, con
el codigo que la persona elige — y sin codigo sigue sin cerrar: que la
conversacion sea vieja no la hace menos de un cliente.

```
cerrar_con_desenlace   estado cerrada, cerrada_por_tipo 'operador' con su
                       usuario, desenlace + categoria + nota, evento 'cerrada'
                       con legado, g8 y el desenlace.
```

Ver SPEC/auditorias/B6-CIERRE-DESENLACE.md. El comando toma `--desenlace` y
`--nota`; si el codigo falta o no esta en el catalogo, imprime los validos y
**no sugiere ninguno**.

### La que TODAVIA no se puede registrar, y por que

```
resolver_estado_externo   no es una transicion del relevo, es un efecto externo
                          (cerrar_caso / cerrar_ticket), sin productor y con
                          cerrar_ticket bloqueado por Q2
```

Se rechaza con su motivo en vez de hacer algo parecido: quien revise creeria
que decidio algo que el sistema no guardo.

### El comando

`cli/decidir_g8.py`, una conversacion por invocacion. No acepta `--todas` ni
`--desde-archivo`, y `--conversacion` toma una sola: §11.2 dice **una por una**,
y un comando en lote lo volveria el tramite que el gate existe para impedir.

La clasificacion A/B/C no llega a ninguna escritura: `revision_g8.py` ni
nombra la adopcion, y ningun modulo del motor la llama por su cuenta.

Seis mutaciones mas, seis rojas. Concurrencia real: de dos operadores
decidiendo a la vez gana uno, con un solo evento y la version en 1.

## Lo que hace falta autorizar

Una lectura de producción, acotada: `conversations` y un conteo sobre
`messages`, sin contenido. Es lo que la herramienta consulta y nada más. Con eso
sale el informe de las 16 y la revisión puede empezar.
