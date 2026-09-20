# D28 — quién figura atendiendo el caso en el CRM

```
BASE       e419431
VEREDICTO  implementado. La sincronización automática NO está enganchada todavía
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

## Lo que falta para que esto corra solo

**La sincronización no está enganchada.** Existe el endpoint, el ejecutor, la
detección y el tipo en la cola — pero nada **encola** todavía un `asignar_caso`
al tomar, reasignar o transferir. Falta:

```
1. el productor: encolar desde T2/T5 (tomar, reasignar), en la misma
   transacción que el cambio de asignación
2. las dos capacidades en el worker: agregar_asignado y leer_asignados,
   atadas al catálogo del tenant como ya se hace con crear_caso
3. el panel que muestre la diferencia (la lógica y sus etiquetas ya están)
```

Sin el punto 2, un `asignar_caso` que llegue a la cola hoy termina en
`fallida_definitiva` con `sin_ejecutor:asignar_caso` — visible, no silencioso.
Es el comportamiento correcto, pero conviene saberlo.

Y como todo lo de B4: no corre hasta G7.
