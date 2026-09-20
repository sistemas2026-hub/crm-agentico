# Gate G3 — el legado queda seguro y revisable

```
BASE       1dfb79b
VEREDICTO  G3 VERDE — el camino de ejecución está cerrado y hay dónde revisar
ALCANCE    implementación. Sin tocar producción.
FECHA      20/09/2026
ENTRADA    auditorias/G3-ACCIONES-LEGACY.md (ROJO, 4 bloqueos)
```

## Qué estaba roto, y qué cambió

| Bloqueo (auditoría) | Estado |
|---|---|
| 1. `aprobar` ejecutaba las 36 | **cerrado.** 409 antes de tocar nada |
| 2. nadie podía revisarlas | **cerrado.** Pantalla propia, sin botón de aprobar |
| 3. `cancelada` no existía | **cerrado.** Estado declarado, con motivo y evento |
| 4. los datos están en producción | **sigue abierto, y es correcto.** Ver «La reconciliación» |

## 1. El camino peligroso

`POST /acciones/propuestas/<id>/aprobar` rechaza con **409** y no ejecuta nada.
La guarda corre **antes** de todo lo demás —antes del chequeo de estado y antes
de leer la config— porque lo que se prohíbe es llegar al ejecutor, y cada paso
previo que pueda escribir es un paso de más en un camino que no debería existir.

El criterio es **uno solo** y no es una heurística:

```python
def es_accion_de_legado(accion) -> bool:
    return not (accion or {}).get("conversation_id")
```

Sin `conversation_id` no hay contexto actual contra el cual revalidar (§3.7).
**No se mira la edad ni el tipo.** Una acción de hace un minuto sin conversación
es igual de inejecutable que una de hace un mes: el problema nunca fue el
tiempo. Y una regla por edad se vuelve falsa sola, en silencio, el día que
alguien cambie el plazo.

Hoy eso alcanza a las 36, porque la columna no existe. **Cuando B5 la traiga, la
misma función deja pasar las que la tengan sin que haya que tocarla** — probado
en las dos direcciones.

El intento queda registrado. Un 409 se responde y se pierde; si alguien insiste
contra el legado, lo que falta es explicar mejor por qué, no repetir el rechazo.

## 2. `cancelada`

Migración `202609201400_acciones_legado.sql`, aplicada limpia sobre una base con
el esquema completo (50 en el ledger, todos `aplicada`).

```
acciones_propuestas_estado_declarado   pendiente|aprobada|rechazada|cancelada
acciones_propuestas_cancelada_con_motivo   una cancelada exige su motivo
```

Los dos van **`not valid`**: no escanean la tabla —sin lock largo sobre datos de
producción— y aun así validan todo INSERT y UPDATE nuevo, que es donde puede
entrar un estado inventado. Las filas viejas se validan cuando producción lo
decida.

**`cancelada` no es `rechazada`.** Rechazada es «alguien la evaluó y dijo que
no»; cancelada es «quedó obsoleta y nadie la va a evaluar». Las dos evitan la
ejecución, pero en un registro que existe para auditar decir cuál fue es el
registro entero.

### El evento

Tabla nueva `asistente.acciones_eventos`. `relevo_eventos` no servía: su
`conversation_id` es `NOT NULL` con FK a `conversations`, y estas 36 no tienen
conversación — la ausencia es justamente lo que las hace de legado. La nueva lo
tiene **nullable**, con el mismo vocabulario de tipos, así que cuando B5 traiga
la columna el evento la lleva también y las dos vistas se cruzan.

Sólo `select` e `insert` para `app_backend`, igual que `relevo_eventos`: un
expediente que se puede corregir no es un expediente.

El evento y el cambio de estado entran en **la misma transacción** (I12):
`registrar_evento_de_accion` recibe el cursor en vez de abrir su propia sesión.
Con una sesión propia existiría el estado intermedio donde la acción ya está
cancelada y nadie registró quién ni por qué.

El candado es el `and estado = 'pendiente'` del UPDATE: dos operadores
cancelando a la vez escriben una sola vez, y el segundo se entera.

## 3. La superficie

`/acciones-legado`. Lista las pendientes, agrupadas por tipo arriba del todo
—que «34 crearían tickets» cambia cómo se lee la lista: no son 36 filas iguales,
son 34 visitas técnicas y 2 promesas vencidas—.

**No hay botón de aprobar. No deshabilitado: ausente.** Un botón gris invita a
preguntar cómo habilitarlo. Tampoco hay proxy que llegue a `/aprobar`.

Cada fila dice qué haría, su resumen, la antigüedad y **por qué no se aprueba**,
con la razón real de su tipo. La antigüedad se muestra porque ayuda a decidir,
pero el texto no la presenta como el motivo: si se leyera así, la regla
parecería un plazo que alguien podría estirar.

**Sin `argumentos`.** Ahí están los valores reales sin enmascarar —teléfono,
cédula, dirección— con los que se iba a escribir afuera. Para revisar alcanza el
resumen, que existe para eso. Quien necesita la acción completa para ejecutarla
usa otro camino y es otra decisión.

Quien cancela sale de la sesión, nunca del cuerpo que arma el navegador.

## 4. La reconciliación de las 36

**No se tocó ninguna fila, y eso es lo correcto.** Viven en producción, y el
contrato pide revisión humana una por una — no un `UPDATE` masivo que las
cancele en lote. Lo que faltaba era que el sistema *permitiera* esa revisión;
ahora la permite.

```
34 create_ticket     cancelar. Con Q2 rojo, crear el ticket hoy es irreversible
                     y sin forma de detectar duplicado. Si el problema sigue
                     vivo, la conversación de hoy lo vuelve a proponer.
 2 promise_payment   quedan listas para revisión humana. NO se afirma si el
                     cliente pagó: eso exige consultar producción, y no se
                     consultó. Inventar ese resultado sería peor que no darlo.
```

**Ninguna se adopta automáticamente**: no hay proceso que cancele ni apruebe en
lote. El reloj no las vence (§11.4 lo prohíbe expresamente) y el reconciliador
no las toca. Verificado en el test, no afirmado.

## Tests

```
tests/test_g3_acciones_legado.py    contra PostgreSQL real
  aprobar: 409, ejecutor con CERO llamadas, estado intacto, evento del intento
  insistir cuatro veces sigue sin ejecutar
  el criterio en las dos direcciones, y que no mira la edad
  cancelada: estado, motivo, quién, cuándo, evento, todo junto (I12)
  cancelar dos veces: 409, sin pisar el motivo ni duplicar el evento
  la base rechaza un estado inventado y una cancelada sin motivo
  la lista: sin argumentos, sin los datos reales por ningún camino
  aislamiento entre empresas, en lectura, cancelación y aprobación

src/lib/acciones/legado.test.js     16 aserciones
  ningún control que apruebe · ningún proxy que llegue a /aprobar
  quién cancela sale de la sesión · las dos rutas exigen sesión
  la antigüedad no es lo que la hace inejecutable
```

**Mutaciones: 8 probadas, 8 rojas.**

| Mutación | Resultado |
|---|---|
| se reabre la ejecución (la guarda desaparece) | ROJO |
| la guarda corre después de ejecutar | ROJO |
| el criterio pasa a ser la edad | ROJO |
| cancelar no deja evento | ROJO |
| cancelar reusa `rechazada` | ROJO |
| se quita el candado de `pendiente` | ROJO (4 fallos) |
| la lista vuelve a traer los argumentos | ROJO |
| se agrega un botón de aprobar a la pantalla | ROJO |

**Un error propio, el mismo de siempre, la cuarta vez en esta fase.** La
aserción «la lista no pide los argumentos» dio rojo por el *comentario* que
explica que no los pide. Y la del botón prohibía la palabra «aprobar» en el
marcado, cuando la pantalla **tiene que** decir «no se pueden aprobar» en su
texto. Las dos reescritas para afirmar sobre lo que se ejecuta y sobre los
controles, no sobre la prosa. Queda un helper `soloCodigo()` con el porqué.

## G3: VERDE

El camino que el gate existía para impedir está cerrado, con la guarda medida
por su efecto —cero llamadas al ejecutor— y no por su presencia. Hay dónde
revisar las 36 y con qué cancelarlas dejando rastro.

**Lo que NO cierra este gate, y no debe confundirse:** las 36 filas siguen
`pendiente` en producción. Cancelarlas es trabajo de una persona con la pantalla
delante, y ese es el punto — el gate pedía hacerlo posible, no hacerlo solo.

B5 queda desbloqueado.
