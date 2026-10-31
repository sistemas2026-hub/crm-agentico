# D28 — quién figura atendiendo el caso en el CRM

```
BASE       e419431
VEREDICTO  CERRADO EN CÓDIGO. No corre hasta G7
FECHA      20/09/2026
DECISIÓN   (b) + salvedad conservadora, cerrada por el auditor
```

## El problema

Dexter decide quién atiende. El CRM mostraba al operador anterior: el proxy
sincronizaba al **tomar** y nunca más, así que una reasignación dejaba las dos
vistas divergiendo y nadie se enteraba. Soltar tampoco lo tocaba.

## Lo que la auditoría de capacidades encontró

`Case.assigned_to` es **ManyToMany**, no un dueño. Y las tres formas que la API
tenía de escribirlo **reemplazan el conjunto**:

```
POST /api/cases/             .add(), pero sólo al CREAR
PUT  /api/cases/<id>/        clear()+add() — y borra contacts, teams y tags
POST /api/cases/bulk/update  .set()
```

Para una persona editando un formulario eso está bien: ve el conjunto que
reemplaza. Para un reconciliador no — entre leer y escribir, un supervisor que
suma un segundo técnico pierde su cambio sin rastro.

Eso motivó el STOP, y la decisión del auditor fue **(b)**: agregar al operador
sin pisar a nadie, mostrar los extras, no borrarlos.

## El endpoint nuevo del CRM (`91127c6`)

```
POST /api/cases/<id>/assignees/   {"profile_id": "<uuid>"}
GET  /api/cases/<id>/assignees/
```

`ManyToMany.add()` **no** es read-modify-write: inserta en la tabla intermedia
ignorando conflictos. Dos llamadores agregando personas distintas a la vez
tienen éxito los dos. Esa es la razón por la que este endpoint puede ser seguro
y los otros tres no pueden hacerse seguros.

Falla cerrado, y a propósito **distinto** de `bulk/update`: ahí un perfil de
otra organización se filtra en silencio y el conjunto termina vaciado, así que
«asigna a X» puede significar «no asignes a nadie» con un 200. Aquí es un 400 y
el conjunto no se toca.

La respuesta dice quién está asignado **ahora**: un llamador automático no tiene
otra forma de confirmar el efecto.

### No hay DELETE, y es una decisión

`remove()` sería igual de atómico. Lo que falta es **procedencia**: la tabla
intermedia no guarda quién creó la relación ni por qué, así que nada distingue
una asignación automática vieja de una colaboración que alguien armó a mano esta
mañana. Desasignar sigue siendo manual hasta que haya forma de saber la
diferencia.

## El lado de Dexter (`5634f0b`)

```
nucleo/relevo/asignados_crm.py    qué falta y qué se preserva
efectos_externos.asignar_caso     escribe, RELEE y comprueba
tipo 'asignar_caso' en la cola    migración 202609202100
```

**La identidad se cruza por id.** Dexter guarda el `User.id` de Django; el CRM
devuelve `Profile.id` junto a `user_details.id`, que es ese mismo `User.id`.
Probado con dos perfiles **homónimos**: un nombre que coincide no prueba nada, y
actuar sobre esa coincidencia asigna el caso a quien no es.

**Un 200 no es el efecto.** Se relee siempre, incluso cuando la escritura no dio
error. Si la relectura no confirma que el perfil quedó → `incierto`, nunca
`éxito`. Si la escritura falló pero la relectura muestra que sí quedó, se
adopta — mismo criterio que `crear_caso`.

**La clave de idempotencia lleva el perfil**, no sólo la conversación:
reasignar a otra persona es otro efecto. Sin eso, la segunda asignación se
descartaría como repetida y el CRM seguiría mostrando al operador anterior —
exactamente el defecto que D28 describe.

**Soltar no limpia el caso.** Deja divergencia visible.

## La pantalla (`713b7b2`)

```
A cargo en Dexter    UNA persona, y es la autoridad
Asignados en CRM     un CONJUNTO
```

No se dice «dueño del caso» en ningún lado, y hay una aserción que lo fija. Ese
nombre promete una sola persona y una autoridad que el campo no tiene, y quien
lo lea así va a querer corregirlo borrando a los demás.

Un colaborador de más es **información**, no un defecto: el texto no sugiere
quitarlo. Una asignación que todavía no se reflejó es trabajo en curso, no un
error. Un operador sin perfil en el CRM se explica sin prometer que se va a
sincronizar, porque reintentar no lo arregla.

## Tests

```
cases/tests/test_case_assignees.py   12, ejercitando el endpoint (pytest-django)
  agregar a [B,C] → [A,B,C] · repetir no duplica · dos altas no se pisan
  perfil de otra org → 400 y conjunto intacto · caso de otra org → 404
  ninguna forma de la petición vacía el conjunto · no hay DELETE

tests/test_d28_asignado_crm.py       25
  identidad por id, con dos homónimos · colaboradores preservados
  soltar no vacía · los tres desenlaces de la relectura

asignados.test.js                    9
```

**Mutaciones: 17 probadas, 17 rojas.**

| | |
|---|---|
| `add()` se vuelve `set()` | ROJO |
| el perfil de otra org se filtra en silencio | ROJO |
| el caso deja de filtrarse por org | ROJO |
| la identidad se cruza por nombre | ROJO |
| los colaboradores se descartan | ROJO |
| soltar marca que hay que limpiar | ROJO |
| la clave ignora a quién se asigna | ROJO |
| se cree el 200 y no se relee | ROJO |
| no poder comprobar se trata como éxito | ROJO |
| la etiqueta vuelve a decir «dueño» | ROJO |
| + 7 más | ROJO |

Los 826 tests del módulo `cases` del CRM siguen pasando.

## Las tres piezas que faltaban (`86879aa`)

**Productor.** `tomar()` y `reasignar()` encolan en la **misma transacción** que
el cambio de asignación. Eso no contradice «no escribir en el CRM dentro de la
transacción»: lo que se escribe es la *intención*, en una tabla propia; al CRM
lo llama el reconciliador después del commit (§3.6, X23). Al revés —primero el
CRM, después el commit— un fallo dejaría el caso asignado a alguien que en
Dexter no lo tiene.

```
tomar        encola al operador
reasignar    encola al que ENTRA; al que sale no se lo quita
soltar       NO encola          devolver_a_ia   NO encola
```

Sin caso todavía no se encola. Y si encolar falla, la toma **no se cae**: quien
atiende ya cambió en Dexter, que es la autoridad.

**Worker.** Tres capacidades, fail-closed sin cualquiera: `asigna_caso`,
`lee_asignados`, `lee_perfiles`. La tercera traduce el usuario durable al perfil
del CRM **por id** — sin ella habría que adivinar por nombre.

**UI.** Panel propio, «A cargo en Dexter» / «Asignados en CRM», sin botón para
quitar a nadie.

### La clave lleva el usuario, no el perfil

El brief pedía conversación + caso + **profile**. Lleva conversación + caso +
**usuario durable**, y la razón es dura: resolver el perfil exige preguntarle al
CRM, y la clave se arma dentro de la transacción que cambia la asignación —
meter una llamada HTTP ahí es exactamente lo que X23 prohíbe. Dentro de una
organización la correspondencia es uno a uno, así que discrimina igual: dos
operadores distintos dan dos claves distintas, que es lo único que el requisito
necesitaba.

## El hallazgo que apareció en el camino

**Las banderas de capacidad no existían en el schema.** `Herramienta` usa
`extra="forbid"`, así que un YAML con `busca_caso: true` hacía fallar la carga
entera — y el código de B4 ya la leía con `getattr(..., False)`, que devuelve
False en silencio.

O sea: la capacidad se consultaba, no se podía declarar, y nadie se enteraba.
**G7 dependía de eso**: «declarar `busca_caso` en el catálogo del tenant» era
imposible tal como estaba. Quedan declaradas las cuatro.

No lo encontró una prueba: apareció al intentar declarar `asigna_caso` y ver que
el modelo lo rechazaba.

## Tests

```
cases/tests/test_case_assignees.py   12, ejercitando el endpoint (pytest-django)
tests/test_d28_asignado_crm.py       47
  identidad por id, con homónimos · colaboradores preservados
  quién encola y quién NO · el orden dentro de la transacción
  las transiciones no hablan con el CRM
  el worker exige las tres capacidades · la pantalla está cableada
asignados.test.js                     9
```

**Mutaciones: 23 probadas, 23 rojas.** Entre ellas: `add()` se vuelve `set()`,
la identidad se cruza por nombre, soltar empieza a encolar una limpieza,
reasignar encola al anterior, el worker se conforma con una capacidad, sin
catálogo de perfiles se adivina igual.

Los 826 del módulo `cases` del CRM siguen pasando.

## La atomicidad (`3a7e79f`)

El primer intento tenía una contradicción que encontró el auditor: «encola en
la misma transacción» y «si encolar falla, la toma no se cae» juntos permiten
**operador cambiado + ninguna intención durable + nada que lo diga**. Ahí D28
reaparece en silencio.

El `try/except` estaba mal por dos motivos, y el segundo es el que importa:

1. **No salvaba nada.** Corre con el cursor de la transacción: un error de base
   la deja abortada, así que atraparlo no permite seguir — el COMMIT termina en
   ROLLBACK igual. Prometía una resistencia que no existía.
2. **Si hubiera funcionado**, habría dejado justo el estado prohibido.

Quitado. Ahora la transición entera hace rollback: **o las dos cosas, o
ninguna**. El operador ve un error y reintenta, que es mejor que una
divergencia que nadie nota.

Una clave repetida no es un fallo, y no hizo falta tocar nada para eso:
`encolar_sincronizacion` ya hace `on conflict do nothing`. La intención
existente se adopta — probado soltando y volviendo a tomar.

La garantía se afirma entera, con una consulta:

```sql
-- ninguna conversación con caso y operador sin su intención
select count(*) from conversations c
 where c.caso_id is not null and c.asignada_a_usuario_id is not null
   and not exists (select 1 from sincronizaciones_externas s
                    where s.conversation_id = c.id and s.tipo = 'asignar_caso')
```

## D28: CERRADO EN CÓDIGO

Lo que queda es despliegue, no diseño:

```
1. declarar las cuatro herramientas en el catálogo del tenant
   (asigna_caso apuntando al endpoint aditivo nuevo, no a bulk/update)
2. G7: encender el reconciliador
```

Sin el punto 1, un `asignar_caso` termina en `fallida_definitiva` con
`sin_ejecutor:asignar_caso` — visible, no silencioso.

**No se automatiza quitar a nadie**, y esa decisión no cambia hasta que el CRM
guarde la procedencia de cada asignación.
