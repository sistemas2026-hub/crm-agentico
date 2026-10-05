# Pedir material a bodega desde la calle

**Estado:** construido y medido · 05/10/2026
**Dónde vive:** `lib/features/materiales/pedir_a_bodega.dart` (app) ·
`django-crm/backend/campo/pedidos.py` + `pedidos_views.py` (servidor)

---

## El problema

El técnico se queda sin conectores en la tercera instalación y la aplicación no
tenía nada que ofrecerle: sacaba el otro teléfono y escribía al grupo. La
pantalla de Materiales le decía lo que tiene, y ahí se cortaba.

El botón que ocupaba ese lugar —**«Transferir»**— estaba dibujado **sin acción**
desde que la pantalla se replicó del diseño. Un botón que no responde enseña a
no confiar en la barra entera, así que el pedido reemplaza a ese, no se agrega
al lado.

---

## La decisión que ordena todo: un pedido NO es un movimiento

Está escrita en `campo/models.py` y sostiene al inventario completo:

> Un movimiento de material **ES UN HECHO QUE YA OCURRIÓ** en la calle, no una
> solicitud que el servidor pueda aprobar.

De ahí salen el append-only, el saldo calculado y el descuadre que se acepta
igual. Un pedido es exactamente lo contrario: todavía no pasó nada, alguien lo
tiene que atender, y puede decir que no.

Por eso hay **tabla propia a los dos lados**:

| | Movimiento | Pedido |
|---|---|---|
| Servidor | `campo_movimiento_material` | `campo_pedido_de_material` |
| Teléfono | `cola_movimientos_material` | `cola_pedidos_material` (v22) |

Compartirlas rompería la única afirmación que sostiene a la primera, y el
primer síntoma sería **un saldo que cuenta material que nadie entregó** — un
descuadre de fin de mes imposible de explicar.

Medido: `pedir_a_bodega_test` B2 y B10, `test_pedido_de_material` D1.

---

## Se identifica por **código**, no por UUID

El kit que baja la aplicación trae `codigo`; es lo que ya manda la cola de
movimientos. El endpoint acepta los dos, pero **el código es el camino real**.

Exigir el UUID habría dejado la pantalla con el dato con el que no se puede
preguntar: el botón existiría y el pedido nunca se podría hacer. Medido:
`test_a6_se_pide_por_CODIGO_que_es_lo_que_el_telefono_tiene`.

Un texto que no es un UUID entraba al `filter(id=…)` y reventaba la consulta:
el técnico veía «error del servidor» por haber pedido algo que simplemente no
está en el catálogo. Ahora es 404. Medido: `test_a7`.

---

## La idempotencia, y lo que no promete

La clave es el **`id` de la fila local**, generado al encolar, y viaja en el
cuerpo como `idempotency_key`. Un reenvío sin señal es **el mismo pedido**.

> Una clave nueva por intento es un identificador único, **no** una clave
> idempotente. — `CLAUDE.md` §12

Del lado del servidor es `UniqueConstraint(["org", "idempotency_key"])`: por
clave primaria, nunca por un `select` previo, que es donde vive la carrera.

**El reenvío se responde 200, no 409.** Para la cola de la app un error es
motivo de reintento: un 409 la dejaría reintentando para siempre. Medido:
`test_b2`, `subir_pedidos_test` caso 2.

**Reencolar un id ya enviado no lo reabre** (`ConflictAlgorithm.ignore`, no
`replace`). Con `replace`, un pedido que bodega ya recibió volvería a
`pendiente` y se mandaría de nuevo: el duplicado entraría por la puerta de al
lado. Lo cazó una mutación — la prueba B6 sola no lo veía. Medido: B6b.

---

## Los tres estados, y por qué se dicen distinto

| Estado | Lo que ve el técnico | Por qué |
|---|---|---|
| `pendiente` | «Sube cuando haya señal» | Se pidió, todavía no salió del teléfono |
| `enviado` | «Bodega ya lo recibió» | Salió y el servidor lo tomó |
| `fallido` | «No se pudo pedir» | Un 400/404: daría el mismo resultado para siempre |

Una sola frase («pedido») dejaría a un pedido fallado pareciendo que está en
camino, **y el técnico lo espera**. Eso es peor que no haber pedido.

Un pedido fallado **no se borra**: queda con su motivo a la vista, que es lo
único que puede destrabarlo. Una fila que desaparece se lee como «no se mandó».

**Un 400 o un 404 son definitivos; un corte de red no.** Reintentar un 400 es
ruido; perder un pedido por falta de red es perderlo siempre. Medido:
`subir_pedidos_test` casos 3, 4 y 5.

---

## Se ve que se pidió

La tira «Pedidos a bodega» aparece en Materiales **sólo si hay pedidos**.

Sin ella, un pedido encolado no produce ninguna señal visible: el técnico
vuelve a pedir lo mismo —o deja de pedir creyendo que ya pidió—. La
idempotencia evita el duplicado del lado del servidor; esta tira evita la duda
del lado de la persona, que es **otro problema**.

Una tira vacía que dijera «Pedidos a bodega» ocuparía el lugar de lo que sí hay
que mirar. Medido: C3 y C4.

---

## El aviso a bodega

Sale por **los canales que la empresa ya configuró** (`services/avisos.py`): el
chat, el correo. Bodega se entera por donde ya recibe todo lo demás.

Construirle una bandeja aparte sería pedirle que mire dos lugares, y **la que
mira menos es siempre la nueva**.

Tres cosas medidas sobre ese aviso:

- **No lleva datos del cliente.** A bodega no le hace falta saber a quién se le
  instala para sacar veinte conectores de una caja. Medido: `test_e2`.
- **Un reenvío no vuelve a avisar.** Medido: `test_e3`.
- **Si el aviso falla, el pedido existe igual.** El hecho es la fila, no el
  mensaje: un chat caído no puede dejar al técnico sin material. Medido:
  `test_e4`.

---

## Lo que NO resuelve, y hay que decirlo

1. **Sólo se puede pedir material que ya está en el kit** (incluso con saldo
   cero). Pedir algo que nunca tuvo exigiría bajar el catálogo completo de la
   empresa, que la aplicación hoy no baja.

2. **No hay pantalla en el CRM para marcar un pedido como atendido.** Eso se
   hace **despachando**, con el flujo de entrega que ya existe: esto no inventa
   una segunda forma de entregar material. El pedido queda `pendiente` hasta
   que alguien lo cierre a mano o se construya esa pantalla.

3. **El motivo es opcional, a propósito.** Parado en una escalera, escribir un
   motivo es lo primero que se saltea. Exigirlo haría que el pedido no se haga,
   que es el único resultado malo acá.

Las tres son **deuda declarada**, no olvidos.

---

## Lo que se midió

| Suite | Casos | Contra qué |
|---|---|---|
| `campo/tests/test_pedido_de_material.py` | 20 | **PostgreSQL real** |
| `test/pedir_a_bodega_test.dart` | 28 | SQLite real (ffi) |
| `test/subir_pedidos_test.dart` | 9 | `Dio` interceptado: la petición se arma completa |
| `test/guarda_de_ancho_real_test.dart` | 16 | 360 y 412 px, con letra 1.3× |

**19 mutaciones aplicadas, 19 cazadas.** Tres de ellas eran huecos reales de
las pruebas, no del código: el filtro por persona al cerrar un pedido (B11), el
reencolado de un id ya enviado (B6b), y la espera del reintento (B9).

### Dos desbordes que encontró la guarda, y no los puso el pedido

La guarda de ancho real no cubría la pantalla de Materiales. Al agregarla
aparecieron dos cosas que **ya estaban rotas a 360 px** —el Galaxy A que una
empresa le compra a una cuadrilla—:

- el título «Materiales en Custodia» con su conteo: **153 px** de desborde;
- el botón «Preparar Devolución al Depósito»: **190 px** — el botón que cierra
  la jornada se salía de la pantalla sin que nada avisara.

Los dos arreglados. Es el corolario de §6: lo que no se mide no se ve, y acá no
se veía porque nadie había montado esta pantalla a un ancho de verdad.

### Lo que queda sin medir

El ciclo **con el servidor real corriendo**: `subir_pedidos_test` intercepta el
`Dio`, así que afirma lo que el servidor va a recibir, no que el servidor de
verdad lo acepte. La forma del cuerpo sí está medida contra PostgreSQL real por
el lado del backend, pero **las dos mitades no se tocaron en una sola corrida**.
