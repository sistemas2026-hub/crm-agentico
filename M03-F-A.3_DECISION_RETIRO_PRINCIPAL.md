# M03-F-A.3 — Cierre de decisión: retiro del principal

**Fecha:** 2026-09-18
**Alcance:** decisión empresarial/operativa. **Sin implementar.**
**Decisión:** **OPCIÓN A** — al retirar al principal se indica el nuevo principal en la misma operación
**Veredicto F-B:** **GO**

---

## Resumen

```
Codigo modificado:   0    Modelos: 0   Migraciones: 0   Endpoints: 0
Serializers: 0   AsignacionTrabajo: sin tocar   M09: sin tocar   revisar_coherencia: sin tocar
makemigrations --check:    "No changes detected"
Produccion:          SIN CAMBIOS -- 15 claves, DIFERENCIAS: NINGUNA (solo SELECT, read_only)
Commit:              no

Mediciones nuevas:   5 (P1..P5), contenedor aislado, 0 credenciales de produccion

F-1 CERRADO · F-2 CERRADO · F-3 CERRADO · F-4 CERRADO · RETIRO PRINCIPAL CERRADO
```

### Por qué A, en una línea

**[MEDIDO]** Porque este sistema **ya resolvió dos veces la misma clase de
problema de la misma forma**, y porque la forma de fallar de B es silenciosa:
un retiro a medias deja un estado **legal** que ninguna comprobación existente
marca.

---

## Método

**[MEDIDO]** Cinco mediciones (P1–P5) sobre PostgreSQL 16 aislado (`pg-fa3`),
runner desde `crm-agentico-backend:latest`, **0 credenciales de producción**
(medido con `env | grep -ci`). Las operaciones de retiro **no existen**: se
**simularon** las dos formas para medir el estado que deja cada una. Entorno
eliminado, archivo de medición borrado (verificado con `git status`).

Producción: **solo `SELECT`**, `read_only = True`.

---

## A. Evidencia encontrada

> El encargo: *"Revisar si existe algún flujo actual que permita inferir cómo
> Rapilink maneja reemplazo / cambio de responsable / retiro / reasignación.
> Si existe evidencia: [MEDIDO]. Si no: [PENDIENTE EMPRESARIAL]. No inventar
> una política."*

### A.1 El sistema ya declaró su postura sobre este problema exacto

**[MEDIDO]** `campo/services/despacho.py:148-155`, docstring de `asignar()` —
escrito por una persona, sobre este mismo campo:

> *"El modelo ya impone un solo principal por orden […] asi que hay que bajar
> el anterior ANTES de subir el nuevo o la base rechaza el cambio. **Las dos
> cosas van en la misma transaccion: una orden sin principal, aunque sea por un
> instante, es una orden que nadie ve como suya.**"*

**[MEDIDO]** No es una interpretación: es la **política de diseño ya escrita**
para el traspaso de responsabilidad, y su forma es exactamente la de la
**Opción A** — bajar y subir **en un solo acto**, nombrando al sucesor.

### A.2 Ninguna operación de M03 se hace en dos pasos

**[MEDIDO]** Todas las operaciones mutantes del módulo **nombran su destino en
la misma llamada**:

| Operación | Exige nombrar el destino |
|---|---|
| `programar_orden` | `programacion` **+** `programada_para` |
| `reprogramar_orden` | `programacion_destino` **+** `programada_para` |
| `actualizar_secuencia` | `secuencia` (el valor nuevo) |
| `secuenciar_jornada` | `lineas` (**todas**, decisión G-2 aprobada) |
| `asignar` | `profile_tecnico` (el nuevo principal) |
| `registrar_contingencia` | `causa` obligatoria |

**[MEDIDO] No existe en todo el módulo una sola operación de "deshacer y
después rehacer".** `reprogramar_orden` es el análogo más directo: cambiar el
**cuándo** de una OT que ya tenía un cuándo **exige el destino en el mismo
acto** — no hay "desprogramar" seguido de "programar". Retirar al principal es
cambiar el **quién** de una OT que ya tiene un quién: la operación simétrica.

**[DISEÑO]** La Opción B sería **la primera operación de dos pasos del módulo**.

### A.3 No hay práctica operativa observable de Rapilink

**[MEDIDO]** Producción **nunca ha tenido una cuadrilla**: 3 OT, 3 asignaciones,
**1 persona por orden**, las 3 con `rol='tecnico_lider'` y `es_principal=True`.
Cero `teams`, cero disponibilidades.

**[MEDIDO]** Tampoco hay interfaz que observar: el barrido del frontend no
encontró **ninguna pantalla** que asigne técnicos a órdenes de campo. Las
coincidencias de *"asignar"* son de tickets, conversaciones y documentos —
otro dominio.

### A.4 Qué se puede y qué no se puede afirmar

**[MEDIDO] Existe evidencia, y es del sistema, no del negocio.** Lo que está
medido es cómo **este código** resuelve ya el traspaso de responsabilidad
(A.1) y el cambio de estado en general (A.2).

**[RIESGO] Lo que NO está medido es una práctica de Rapilink.** Sin cuadrillas
en producción no hay historia operativa que leer. La decisión que sigue se
apoya en **coherencia con el sistema existente y en el modo de fallar de cada
opción**, no en *"así lo hace Rapilink"*. **Se dice explícitamente para que
pueda revocarse con conocimiento**: si la operación real de Rapilink
contradice esto, la evidencia del negocio manda sobre la del código.

---

## B. Evaluación de la Opción A — reemplazo en el mismo acto

### B.1 Ventajas operativas

**[DISEÑO]**

| | |
|---|---|
| **Una sola decisión, en el momento en que importa** | Quien retira a alguien sabe **en ese instante** quién queda a cargo. Es cuando tiene el contexto |
| **No existe estado intermedio** | La OT nunca queda a medio camino: o cambió por completo, o no cambió |
| **Un solo viaje contra el servidor** | Relevante en campo: **[MEDIDO]** el módulo ya mantiene un contador `revision` para la cola offline del técnico (`despacho.py:181-182`), o sea que la mala conectividad es un escenario contemplado. Dos viajes son dos oportunidades de fallar |
| **Coherente con todo el módulo** | A.2: ninguna operación de M03 se parte en dos |

### B.2 Riesgos operativos

**[RIESGO]**

| | |
|---|---|
| **Obliga a decidir el sucesor ya** | Si quien opera no sabe quién queda a cargo, **no puede retirar**. La operación falla y no cambia nada |
| **Fricción cuando el sucesor es obvio** | En una cuadrilla de 2, el sucesor es el único que queda, y aun así hay que nombrarlo |

**[DISEÑO] Mitigación medida, no inventada:** el módulo ya distingue *"exigido
según el contexto"* — `_validar_causa(..., exigida=es_adicion_formal)` pide
causa solo cuando hay compromiso operacional. La misma forma aplica aquí: el
sucesor se exige **solo** cuando la persona que sale es la principal **y** queda
al menos un integrante. Si sale el último, no hay sucesor que pedir (§J).

### B.3 Complejidad de la operación

**[DISEÑO] No agrega una operación.** Es `retirar_integrante` con un parámetro
**condicionalmente obligatorio**:

```
retirar_integrante(orden, persona, nuevo_principal=None, motivo="")
```

**[DISEÑO]** No hace falta una operación "reemplazar" aparte: F-A.2 §F.1 ya la
había descartado como `[NO NECESARIO]`, y esta decisión lo confirma — el
reemplazo **es** este retiro.

### B.4 Riesgo de error humano

**[DISEÑO] Concentra la decisión y no admite resultado parcial.** El error
posible es *nombrar al sucesor equivocado*, que es visible de inmediato: la OT
queda a nombre de alguien, y quien mira la bandeja lo ve. **No existe el error
de "olvidar terminar"** — porque no hay un segundo paso que olvidar.

### B.5 Trazabilidad

**[DISEÑO] Un acto, un evento** (§F): el mismo registro dice quién salió, quién
era principal y quién lo es ahora. Quien lee la bitácora ve **una decisión**,
que es lo que efectivamente ocurrió.

### B.6 Concurrencia

**[MEDIDO] P3** — con el lock sobre la OT que F-A.2 §G.3 propuso, dos cambios
simultáneos de principal se serializan **sin una sola excepción**:

```
excepciones ......... 0
se serializaron en .. ['->pc', '->pb']
integrantes 3 · principales 1 · invariante ok? True
CONTRASTE F-A.2 N6 (sin lock): 1 IntegrityError
```

**[MEDIDO]** El lock propuesto **arregla** la carrera que N6 había medido. No
es una promesa: se midió con el lock puesto y con el lock ausente.

### B.7 Auditoría

**[MEDIDO] P2 — un fallo a mitad no deja nada escrito:**

```
fallo forzado despues de mover al principal y borrar la fila
estado antes  == estado despues   ->  identico? True
invariante ok? True (2 integrantes, 1 principal)
eventos 1 -> 1
```

### B.8 Comportamiento de la interfaz

**[MEDIDO] No hay interfaz que respetar** (A.3): la pantalla está por
construirse, así que **la decisión moldea la interfaz, no al revés**.

**[DISEÑO]** La forma natural de A es un diálogo único: *"Retirar a Ana. ¿Quién
queda a cargo?"* con la lista de los integrantes restantes. En una cuadrilla de
2 la lista tiene un solo elemento y puede venir preseleccionado — la fricción
de B.2 se resuelve en la interfaz, no en el contrato.

### B.9 Reemplazos rápidos en campo

**[DISEÑO]** Una llamada, una confirmación, sin estado intermedio que quede
colgado si se corta la señal a la mitad. Es la opción que mejor soporta un
enlace malo — que es la condición normal del trabajo en campo.

### B.10 Datos que debería recibir la operación

**[DISEÑO]** Sin implementar.

| Dato | Obligatorio | Nota |
|---|---|---|
| `orden` | sí | de la ruta |
| `profile_id` | sí | quién sale |
| `nuevo_principal_id` | **condicional** | **solo si** quien sale es el principal **y** queda ≥1 integrante. Debe ser integrante vigente y distinto del que sale |
| `motivo` | **condicional** | exigido cuando hay compromiso operacional (plan publicado u OT ya iniciada) — misma regla aprobada en M03-D1/E3 |

**[DISEÑO] Lo que la operación NO recibe:** `es_principal` (no es del cliente
elegirlo — misma decisión que `ProgramarSerializer` en M03-B), ni fecha, ni
secuencia, ni plan, ni `rol` del sucesor (§J).

---

## C. Evaluación de la Opción B — cambio de principal previo

### C.1 Ventajas operativas

**[DISEÑO]**

| | |
|---|---|
| **Cada operación hace una sola cosa** | `cambiar_principal` y `retirar_integrante` quedan simples y ortogonales |
| **No agrega parámetros condicionales** | Ningún campo "obligatorio a veces" |
| **Permite separar las decisiones en el tiempo** | Se puede cambiar el responsable hoy y retirar a la persona mañana |

**[DISEÑO]** La tercera es una ventaja real: hay casos donde el traspaso de
responsabilidad y la salida física **son** dos hechos distintos. **Pero eso ya
está cubierto por A**: con A siguen existiendo `cambiar_principal` y
`retirar_integrante` por separado; lo que A añade es que el retiro **del
principal** no pueda quedar a medias.

### C.2 Riesgo principal — medido

**[MEDIDO] P1 — el estado a medio camino de B es LEGAL, y nada lo marca:**

```
ESTADO INTERMEDIO DE B (paso 1 hecho, paso 2 NO):
     integrantes .................... 2   (pa sigue asignado)
     principales .................... 1
     invariante F-2 se cumple? ...... True
     revisar_coherencia ............. 0 problema(s)
     H-05 ........................... 0 senal(es)
```

**[MEDIDO]** Tras el paso 1, la persona que debía salir **sigue asignada a la
OT**, y el estado resultante es **indistinguible de una cuadrilla correcta de
2 personas**. El invariante de F-2 se cumple. `revisar_coherencia` no ve nada.
H-05 no emite nada.

**[RIESGO] Esta es la razón de fondo para no elegir B.** Su forma de fallar es
**silenciosa**: un operador interrumpido —se corta la señal, termina el turno,
se distrae— deja un estado incorrecto que **ninguna comprobación existente
puede detectar**, porque no viola ninguna regla. El sistema no tiene cómo
distinguir *"cuadrilla de 2 correcta"* de *"retiro a medio hacer"*.

**[MEDIDO] Contraste directo con A (P2):** un fallo en A deja el estado
**exactamente** como estaba.

```
B interrumpida  ->  estado incorrecto, legal, invisible
A interrumpida  ->  estado original, intacto
```

### C.3 Complejidad y cantidad de pasos

**[DISEÑO]** Dos llamadas, dos confirmaciones, dos eventos, dos oportunidades
de fallar. En campo, con conectividad intermitente, la ventana entre ambas es
justamente donde vive el riesgo de C.2.

### C.4 ¿Deja la OT temporalmente sin principal?

**[DISEÑO] No — y conviene decirlo con precisión, porque el encargo lo pregunta
directamente.** En B nunca hay cero principales: el paso 1 mueve la principalía
a B y el paso 2 retira a A, que para entonces es auxiliar.

**[MEDIDO]** P1 lo confirma: el estado intermedio tiene **1 principal**, no
cero.

**[DISEÑO] El riesgo de B no es la ausencia de principal: es la permanencia de
un integrante que debía salir.** Es un riesgo distinto del que el encargo
anticipaba, y **peor**, porque el que se temía sería detectable (0 principales
viola el invariante) y este no lo es.

### C.5 Trazabilidad y auditoría

**[DISEÑO]** Dos eventos independientes, sin nada que los ligue. Quien lea la
bitácora ve **dos decisiones** donde hubo una; y si el paso 2 nunca ocurrió, ve
un cambio de principal que parece completo y no lo era.

### C.6 Concurrencia

**[RIESGO]** B multiplica la ventana de carrera: entre el paso 1 y el paso 2,
**otro supervisor puede cambiar la composición**, y el paso 2 llega con una
foto vieja. A no tiene esa ventana, porque no tiene "entre".

### C.7 Comportamiento de la interfaz

**[DISEÑO]** La interfaz tendría que guiar al operador por dos pantallas y —
para ser segura— recordarle que le falta el segundo paso. **Eso es un estado de
progreso que el sistema no puede almacenar**: no hay campo que diga *"este
cambio de principal era parte de un retiro"*. La interfaz tendría que
inventarlo del lado del cliente, donde se pierde al recargar.

---

## D. Integridad — prohibir "2+ integrantes, 0 principales"

### D.1 Dónde vive cada garantía

**[DISEÑO]** El encargo pide determinar el mecanismo **independientemente de la
opción elegida**:

| Mecanismo | Qué puede garantizar | Veredicto |
|---|---|:--:|
| **Regla de servicio** | La política y **el mensaje**. Cubre todo lo que pase por el servicio | **sí, necesaria** |
| **Constraint de Django** | `UniqueConstraint` parcial da *"como máximo uno"*. **No puede expresar "al menos uno"**: evalúa una fila, no la ausencia de otra | **insuficiente por sí sola** |
| **Trigger `DEFERRABLE`** | *"Exactamente uno"* evaluado **al cierre de la transacción** | **sí, para la garantía dura** |
| **Combinación** | Servicio (política + mensaje) **+** trigger diferido (garantía) | **RECOMENDADA** |

### D.2 Por qué el trigger tiene que ser DIFERIDO

**[MEDIDO]** Dentro de `asignar()` existe un instante legítimo con **cero**
principales: `update(es_principal=False)` corre **antes** del `get_or_create`
(`despacho.py:170-176`). Un trigger inmediato abortaría una operación correcta.
Debe ser `CONSTRAINT ... DEFERRABLE INITIALLY DEFERRED`, evaluado al `COMMIT`.

**[RIESGO]** Django no gestiona triggers: quedaría como `RunSQL`, invisible a
`makemigrations --check`. Es deuda conocida y hay que asumirla a ojos abiertos.

### D.3 Qué cambia con la Opción A

**[DISEÑO] Con A, el servicio nunca puede producir el estado prohibido**,
porque retirar y transferir son el mismo acto. El trigger deja de ser la
defensa principal y pasa a ser la defensa contra **los otros escritores** —
admin, ORM directo y seeds — que F-A.2 ya midió que rodean toda regla de
servicio (M6: escritura directa, **0 eventos**).

**[DISEÑO]** Con B, en cambio, el trigger tampoco ayudaría: el estado peligroso
de B (**P1**) **no viola el invariante**. Ninguna constraint puede detectarlo,
porque no es un estado inválido — es un estado válido equivocado. **La
integridad no puede rescatar a B.** Ese es el argumento técnico decisivo.

---

## E. Concurrencia — S1 retira A mientras S2 cambia el principal

### E.1 El mecanismo

**[MEDIDO] P3** — con `select_for_update` sobre la **OT**, dos operaciones
simultáneas de composición se serializan con **0 excepciones** y dejan el
invariante intacto. Sin lock, F-A.2 N6 midió **1 `IntegrityError`** crudo.

**[DISEÑO]** Se bloquea la **OT**, no las filas de asignación: el invariante es
**del conjunto**, y bloquear filas no impide que llegue una fila nueva. Es
además el mismo objeto que bloquea `programar_orden`, así que **no se introduce
un orden de lock nuevo** y el invariante del módulo —*el plan es siempre el
último lock*— se respeta por vacuidad: ninguna operación de cuadrilla toca el
plan.

### E.2 Quién gana

**[DISEÑO] Gana quien toma el lock primero.** La segunda **relee la fila fresca
bajo lock** y decide contra ella — el patrón que ya rige en todo M03
(*"lo que decide es la fila bloqueada, no la copia en memoria"*,
`programacion.py:215-218`).

| Escenario | Qué encuentra la segunda | Respuesta |
|---|---|---|
| **S1 gana** (A retirado, B principal) | S2 pide "principal = B"; B **ya** es principal | **200 `sin_cambios`** — el contrato de no-op ya aprobado en M03-B1 |
| **S2 gana** (B principal, A auxiliar) | S1 pide "retirar A, nuevo principal = B"; A ya no es principal y B **ya** lo es | **200**, se retira A. El evento registra que **el principal no cambió en este acto** |
| **S2 gana y S1 nombró a otro** (por ej. C) | La intención de S1 ya no corresponde a la realidad | **409** con lo que cambió — la foto del solicitante está vieja |

**[DISEÑO]** Ninguno de los tres inventa un mecanismo: el no-op de 200, el 409
para conflicto real y la relectura bajo lock son **los tres patrones que M03 ya
usa**.

---

## F. Auditoría

### F.1 La superficie

**[MEDIDO]** `EventoTrabajo` (`campo/models.py`) — *"Bitácora append-only"* —
ya tiene las seis piezas que el encargo exige: `orden` (**OT**), `profile`
(**actor**), `created_at` (**fecha/hora**), y `datos` JSON para **antes**,
**después** y **motivo**. **No se crea ninguna superficie nueva.**

### F.2 El registro de la Opción A

**[DISEÑO] Un acto, un evento** — porque hubo **una** decisión:

```jsonc
tipo: "principal_retirado"
datos: {
  "integrante_retirado": "<profile A>",
  "principal_anterior":  "<profile A>",
  "principal_nuevo":     "<profile B>",
  "rol_que_tenia":       "tecnico_lider",
  "motivo":              "..."          // cuando hay compromiso operacional
}
```

**[DISEÑO] Por qué un evento y no dos:** partir un acto atómico en dos registros
sugeriría que se tomaron dos decisiones. La bitácora debe reflejar lo que
ocurrió.

**[DISEÑO] El costo, y cómo se paga:** quien pregunte *"¿cuándo cambió el
principal?"* tendría que mirar dos tipos (`cambio_principal` y
`principal_retirado`). Se resuelve usando **las mismas claves**
`principal_anterior` / `principal_nuevo` en `datos` en ambos tipos: una sola
consulta sobre esas claves los cubre a los dos, sin catálogo nuevo ni
duplicación.

### F.3 Qué habría registrado la Opción B

**[DISEÑO]** Dos eventos sin vínculo: `cambio_principal` y luego
`integrante_retirado`. **Y si el segundo nunca llega, la bitácora muestra un
cambio de principal que parece completo** — el mismo problema silencioso de
§C.2, ahora en el historial.

### F.4 Dos riesgos que persisten

**[RIESGO] La escritura directa no deja rastro.** F-A.2 M6 y N7: crear o borrar
la fila por ORM deja **0 eventos**. Mientras el inline del admin siga con
`es_principal` y `rol` editables (`campo/admin.py:17-21`), el historial tendrá
huecos silenciosos.

**[RIESGO] `EventoTrabajo.tipo` es texto sin catálogo cerrado.**
`operaciones/auditoria.py:44` ya advierte que un tipo sin declarar *"queda
divergiendo sin que nadie lo vea"* — y cita precisamente a
`AsignacionTrabajo.rol` como el caso que terminó así.

---

## G. Programación — confirmación

> El encargo: *"Si existe evidencia contraria, reportarla."*

**[MEDIDO] No existe evidencia contraria.** P4 — retiro del principal sobre una
OT **ya programada** (plan, secuencia 5, zona sur, prioridad 2):

```
programada_para   IGUAL
estado            IGUAL
secuencia         IGUAL
dia               IGUAL
zona              IGUAL
prioridad         IGUAL
estado_linea      IGUAL
updated           IGUAL          <- ni el updated_at de la linea se movio
lineas del plan   1
revisar_coherencia  0 problema(s)
```

**[MEDIDO]** F-A.2 N3 ya lo había confirmado para `asignar()`. **P4 lo confirma
ahora para el retiro**, que es el caso que este paso decide.

**[MEDIDO] Sustento estructural:** `operaciones/programacion.py` **no lee
`asignaciones` en ninguna línea**, y `revisar_coherencia` tampoco — comprueba
organización, límites de semana, coherencia día↔fecha y líneas duplicadas.
**Ninguna comprobación mira personas.**

**[DISEÑO]** La única escritura sobre la OT que F-B debe conservar es
`revision += 1`: es el contador de la cola offline, y si cambia la cuadrilla el
dispositivo del técnico tiene que enterarse.

---

## H. Disponibilidad — confirmación

**[MEDIDO] P5 — declarar ausente al principal de una OT programada:**

```
composicion cambio? ....... False
programacion cambio? ...... False
eventos nuevos ............ 0
senales H-05 .............. 1        <- solo SENAL
```

**[MEDIDO] Sustento estructural:** `DisponibilidadTecnico` tiene **un solo
lector**: `_ordenes_en_riesgo` (`supervisor.py:481`). Y **no hay ni un
`post_save`, ni un `pre_save`, ni un `receiver`** en `campo/` ni en
`operaciones/` — el barrido no devolvió nada. **Nada puede reaccionar
automáticamente a una ausencia**, porque no hay mecanismo que lo haga.

**[DISEÑO] Confirmado para F-B:** ante un principal ausente, **no** se retira,
**no** se reasigna, **no** se reprograma. Queda como **señal**, y la propuesta
es de un paso posterior.

**[DEPENDENCIA]** Ampliar H-05 para mirar a **todos** los integrantes vive en
`operaciones/supervisor.py`, que es **M09** — prohibido en este paso y fuera
del alcance de F-B.

**[RIESGO]** Queda dicho de nuevo, porque importa: F-B habilita cuadrillas de N
personas mientras H-05 sigue mirando a una sola. **El punto ciego crece con la
adopción.**

---

## I. Decisión final

# DECISIÓN A

> **"Al retirar al principal, se debe indicar el nuevo principal en la misma
> operación."**

### I.1 Los cinco motivos, cada uno con su evidencia

| # | Motivo | Evidencia |
|:--:|---|---|
| **1** | **El sistema ya declaró esta política para este mismo campo** | **[MEDIDO]** `asignar()` docstring: *"una orden sin principal, aunque sea por un instante, es una orden que nadie ve como suya"* — bajar y subir **en la misma transacción** |
| **2** | **Ninguna operación de M03 se hace en dos pasos** | **[MEDIDO]** Las 6 operaciones del módulo nombran su destino en el mismo acto. `reprogramar_orden` exige el destino; no existe "desprogramar". B sería la primera excepción |
| **3** | **La forma de fallar de B es silenciosa** | **[MEDIDO] P1**: el estado a medio camino cumple el invariante, pasa `revisar_coherencia` y no dispara H-05. Es **indistinguible** de una cuadrilla correcta |
| **4** | **La forma de fallar de A es segura** | **[MEDIDO] P2**: un fallo a mitad deja el estado **idéntico**. Rollback completo |
| **5** | **La integridad no puede rescatar a B** | **[DISEÑO]** El estado peligroso de B **no viola ninguna regla**: ninguna constraint ni trigger puede detectarlo, porque es un estado *válido equivocado* (§D.3) |

### I.2 Lo que esta decisión NO afirma

**[RIESGO] No afirma que así opere Rapilink hoy.** Nunca ha existido una
cuadrilla en producción (A.3), así que no hay práctica que medir. La decisión
se apoya en **coherencia con el sistema** y en el **modo de fallar** de cada
opción. Si la operación real contradice esto, **la evidencia del negocio manda
sobre la del código** y la decisión se revisa.

### I.3 No se plantea una tercera alternativa

**[DISEÑO]** El encargo lo permite *"solo si existe evidencia real que la haga
necesaria"*. **No apareció ninguna.** El caso que podría parecer una tercera
vía —retirar al **último** integrante, sin sucesor posible— **no lo es**: es el
paso al estado A (0 asignaciones), que F-2 ya declara legítimo, y queda cubierto
por la regla condicional de §B.10 sin inventar nada.

---

## J. Contrato F-2 actualizado

**[DISEÑO]** Conceptual. **No implementado.**

### J.1 Los tres estados

| | Estado | ¿Válido? | Principal | Rol | Líder |
|:--:|---|:--:|---|---|---|
| **A** | **0 integrantes** | **SÍ** — deliberado y consumido por M09 | ninguno | no aplica | no aplica |
| **B** | **1 integrante** | **SÍ** | **exactamente 1** (esa persona) | descriptivo | no aplica |
| **C** | **2+ integrantes** | **SÍ** | **exactamente 1** | descriptivo, uno por integrante | el principal cumple ese papel |

### J.2 Regla de principal

```
count(integrantes vigentes) == 0   ->   count(principal) == 0     valido
count(integrantes vigentes) >= 1   ->   count(principal) == 1     exigido
```

**[DISEÑO]** Evaluada **al cierre de la transacción**, nunca por fila: dentro de
un traspaso existe un instante legítimo con cero principales (§D.2).

### J.3 Comportamiento al retirar — **nuevo**

**[DISEÑO]**

| Caso | Regla |
|---|---|
| **Sale un auxiliar** (no principal) | Se retira. El principal **no cambia**. Nada más se toca |
| **Sale el principal y quedan ≥1 integrantes** | **Obligatorio** indicar el nuevo principal **en la misma operación**. Ambos cambios en **una transacción**. El sucesor debe ser integrante vigente y distinto del que sale |
| **Sale el principal y es el último** | Se retira sin sucesor. La OT pasa al **estado A** (0 integrantes), que es válido |
| **Falla cualquier parte** | **Nada** se escribe. La OT queda como estaba |
| **Motivo** | Exigido cuando hay compromiso operacional (plan publicado u OT iniciada) — regla ya aprobada en M03-D1/E3 |

### J.4 Transiciones válidas

```
        (sin asignar)
         estado A: 0
              |
              |  asignar primera persona  -->  queda principal
              v
         estado B: 1                  <------------------+
              |  ^                                       |
              |  |  retirar al ultimo                    |  retirar auxiliar
              |  +---------------------------+           |  (principal no cambia)
              |                              |           |
              |  agregar integrante          |           |
              |  (es_principal = False)      |           |
              v                              |           |
         estado C: 2+  -------------------------------->-+
              |
              |  cambiar principal          (traspaso, sin salida)
              |  retirar al principal  -->  EXIGE nuevo principal, mismo acto
              v
         estado C o B, siempre con exactamente 1 principal
```

### J.5 Lo que ninguna operación de cuadrilla puede tocar

**[MEDIDO]** Confirmado en P4 y en F-A.2 N3:

```
programada_para · ProgramacionOrden · secuencia · dia · zona · prioridad
estado_operativo de la OT · el plan semanal
```

**[DISEÑO]** Única excepción deliberada: `revision += 1`, para la cola offline.

---

## K. GO / NO-GO para F-B

### K.1 Estado de las decisiones

```
F-1  CUADRILLA AD-HOC POR OT ............................ CERRADO
F-2  0 / 1 / 2+ INTEGRANTES, REGLA DE PRINCIPAL ......... CERRADO
F-3  es_principal ES LA FUENTE DE VERDAD ................ CERRADO
F-4  ROLES_CUADRILLA CATALOGO CERRADO ................... CERRADO
     RETIRO DEL PRINCIPAL .............................. CERRADO  (Decision A)
```

### K.2 Criterio

> *"GO solamente si no queda ninguna decisión empresarial crítica sobre la
> composición de la cuadrilla."*

**[DISEÑO]** Las cuatro decisiones de F-A.2 estaban cerradas; la única que
quedaba —el retiro del principal— **se cierra aquí con evidencia medida**.
**No queda ninguna decisión empresarial abierta sobre la composición de la
cuadrilla.**

# GO

### K.3 Lo que F-B recibe cerrado

| | |
|---|---|
| **Qué es una cuadrilla** | El conjunto de `AsignacionTrabajo` de una OT, agrupado por `orden_id`. Sin entidad nueva |
| **Estados válidos** | 0 / 1 / 2+, con la regla de principal de §J.2 |
| **Quién responde** | `es_principal`, siempre. `rol` no decide nada |
| **Roles** | Catálogo cerrado en la frontera de entrada (`ChoiceField`, **sin migración**) |
| **Retiro del principal** | Con sucesor nombrado, en un solo acto atómico |
| **Operaciones** | Asignar primera · agregar integrante · cambiar principal · retirar integrante · desasignar · consultar composición |
| **Locks** | `select_for_update` sobre la **OT**. Medido que serializa (P3) |
| **Auditoría** | `EventoTrabajo`, sin superficie nueva |
| **Lo intocable** | Programación, secuencia, fecha, plan, M09, `revisar_coherencia` |

### K.4 Lo que F-B arrastra, documentado y no bloqueante

**[RIESGO]** Ninguno es una decisión empresarial sobre la composición; son
deuda técnica conocida o alcance de otros pasos:

| # | Punto | Dónde se decidió |
|:--:|---|---|
| 1 | **El admin rodea toda regla de servicio** y no deja evento | F-A.2 §H — pasar `es_principal`/`rol` a `readonly` |
| 2 | **0 RLS, sin `org_id` propio** en `campo_asignacion_trabajo` | F-A.2 §M — fuera del alcance de F-B |
| 3 | **H-05 solo mira al principal**; el punto ciego crece con la adopción | §H — es M09, paso posterior |
| 4 | **`es_principal` tiene default `False`**, contradiciendo toda vía de escritura | F-A.2 §B.3 — migración identificada |
| 5 | **`EventoTrabajo.tipo` sin catálogo cerrado** | §F.4 |
| 6 | **Sin control de solape horario** de una persona entre OTs | F-A.2 §A.4 — corresponde a M09 |
| 7 | **Trigger `DEFERRABLE` como `RunSQL`**, invisible a `makemigrations --check` | §D.2 — deuda asumida a ojos abiertos |

---

## Anexo — Mediciones

**[MEDIDO]** Contenedor aislado, **0** credenciales de producción. Las
operaciones de retiro no existen: se **simularon** ambas formas.

```
P1  ESTADO INTERMEDIO DE LA OPCION B (paso 1 hecho, paso 2 no):
      integrantes 2 (el que debia salir sigue asignado) · principales 1
      invariante F-2 se cumple? .... True
      revisar_coherencia ........... 0 problemas
      H-05 ......................... 0 senales
      => estado incorrecto, LEGAL e indistinguible de una cuadrilla correcta

P2  OPCION A CON FALLO FORZADO A MITAD:
      estado antes == estado despues ... identico? True
      invariante ok? True (2 integrantes, 1 principal)
      eventos 1 -> 1
      => rollback completo, nada a medio hacer

P3  DOS CAMBIOS DE PRINCIPAL SIMULTANEOS, CON LOCK SOBRE LA OT:
      excepciones 0 · se serializaron ['->pc', '->pb']
      integrantes 3 · principales 1 · invariante ok? True
      CONTRASTE F-A.2 N6 (sin lock): 1 IntegrityError

P4  RETIRO DEL PRINCIPAL SOBRE UNA OT YA PROGRAMADA:
      programada_para IGUAL · estado IGUAL · secuencia IGUAL · dia IGUAL
      zona IGUAL · prioridad IGUAL · estado_linea IGUAL · updated IGUAL
      lineas del plan 1 · revisar_coherencia 0 problemas

P5  PRINCIPAL DECLARADO AUSENTE:
      composicion cambio? False · programacion cambio? False
      eventos nuevos 0 · senales H-05 1   (solo SENAL)
```

### Producción — foto de cierre

**[MEDIDO]** Solo `SELECT`, `read_only = True`. **15 claves → DIFERENCIAS:
NINGUNA.**

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · teams 0 · Disponibilidad 0 · operaciones_externas 0
kill switch detenido · tenant_config rapilink v146

asignaciones: rol=tecnico_lider  es_principal=True  ->  3   (sin cambios)
```

---

```
codigo ......... 0 archivos modificados    pruebas ... 0 (el temporal se borro)
migraciones .... 0    modelos .... 0    endpoints .... 0    serializers .... 0
AsignacionTrabajo  sin tocar    M09 ... sin tocar    revisar_coherencia ... sin tocar
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no

DECISION ....... OPCION A -- retiro del principal con sucesor, en un solo acto
VEREDICTO F-B .. GO
```
