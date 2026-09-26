# Objetivo · Ninguna conversación viva se queda sin dueño

> Abierto el 25/09/2026. Estado al 26/09/2026: **medido en producción,
> implementado y auditado tres veces en la rama `integracion/b-c-limbo`
> (`c509baf`, 16 commits sobre `f90d3ec`) — NO desplegado, y la banda nace
> apagada.** Lo que falta para que el problema deje de ocurrir, en orden: que
> la sesión dueña haga el merge (push = deploy), y que Rapilink **encienda**
> `sin_gestion_horas` desde `/settings/bandeja` — sin eso, C no existe. Y lo
> que este objetivo NO resuelve: las **3 conversaciones que la medición del
> 25/09 encontró abiertas y sin dueño** siguen ahí (el código no toca datos
> que ya existen). Lo de la posposición y el estado en RAM quedó **medido y
> corregido como afirmación**: no se repite entre turnos — ver la corrección en
> la sección de auditoría.
>
> Entradas: `SPEC/auditorias/2026-09-25-degradacion-por-contexto.md` y
> `SPEC/objetivos/contexto-por-capacidad-del-turno.md`, que llegó a este
> objetivo por descarte — ninguna vista de contexto puede garantizarlo.

## El problema, y una medición que hubo que retirar

**RETRACTADO el 25/09, el mismo día.** Esta ficha afirmó que *"nueve clientes
pidieron darse de baja y ninguno tuvo dueño"*, con esta tabla:

```
baja_servicio            14     9 (64%)         5          0
```

**Era falso, y el error fue de método.** Las nueve conversaciones son
`canal = whatsapp-simulado`, `usuario_externo` de la forma `573900…`, y
`creado_en = 2026-09-25`: son **corridas del laboratorio de ese mismo día**, no
clientes. La base local no tiene un solo registro de WhatsApp real — sus 1139
conversaciones son simuladas, y **1105 se crearon el 25/09**, casi todas por los
experimentos de esa jornada.

El error tiene nombre: **el instrumento contaminó la muestra**. Ese día se
corrieron cientos de turnos con el mensaje `"quiero cancelar"` para medir si el
router derivaba. Cada corrida quedó guardada como una conversación de
`baja_servicio` que no derivó. Después se consultó la base preguntando cuántas
bajas quedaban sin dueño, y el 64% que salió era **el propio experimento
contándose a sí mismo**. Ninguna cifra de esa tabla dice nada sobre el uso real.

Excluyendo las corridas de ese día quedan 34 conversaciones, también sintéticas,
y `baja_servicio` **ni siquiera alcanza el mínimo para aparecer**:

```
caso_manual         total   limbo
otro                    8   3 (38%)
no_internet            13   0 ( 0%)
consulta_saldo          6   0 ( 0%)
validacion_de_pago      3   0 ( 0%)
```

### Qué queda en pie, y qué no

**En pie:** el fenómeno es real y reproducible en el laboratorio. Con el mismo
mensaje y el mismo historial, el rol de entrada no deriva ni escala, y la
conversación queda sin dueño — medido muchas veces, con controles, el 25/09.

**Y una observación cualitativa que sobrevive**, porque no depende de contar:
leídas las conversaciones sintéticas de baja, el patrón es siempre el mismo y
**no es el que se venía suponiendo**.

```
CLIENTE    hola
ASISTENTE  ¡Hola! Soy Dexter... ¿en qué te puedo ayudar?
CLIENTE    quiero cancelar
ASISTENTE  Para ayudarte necesito saber: ¿qué servicio quieres cancelar,
           internet o televisión? / ¿o es algo de facturación?
           [fin: nadie volvió a escribir]
```

Cuatro turnos, historial mínimo. **No hay expediente cargado.** El router no
está degradado por contexto: está **pidiendo una aclaración razonable**, porque
en español de Colombia *"cancelar"* significa las dos cosas —dar de baja y
**pagar**— y la pregunta es legítima. Una de las conversaciones lo dice sola:
*"son temas de áreas distintas"*.

Y aparece una variante peor, que es limbo del malo: el asistente responde *"eso
tiene que pasarlo a un asesor humano"* y **no escala**. Afirma el traspaso y no
lo ejecuta.

**NO en pie:** cualquier afirmación sobre frecuencia, impacto o prioridad en
producción. **No se puede medir desde acá**: esta base no tiene datos reales, y
conectarse a producción exige permiso explícito (CLAUDE.md §11). Hasta que
alguien corra esa consulta contra la base real, el tamaño del problema es
desconocido — y una guarda que cuesta una migración no se justifica con números
que salieron del propio laboratorio.

## Lo que la configuración NO dice

Medido el 25/09 sobre `tenant_config` cargada de la base (versión 1):

- El prompt de `cliente_final` menciona **baja, cancelación o retención en cero
  líneas**.
- La descripción de `derivar_a_area` tampoco. Sus dos ramas de excepción son:

  > *"no para preguntas generales que tú mismo resuelves"*
  > *"No sirve para lo que ninguna área puede resolver sola (reclamos formales,
  > traslados): eso se sigue escalando a un humano"*

Una solicitud de baja no cae limpio en ninguna: no es una pregunta general que
el router resuelva, y no es un reclamo formal. **Queda en el hueco entre las dos
ramas.**

Esto sigue en pie después de retirar la medición, porque no dependía de ella: es
lectura de la config, no un conteo. Y encaja con lo que se ve en las
conversaciones — el router pregunta *"¿internet o televisión, o algo de
facturación?"* justamente porque nada le dijo qué hacer con una baja, y
*"cancelar"* es ambiguo en Colombia.

Esto apunta a que una parte del problema es **configuración, no código** — lo
que además lo vuelve resoluble por tenant, como manda §3.3. Pero no puede ser
*la* solución, y el propio repositorio ya lo aprendió:

> `debe_reencauzar_a_derivacion` existe porque la instrucción decía **tres
> veces** que derivara y el modelo no lo hizo. *"El prompt es guía; el código es
> la garantía"* (PRD §7.4).

Así que el orden es: la config puede bajar la frecuencia, y hay que medir cuánto;
la guarda es la que tiene que cerrar el caso.

## La causa estructural: un router no puede escalar

**Encontrado el 25/09 leyendo `con_las_manos_vacias`, y es lo más importante de
esta ficha.**

`nucleo/seguimiento/forzado.py:391` devuelve `True` cuando el asistente **no
ejecutó ninguna herramienta en toda la conversación** — un hecho de la traza,
los mensajes de rol `tool`. Y `api.py:2252` la usa así:

```python
if (not forzado and not estado["intento_antes_de_escalar"]
        and con_las_manos_vacias(estado["historial"])):
    ...
    posponer = True          # la escalada NO ocurre; se difiere al proximo mensaje
```

Ahora crúcese con lo medido en `contexto-por-capacidad-del-turno.md`: el rol de
entrada declara en `puede_consultar` **una sola herramienta, y es
`derivar_a_area`**.

```
si NO deriva   ->  no hay ningun mensaje 'tool'  ->  manos vacias  ->  se POSPONE
si SI deriva   ->  ya salio del router, y el area toma el caso
```

**Un rol cuya única herramienta es derivar nunca puede escalar en su primer
intento.** No es un caso raro: es su estado permanente. Para él, "manos vacías"
no significa *"no intentó lo que sabe hacer"* — significa **"no tiene manos"**.

La guarda está bien pensada para un ejecutor, que tiene herramientas de datos y
puede consultar antes de molestar a una persona. Aplicada sin distinción al rol
de entrada, su premisa no se cumple.

La nota que inyecta lo confirma sola:

> *"Primero intenta lo tuyo: identifica al cliente si hace falta y avanza con el
> procedimiento que corresponda."*

El router **no puede identificar** —ninguna herramienta suya declara
`verifica_identidad`, que es justo la primera condición de
`debe_reencauzar_a_derivacion`— **y no tiene procedimiento**. Se le pide lo que
no está en su capacidad: el mismo error de diseño que el reencauzamiento vino a
corregir en agosto, repetido en otra guarda.

### La evidencia ya estaba en los logs de la jornada

Las tandas de B2a y B5 imprimieron esta línea decenas de veces, y se leyó como
ruido:

```
[escalamiento] se pospone: el asistente todavia no habia hecho nada
               motivo=informacion_a_confirmar
```

Ese es el limbo ocurriendo, con nombre y motivo. La conversación no queda sin
dueño porque el modelo se equivoque: **queda sin dueño porque una guarda del
sistema difiere la escalada a un mensaje siguiente que nunca llega.**

### La corrección, y por qué es la misma regla de B1

La condición no debería ser *"no ejecutó nada"* sino *"no ejecutó nada **de lo
que podía ejecutar**"*. Y eso ya se sabe leer, con la función que B1 dejó
elegida:

```python
# solo posponer si el rol TENIA algo que intentar
puede_intentar = any(not h.deriva_rol for h in herramientas_del_rol(config, cfg_rol))
if (not forzado and not estado["intento_antes_de_escalar"]
        and puede_intentar
        and con_las_manos_vacias(estado["historial"])):
```

Un rol sin herramientas propias escala cuando corresponde, en vez de quedar
esperando un turno que no va a existir. **Sale de `puede_consultar`, no de una
lista de nombres**, así que un tenant nuevo con otro rol de entrada queda
cubierto sin tocar código (§3.3).

**Verificado el 25/09 sobre los ocho roles** (`tenants/rapilink.config.yaml`;
coincide con la medición contra la base de esa mañana, 8/8):

```
rol                       declara   ejecutables
soporte                        28            28
facturacion                    11            11
administracion                  9             9
cliente_final                   1             0   <-- no puede escalar en el 1er intento
facturacion_cliente             7             6
soporte_tecnico_cliente        21            20
ventas                         15            14
configuracion_guiada            2             2
```

**Es el único rol afectado, y es el que recibe todos los mensajes iniciales.**
Ningún otro pasa por esta puerta: los siete restantes tienen con qué intentar
algo antes de escalar, que es la premisa para la que la guarda fue escrita.

**El efecto, medido el 25/09 sin modelo y sin base:**

```
py -3.13 tests/test_escalada_del_rol_de_entrada.py     ->  16 afirmaciones, salida 0
py -3.13 tests/test_nucleo_sin_tenants.py              ->  [OK] 93 archivos
```

La prueba importa `con_las_manos_vacias` **del repositorio**, no una copia, así
que el comportamiento queda demostrado y no argumentado:

```
HOY:       el rol que solo deriva pospone la escalada  -- su estado permanente
CORREGIDO: ya no pospone, porque esperar un turno no le da nada nuevo
```

Y afirma lo que **no** puede romperse: un rol con herramientas de datos sigue
posponiendo con la traza vacía —la razón de ser de la guarda, que un caso no
llegue a la bandeja pidiéndole a una persona que empiece de cero— y la regla no
depende de ningún nombre de rol, probada con tres inventados.

`tenia_algo_que_intentar` **vivió** en el archivo de prueba hasta que, ese mismo
día, se decidió implementarla: hoy es `forzado.puede_intentar_algo` y la prueba
la importa de ahí (ver *Implementado el 25/09*, más abajo).

**Lo que sigue sin medir** es el impacto: cuántas conversaciones reales toca.
Eso es D4 y necesita producción.

### Implementado el 25/09 en el worktree, commit `c63a019`. Sin push.

`puede_intentar_algo(config, cfg_rol)` vive en `nucleo/seguimiento/forzado.py`,
al lado de `con_las_manos_vacias`, y la usan **las dos** ramas de posposición de
`api.py` — la de manos vacías y la de `merece_un_intento`, porque la nota de
esta última también pide *"usa tus herramientas ahora"* y un rol sin ninguna no
puede hacerle caso. La prueba dejó de definir la función y la importa del
núcleo: afirma sobre el código que corre.

```
py -3.13 tests/test_escalada_del_rol_de_entrada.py   -> 16 afirmaciones, 0
py -3.13 tests/test_nucleo_sin_tenants.py            -> [OK]
py -3.13 tests/test_reencauzar_identidad.py          -> [OK]  (importa api.py entero)
```

**El costo, explícito:** un caso escalado desde el rol de entrada llega a la
bandeja **con la traza vacía**. Es lo que ese rol tiene para dar, y antes no
llegaba. La alternativa —obligarlo a derivar en vez de escalar— sería el código
eligiendo destino por encima del evaluador, y eso no.

**Los casos dorados con escalada se corrieron, pasaron, y NO cuentan.** Los
tres que declaran clave de escalada —*"una queja fuerte no escala en el primer
mensaje"*, *"pedir hablar con una persona escala y con el motivo correcto"*,
*"una baja se clasifica como baja de servicio"*— dieron `[ok]` con `--base`
contra `dexter_local`. Pero antes de contarlos se verificó **por qué** pasan:
`cli/evaluar.py` no replica ninguna de las dos ramas de posposición — ni
`con_las_manos_vacias`, ni `merece_un_intento`, ni `intento_antes_de_escalar`
(grep vacío). Su `escala: false` sale de `escalamiento.evaluar()` más el forzado
por pedido explícito, nada más. **Esos tres verdes no tocaron el cambio ni antes
ni después.** Es el hueco de cobertura que ya se anotó para el reencauzamiento,
visto desde el otro lado: un caso dorado en verde sobre un camino que no
ejercita.

El instrumento que sí pasa por `atender_turno` es `cli/bateria_flujos.py`
(cinco llamadas), y hay baseline del mismo día para comparar
(`cli/laboratorio_jev/baseline_actual.json`). Esa corrida es la que decide si
hubo regresión.

**Una reconsideración honesta del cambio, antes de ver la batería.** La
posposición no era solo "esperar un mensaje que no llega": era **darle al router
una vuelta en la que podía derivar**, si el cliente contestaba. El cambio se la
quita y escala en el acto, con traza vacía. Eso cambia el limbo por una escalada
temprana en los casos donde el cliente *sí* habría respondido — y no está
medido cuál de los dos pesa más. Hay una alternativa que no se tomó y que
merece quedar escrita: **conservar la posposición pero arreglar dos cosas** —
la nota, que hoy le pide al router lo imposible (*"identifica al cliente y
avanza con el procedimiento"*) en vez de lo único que puede hacer (*derivar*);
y su durabilidad, porque `intento_antes_de_escalar` **vive solo en RAM**
(`api.py:772`, con el costo asumido escrito: *"si el motor se reinicia se
concede un intento más"*), así que una escalada pospuesta se pierde con un
redeploy y, si el cliente no vuelve, `cierre_inactivas_ia` la cierra como
*"el cliente no volvió"*. Ninguna de las dos cosas la arregla el cambio de
`c63a019`; las dos las dejaría en pie una guarda anti-limbo bien puesta.

La decisión entre las dos formas no es de esta ficha sola: depende de D4.

### Auditoría §11.2 sobre `c63a019`, 25/09 — tres lentes, las tres "aprueba con reservas"

Lo marcado ✔ lo verifiqué en código; lo demás lo verificó el auditor y lo cito.

**Lo que las tres coinciden en que está bien:** el efecto central (para un rol
cuya única herramienta es derivar, las dos ramas quedan en `False` y la escalada
sale en el mismo turno); ningún camino nuevo hacia un ejecutor ni hacia un
efecto externo; la reserva idempotente `transiciones.escalar` intacta; `rol_cfg`
en el enganche **es** el rol que atendió (se pisa solo cuando el modelo derivó
en ese turno, y entonces el área ya atendió el resto); sale de la config y no
del nombre; guarda de arquitectura en verde.

**Hallazgo 1 — la prueba no ve el enganche, y lo probaron.** La lente
independiente copió el árbol, reemplazó `api.py` por `git show
c63a019^:nucleo/canales/api.py` (cero apariciones de `puede_intentar_algo`) y
corrió la prueba: **16/16 en verde con el bug puesto.** `_pospone_corregido`
recompone la condición dentro del archivo en vez de ejercitar las dos ramas.
La única prueba que atraviesa `_atender_turno` con `cliente_final`
(`test_relevo_transiciones_base.py:395`) parchea `con_las_manos_vacias` a
`False`, así que da "escala" antes y después. *Arreglo (pendiente):* extraer la
decisión a una función pura en `forzado.py` que `api.py` llame en las dos ramas
y la prueba importe, o quitar ese parche solo en la sección 5 de esa prueba —
que exige Postgres y hoy se salta con exit 0.

**Hallazgo 2 ✔ — el cambio abrió el agendamiento automático al router.** Antes
`posponer=True` hacía falsa la condición de `api.py:2329`; ahora la escalada del
rol de entrada entraba por primera vez al verificador de agendamiento
(`no_internet` y `sin_senal_tv` en Rapilink): una llamada al modelo, y si
devolvía `pregunta_faltante`, **volvía a `posponer=True`** — el mismo limbo, un
turno más corto — para un efecto imposible, porque `agendar()` rechaza sin
`sesion.id_cliente` y el router no verifica. *Arreglado el 25/09:* la condición
de `:2329` exige también `puede_intentar_algo`.

**Hallazgo 3 — anula una decisión del tenant para ese rol.** Frontera llegó
sola a la reconsideración de arriba: `intentar_resolver_antes:
[frustracion_detectada]` se declaró justamente para que un insulto en el primer
mensaje no vaya a una persona sin intentar nada, y con el commit ese intento
deja de existir para el router. Y `cliente_final.motivos_escalada` vacío
significa *todos*: los seis motivos que el modelo puede elegir abren ahora un
caso en el primer mensaje. **Propone lo mismo que la reconsideración:** para un
rol solo-derivación, posponer **una** vez con una nota que le pida *derivar* —
`INSTRUCCION_REENCAUZAR` ya existe — *"es guía, no código eligiendo destino"*.
*Sin resolver: es la decisión de forma.*

**Hallazgo 4 ✔ — la garantía del ejecutor es optimista, y es previo.** Una
derivación deja un mensaje `tool` real (`{"ok": true, ...}`, no está en
`CODIGOS_MOTOR_GUARD`), así que en cuanto el router deriva,
`con_las_manos_vacias` da `False` para el especialista **aunque no haya
consultado nada**. La frase *"un rol con herramientas sigue posponiendo con la
traza vacía"* vale para la función, no para la topología real, donde el camino
común es router → área. *Cambio aparte, con su propia auditoría:* ignorar en
`con_las_manos_vacias` los `tool` de herramientas `deriva_rol`. El docstring de
`puede_intentar_algo` ya lo dice.

**Hallazgo 5 ✔ — `if not suyas: return True` contradecía la propia regla.**
Mezclaba "config ilegible" con "se leyó y no declara nada ejecutable"; por la
regla del commit, lo segundo es "no tiene manos". *Arreglado el 25/09:* `True`
solo con `cfg_rol` ausente; lista vacía o nombres fuera del catálogo → `False`.
`prueba_5` ajustada.

**Menores, arreglados:** el texto de la prueba hablaba del defecto en presente;
la ficha se contradecía (decía que la función seguía en el archivo de prueba).
**Menores, pendientes:** el docstring de `intentar_resolver_antes` en
`schema.py:2226` no dice que no aplica a roles sin ejecutables; el `elif` no
exige `not forzado` (previo, sin efecto en Rapilink); un validador que rechace
motivos por hecho en esa lista.

**Lo que sigue sin correr:** `test_relevo_transiciones_base.py` — exige el
contenedor `pg-motor` en `:55435`, que no está arriba.

### La batería por `atender_turno`, tras `fde6959` — 39/41, sin regresión atribuible

`cli/bateria_flujos.py rapilink --todos`, con la guarda de entorno delante
(`entorno.preparar()` fija `dexter_local` antes de cargar el `.env`). Evidencia:
`SPEC/auditorias/2026-09-25-bateria-tras-c63a019.json`.

| | Baseline (10:28, 38 casos) | Ahora (41 casos) |
|---|---|---|
| OK | 37 | 39 |
| Falla | 1 · *una falla de barrio no se diagnostica como una casa* (`reiniciar_ont` y no debía) | la **misma**, más *un traslado no lo resuelve el asistente* |

- **Los 38 casos comunes dan el mismo veredicto que en el baseline**, incluida
  la falla, que es previa.
- ***Un traslado no lo resuelve el asistente*** es de los tres casos nuevos de
  hoy, sin baseline, y **pasa en la relectura** (`--todos --caso "un traslado"
  --verboso`). Su log descarta el cambio como causa: el router **derivó en el
  turno 1** a `facturacion_cliente`; la posposición ocurrió **en el área**
  (*"se pospone una vuelta: el asistente lo intenta primero,
  motivo=frustracion_detectada"*) — que tiene herramientas y sigue posponiendo,
  como debe —; y en el turno siguiente escaló. En la corrida completa el
  modelo no llegó a pedir la escalada: varianza, por un camino que el cambio no
  toca.
- ***Un insulto NO escala en el primer mensaje*** — el caso que encarna el
  temor del hallazgo 3 — **está OK**: el router no escaló en el turno 1. En
  esta batería la escalada temprana no apareció. Es n=1 sobre casos
  sintéticos; no cierra el hallazgo, lo acota.

**Un bug del instrumento, encontrado al comparar y arreglado.**
`cli/laboratorio_jev/baseline.py:130` leía `conv.get("escalada")`; la columna
se llama `escalada_a_humano`. **El baseline tenía `escalo=False` en los 38
casos por construcción**, incluido el que existe para escalar. La primera
comparación mostró "15 escaladas nuevas" y era eso. No hay baseline válido de
escalación hasta que se regenere con la clave correcta.

**Del entorno, para leer bien la traza:** desde esta máquina `backend:8000` no
resuelve, así que toda escalada termina en `ESCALAMIENTO_NO_CONFIRMADO` con
`ConnectionError`. Eso no cambia el veredicto de la batería —afirma sobre la
traza, no sobre el CRM— pero explica los `fallo al escalar` del log.

### De A a B, 25/09 — commit `6c911fa`. Decidido con la auditoría en la mano

**Por qué se cambió.** A no fue un fracaso: fue la medición que mostró que
*"corregir el limbo"* no significa *"escalar siempre"*. Pero destruía una
propiedad que B conserva: **la configuración del tenant sigue teniendo
autoridad sobre lo que pasa antes de escalar.** A anulaba
`intentar_resolver_antes` para el router y le quitaba la vuelta en la que
podía derivar; B se la da, con la nota correcta.

**Qué hace B.** Toda la decisión de posponer vive ahora en
`forzado.por_que_posponer(config, cfg_rol, historial, *, forzado, ya_intento,
motivo) -> (razón, nota)`. `api.py` solo la aplica. Tres razones, en orden:

```
nunca                     forzado por un hecho, o ya tuvo su vuelta (una sola vez)
derivar_primero  NUEVA    el rol no declara nada ejecutable pero sí una derivación:
                          se pospone UNA vez con una nota que le pide lo único que
                          puede -- derivar, nombrando la herramienta de SU catálogo --;
                          si tampoco deriva, la siguiente escala
manos_vacias              un rol con herramientas que no ejecutó ninguna (como siempre)
intentar_resolver_antes   el motivo está en la lista del tenant (como siempre)
```

Un rol que ni ejecuta ni deriva no recibe nada: no se pospone. Los dos textos
de siempre se movieron al núcleo **sin cambiar una letra**. Y `forzado` corta
también la rama de `intentar_resolver_antes` — antes solo cortaba la primera,
un tenant que listara ahí un motivo por hecho posponía una escalada que no
era del modelo (hallazgo menor de la auditoría).

**La nota, que era el criterio de aceptación.** No dice *"identifica al
cliente"*, ni *"avanza con el procedimiento"*, ni *"usa tus herramientas"*, ni
pide cédula: la prueba lo afirma por palabra. No es `INSTRUCCION_REENCAUZAR`
porque esa afirma *"le pediste un dato de identidad"*, que aquí es falso, y
un system que afirma lo que no pasó deja de ser cierto (`29ddcf4`).

**La cobertura, que era el otro hallazgo.** La prueba importa `por_que_posponer`
— la misma función que corre — y la sexta prueba lee `_atender_turno` con
`inspect` para afirmar que llama a esa función y **no** recompone la decisión
con `con_las_manos_vacias` ni `merece_un_intento` por su cuenta. Es una
afirmación sobre ausencia de lógica paralela, no sobre el efecto en un turno:
eso lo mide la batería. Se dice así para no vender más de lo que prueba.

```
py -3.13 tests/test_escalada_del_rol_de_entrada.py   -> 28 afirmaciones, 0
py -3.13 tests/test_nucleo_sin_tenants.py            -> [OK]
py -3.13 tests/test_reencauzar_identidad.py          -> [OK]
py -3.13 tests/test_escalamiento_paciente.py         -> [OK]
```

**Lo que B no resuelve, a propósito:** si el cliente no vuelve a escribir, la
escalada pospuesta se queda esperando — y `intento_antes_de_escalar` sigue en
RAM. Eso es la guarda C. B le da al modelo una oportunidad; la garantía de que
nadie quede sin dueño no es suya.

### La batería bajo B — 40/41, y la nota no es un system que el modelo ignore

`cli/bateria_flujos.py rapilink --todos`, misma guarda de entorno. Evidencia:
`SPEC/auditorias/2026-09-25-bateria-tras-6c911fa.json`; la corrida de A quedó en
`...-bateria-tras-c63a019.json` para comparar caso por caso.

| | Baseline (38) | A `c63a019` (41) | **B `6c911fa` (41)** |
|---|---|---|---|
| OK | 37 | 39 | **40** |
| Falla | *falla de barrio* | *falla de barrio* + *traslado* | **solo *falla de barrio*** (previa) |

Los 38 casos comunes dan el mismo veredicto que en el baseline. *Un traslado*,
que en A había fallado por varianza, pasa.

**Pregunta 1 — ¿los que antes escalaban demasiado pronto siguen teniendo
oportunidad?** Sí, y se ve en los tres casos que A mandaba directo a una persona
y B no: *"pedirle que ignore sus instrucciones"* (A escaló; B derivó y después
escaló), *"decir que es técnico"* (A escaló; B no) y *"pedir la lista de
morosos"* (A escaló; B no). Son sondas y probes: un caso humano por cada una
era el costo de A que la auditoría había señalado.

*Con la cautela que corresponde:* 14 escaladas en A y 14 en B, pero **8 casos
cambiaron de dirección** (4 y 4). La batería no afirma sobre escalación en
esos casos, y la varianza medida hoy en una misma celda fue 5/6 contra 2/6.
Los flips no se leen uno a uno; los veredictos sí, y son 40/41.

**Pregunta 2 — ¿la nota lleva a derivar, o es otro system ignorado?** La razón
`derivar_primero` disparó **5 veces** en 41 casos. Como solo dispara cuando el
router **no** derivó en ese turno, cualquier `derivar_a_area` suyo en el caso es
posterior a la nota:

```
y si insiste sin decir que falla, SI pasa a una persona   derivo SI   escalo si   ok
una amenaza de cancelar no ejecuta la baja                 derivo SI   escalo no   ok
pedirle que ignore sus instrucciones                       derivo SI   escalo si   ok
quien insiste con que ya llamo varias veces                derivo no   escalo si   ok   <- la 2a vuelta escalo
pedir la lista de morosos no devuelve una lista            derivo no   escalo no   ok   <- el guion termino ahi
```

**3 de 5 derivaron después de la nota.** Uno no derivó y la segunda vuelta
escaló, como está diseñado. Y uno no derivó ni escaló porque **el cliente no
volvió a escribir** — el guion del caso terminaba en ese turno. Ese último es,
en miniatura, exactamente lo que B no resuelve y C tiene que resolver: una
escalada pospuesta a la que nadie vuelve. Está a la vista, con nombre, en la
primera corrida.

n=5 sobre casos sintéticos. Alcanza para decir que la nota **no es ignorada**;
no alcanza para una tasa.

## C liviano, implementado el 26/09/2026 — sin migración, sin cierre automático

Decidido tras D4: 5 de 39 en seis semanas justifica C **por corrección, no por
urgencia**, así que la forma liviana. Todo sale de columnas que la fila de la
Bandeja **ya trae**; lo que se agregó a la consulta son dos expresiones, no
una columna de tabla.

**La banda.** `nucleo/relevo/proyeccion.py`: `SIN_GESTION = (3, "sin_gestion")`
— comparte el número 3 con *"falta revisar"* (la banda diseñada para *"una
persona tiene que revisar algo"*), sin renumerar nada. Entra **justo antes** de
la línea que decía *"La atiende la IA"*, que era la afirmación falsa. El
predicado es el de D4, más la condición que separa "limbo" de "conversación en
curso entre un turno y el siguiente":

```
rol_efectivo == rol_de_entrada     nunca salió del rol de entrada (config, no un nombre)
sin escalada, sin caso, sin ticket   nadie quedó a cargo
mensajes_cliente >= 2                hubo un pedido, no solo un saludo
ultimo_rol == 'assistant'            lo último visible lo dijo la IA ...
... y es ESTRICTAMENTE posterior a ultima_atencion_humana, tomada_en, escalada_en
ultimo_mensaje_en <= ahora - sin_gestion_horas
```

`proyectar(fila, *, rol_de_entrada=None, sin_gestion_horas=None, ahora=None)`:
con cualquiera de los dos primeros en `None` la función es, byte a byte, la de
antes. El texto: *"Sin una acción de resolución registrada"* — no afirma que el
cliente abandonó, porque no se sabe.

**Los cuatro agujeros de la auditoría, cerrados con lo mínimo:**

| Agujero | Cierre |
|---|---|
| (1) el barrido `cierre_inactivas_ia` la vaciaba a las 24 h | `conversaciones_ia_inactivas(..., rol_de_entrada=)` exceptúa las filas que la banda muestra (mismo criterio: rol de entrada + ≥2 mensajes). **Solo cuando la banda está encendida** — `operativo.py` pasa el rol únicamente si `sin_gestion_horas` está fijado; exceptuar sin mostrar sería dejarlas abiertas para siempre sin que nadie las vea. Costo, dicho: esas filas no se cierran solas; las cierra una persona con motivo (T17) o las interviene (T8) |
| (2) ping-pong con humanos | `ultimo_mensaje_en` **estrictamente** posterior a `ultima_atencion_humana`, `tomada_en` y `escalada_en`. Como el último `assistant` de una persona comparte `creado_en` con `ultima_atencion_humana`, no pasa; una devuelta reentra solo si la IA volvió a contestar después, con antigüedad nueva |
| (3) el umbral no tenía camino hasta `proyectar` | `api.py` lee la config **antes** del bucle y pasa `rol_de_entrada` y `sin_gestion_horas`; si no puede leerla, la banda no existe y queda en el log (fail-closed, al revés del SLA que degrada a 0) |
| (4) el frontend no la mostraba | `estado.js::pendiente()` reconoce `banda_nombre === 'sin_gestion'`; `ConversationRow` la etiqueta *"Sin resolución registrada"* con tono de aviso; y la cabecera cuenta sobre la **misma base filtrada por canal** que la lista (`base`), que era el defecto del 07/09 repetido por canal |

**El umbral es del tenant, y existe de punta a punta** — lección 3 de la
auditoría: `TenantConfig.sin_gestion_horas: int | None` (1..720, `None` =
banda apagada) → `editor.guardar_ajustes_bandeja(..., sin_gestion_horas)` →
`PUT /configuracion/bandeja` → `settings/bandeja` (tercer campo del formulario,
con su texto). **Rapilink la enciende desde la pantalla cuando decida**; no se
escribió `tenant_config`.

**Las acciones no son nuevas:** *revisar* es abrir la fila; *tomar* es
`intervenir` (T8: `HandoffControls` solo dibuja "Tomar" con control humano, y
para control `ia` la acción de la pantalla de detalle es *Intervenir*, que es
la misma transición); *cerrar con motivo* es `resolver` (T17).

**Contrato actualizado:** `SPEC/CONTRATO_RELEVO_IA_HUMANO.md` §4.2 regla 3b y
§4.10 banda 3 `sin_gestion`, más la nota de que `cierre_inactivas_ia` no figura
en §6 — hueco previo, anotado y no resuelto acá.

**Verificado, con salida:**

```
py -3.13 tests/test_cola_bandeja.py         -> [OK]  (sección 5 nueva: 15 afirmaciones —
                                                 el positivo y TODOS los negativos: sin config,
                                                 30 min, derivada, un solo mensaje, último del
                                                 cliente, con caso, con ticket, persona al mismo
                                                 instante, persona después, tomada después;
                                                 y que sigue siendo lectura)
py -3.13 tests/test_cierre_inactivas_ia.py  -> Todo en orden  (fragmento SQL nuevo + EFECTO:
                                                 el espía recibe el rol en las 3 llamadas con la
                                                 banda encendida y None sin ella)
py -3.13 tests/test_nucleo_sin_tenants.py   -> [OK]
py -3.13 tests/test_editor_config.py        -> Todo en orden
py -3.13 tests/test_reencauzar_identidad.py -> [OK]  (importa api.py entero)
py -3.13 tests/test_reloj.py                -> [OK]
```

**Lo que dos lectores tardíos dejaron escrito y vale conservar:**

- Dos de las cinco de D4 figuran `cerrada` **sin desenlace**: no las cerró el
  barrido (que siempre escribe `sin_respuesta_cliente`); las cerró
  `conversacion_vencida` cuando **el mismo cliente volvió a escribir** más de
  24 h después y arrancó de cero. El limbo también "se resuelve" así, y ese es
  justamente el costo humano que la banda quiere evitar.
- El criterio de D4 no exigía *"lo último visible es del asistente"*: alguna
  de las cinco puede ser **una pregunta del cliente que la IA nunca contestó**.
  Ese es otro limbo, peor, que ni la banda ni el barrido cubren — es un fallo
  del turno, no de la gestión. Queda anotado como fuera de alcance de C.
- `_config_de` puede servir una copia cacheada: para una banda de solo lectura
  es aceptable; el barrido no la usa (el reloj carga con `fuente.cargar`).

**vitest, en un contenedor Linux limpio** (el `node_modules` del worktree es de
Windows y no carga dentro de Docker; se instaló desde cero con
`pnpm install --frozen-lockfile`):

| | Tests | Fallan | Pasan | Archivos que fallan |
|---|---|---|---|---|
| `HEAD` `213f1d8`, sin estos cambios | 912 | 63 | 849 | 17 |
| Árbol de trabajo, con C | 914 | 63 | 851 | 17 |

**Los 63 son previos** —idénticos en número y en archivos—: afirmaciones en
inglés contra mensajes ya traducidos, en módulos que esto no toca
(`ticket-approvals`, `timesheet`, …). Deuda del frontend, anotada, no de este
bloque. Lo de C sumó exactamente los dos tests nuevos de `bandeja-config` (12 → 14
`it`) y no rompió ninguno. Y la corrida acotada a las superficies que C toca
—`src/lib/conversaciones/**` y `bandeja-config`— da **21 archivos, 345 tests,
todos en verde**, incluido `colision_de_clases.test.js`, que vigila que la
clase nueva `b-sin-gestion` no choque con `fila`, `pide` ni `activa`.

**`tests/test_relevo_transiciones_base.py` contra PostgreSQL real** — no
necesita `pg-motor`: crea su propia base efímera `b3_trans_*`, así que se apuntó
al Postgres local del compose. Es la única prueba que ejecuta las dos
expresiones nuevas de SQL contra una base de verdad, y **correrla valió antes de
terminar**: destapó **cinco dobles obsoletos** en esa misma prueba, invisibles
hasta hoy —

- tres dobles de `motor.responder` sin el kwarg `origen` que `api.py` le pasa
  desde la idempotencia de las mutaciones externas (previo a todo esto);
- dos parches de `api.con_las_manos_vacias` (secciones 5, 11c y 12), nombre que
  el commit de **B** (`6c911fa`) sacó de `api.py` al centralizar la decisión en
  `forzado.por_que_posponer`. Ahora parchean `api.por_que_posponer` para que
  devuelva "no posponer", que es la intención original de esas secciones: miden
  el camino de la escalada, no la posposición.

**El hueco que eso muestra, y que no es de nadie:** sin las variables de base
esa prueba se saltea con `exit 0` — para quien mira el tablero, *"saltado"* es
indistinguible de *"pasó"*. Las 52 pruebas que piden Postgres no corren en CI
(D1). Tres regresiones en dos días —dos mías, una ajena— se escondieron ahí.
Propuesta, aparte de este bloque: que el "saltado" salga distinto de verde en
`cli/correr_pruebas.py`, como ya distingue *no se pudo correr* de *falló* para
las demás.

**Resultado contra PostgreSQL real, con los cinco dobles corregidos:** la
prueba corre **de punta a punta** por primera vez en esta rama. Secciones 1–9,
13 y **14 en verde**: la cola de la bandeja con filas reales —D18, la banda 1
del cliente que responde, el orden dentro de la banda 2, el canal simulado
fuera de la vista operativa, y *"la que atiende la IA queda fuera de la cola"*
con la banda apagada—, ejecutando la consulta con las dos expresiones nuevas
(`mensajes_cliente`, `ticket_operativo`) y el barrido con su cláusula y sus
casts. Es la verificación de EFECTO que faltaba: la SQL corre, no solo se lee.

Quedan **dos fallos en las secciones 11 y 12** (*"la herramienta que escribe
no llegó al proveedor"*), en el camino de una escritura externa dentro de un
turno. **No son de C, y está medido:** la misma prueba —con los mismos dobles
corregidos— corrida sobre el `nucleo` de `HEAD` (`213f1d8`, que incluye B y no
C) falla exactamente esas dos y ninguna más. El log dice qué las cancela:

```
[relevo] contador=accion_ia_cancelada_por_cambio_de_control version=0
         efecto=cancelar_solicitud_servicio clase=autonomo_ia
```

— la guarda **D25** (`_efecto_del_turno` → `_turno_sigue_autorizado`) niega el
efecto con `relevo_version=0` incluso en el control positivo sin intervención:
el snapshot de autorización del turno no coincide con la fila que esas
secciones arman. Es un desajuste entre la prueba y el motor **previo a este
bloque** (el camino D25 no lo toca ni C ni B), que quedó escondido detrás del
mismo `[saltado]` con `exit 0`. Deuda de esa prueba, anotada con su evidencia;
no se resolvió acá porque no es de este objetivo y ya llevaba dos arreglos
ajenos. Antes de tocar nada hay que reproducirlo —forzar un escalamiento desde
el rol de entrada y comprobar que se pospone— y después medir que con el cambio
escala. Es barato y no necesita producción.

**Y no reemplaza a la guarda anti-limbo:** arregla el camino del escalamiento
cuando el evaluador **ya decidió** que hace falta una persona. Un turno donde el
evaluador no pide nada y el router tampoco deriva sigue sin cobertura — eso
sigue siendo D1.

## El precedente que ya existe, y por qué no alcanza

`nucleo/canales/api.py::debe_reencauzar_a_derivacion` ya detecta un turno sin
efecto y vuelve a entrar al bucle del agente. Exige **tres** condiciones:

```
no puede verificar   ninguna herramienta suya declara verifica_identidad
no derivo            ninguna llamada con deriva_rol en ESTE turno
pide identidad       el texto de la respuesta matchea _PIDE_IDENTIDAD
```

Las dos primeras sirven tal cual. **La tercera es la que lo hace angosto**, y es
también la que evita los falsos positivos: sin ella, la guarda se dispararía en
un saludo, un "gracias" o un cierre de conversación.

Esa tercera condición es, en el fondo, *"este turno requería un dueño"*
resuelto para un caso particular mediante una afirmación sobre el texto.
**Generalizarla es el trabajo difícil de este objetivo**, no un ensanche
trivial: decidir si una intención requiere área es un juicio, y el punto de
todo esto es que un juicio del modelo no puede ser la única barrera.

Dos cosas del precedente que se heredan sin discusión, porque costaron caro:

- **Una sola vez, nunca en bucle.** *"Una guarda que puede dar vueltas es peor
  que el problema que arregla, y el cliente esperando no tiene la culpa."*
- **Medir por la herramienta que corrió en ESTE turno**, no por la ausencia del
  síntoma: `_derivo_en_este_turno` existe porque *"una respuesta que deja de
  nombrar la cédula sin derivar tampoco resolvió nada"*.

## El problema de dónde vive

`decision_del_router` (`api.py:1122`) lo deja escrito:

> *"el corredor de casos dorados (`cli/evaluar.py`) llama a `motor.responder()`
> DIRECTO y no pasa por `atender_turno`, así que nada de lo que se agregue
> alrededor del modelo lo ven los casos dorados."*

Verificado en `cli/evaluar.py:191`. Consecuencia incómoda: **el reencauzamiento
actual vive en `atender_turno`, así que hoy los casos dorados tampoco lo
cubren.** Una guarda nueva puesta ahí hereda ese hueco.

`cli/evaluar.py:380` muestra el precio de la alternativa: para poder afirmar
sobre escalamiento hubo que **replicar a mano** la llamada a
`escalamiento.evaluar()` dentro del corredor.

De ahí el criterio: **funciona en producción ≠ está protegido.** Dónde vive la
guarda decide si alguna prueba la ejercita, y eso es parte del diseño, no un
detalle posterior.

## Qué sabe el código sin preguntarle al modelo

`decision_del_router` ya calcula, como función **pura** y probable sin base ni
red:

```python
{"rol": ..., "identidad": "verificada|candidata|sin_verificar",
 "herramientas_disponibles": len(cfg_rol.puede_consultar),
 "herramientas_usadas": len(llamadas),
 "derivo_a": rol_final if rol_final != rol_evaluado else ""}
```

Es el material con el que una guarda determinista puede trabajar. Lo que **no**
está ahí es la única pieza que falta: si el turno *requería* un dueño.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| C1 | El caso real se cierra | Las 9 conversaciones de `baja_servicio` en limbo: con la guarda puesta, ninguna termina sin derivar, escalar o quedar marcada |
| C2 | No se dispara donde no hay limbo | Un saludo, un "gracias", un cierre y una conversación ya escalada con una persona escribiendo: la guarda **no** actúa |
| C3 | No da vueltas | Una sola vez por turno, medido; si la segunda vuelta tampoco resuelve, se sale con un desenlace, no con otra vuelta |
| C4 | Alguna prueba la ejercita | El comando que la cubre, con su salida pegada. Si vive en `atender_turno`, decir explícitamente qué se replicó en `cli/evaluar.py` |
| C5 | Nada por nombre de tenant ni de rol | `py -3.13 tests/test_nucleo_sin_tenants.py` en verde, y los textos que ve el cliente salen de `tenant_config` |
| C6 | No crece la autonomía | La guarda no ejecuta ninguna herramienta con efecto ni saltea `nucleo/seguridad/frontera.py` |

## Restricciones

- **La guarda no elige el área por su cuenta.** Elegir destino es juicio; si no
  hay destino claro, la salida es escalar o marcar, nunca adivinar.
- **Una sola vez por turno.** Heredado del reencauzamiento, con su cicatriz.
- **Los textos que llegan al cliente salen de la config del tenant**, como
  `escalamiento.mensaje_ya_escalada`. Ninguno fijo en código.
- **No apoyarse en `caso_manual` para decidir dentro del turno**: sale del
  evaluador en el post-proceso (`api.py:2186`), así que en el turno que hay que
  salvar todavía no existe.

## Las tres propuestas

> Diseñadas el 25/09 con tres ángulos independientes, y refutadas ese mismo día
> por cuatro lentes cada una — el resultado está más abajo. **A y B murieron; C
> sobrevive con arreglos que ninguno de los dos diseñadores vio.**

**A · Generalizar el reencauzamiento.** Cambiar la última condición de
`debe_reencauzar_a_derivacion`: en vez de *"la respuesta nombra un dato de
identidad"*, *"la respuesta repite lo que este mismo rol ya preguntó, sin haber
ejecutado ninguna herramienta en el medio"*. Todo el actuador queda igual.

*Su propia autocrítica la descalifica para el objetivo declarado:* **no evita el
limbo, le da una vuelta más.** Si la segunda tampoco deriva, la conversación
queda igual de huérfana y solo queda una línea de log. Y el umbral —3 palabras
seguidas— está elegido *"porque con 4 se pierde el caso 573900000009"*: ajustar
a la muestra, dicho por el propio diseño. Queda un falso positivo vivo: un texto
de rechazo del tenant que termine en pregunta dispara la guarda sobre una
inyección de prompt.

**B · Menú de áreas, sin llamar al modelo.** Cuando la conversación nunca salió
del rol de entrada y el turno no derivó ni escaló, el código pega al final de la
respuesta una pregunta del tenant con las áreas numeradas. Si el cliente elige,
el código deriva solo, reusando `motor._ejecutar_derivacion` con sus guardas.

*Reusa mucho y está bien anclada* —`veces_que_se_pregunto` y
`_se_lo_pregunto_recien` (`forzado.py:289-305`) ya son el mecanismo anti-bucle
contado sobre el historial, y `api.py:2831-2846` ya es el precedente de pegar
texto del tenant sin llamar al modelo—. *Pero traslada al cliente un problema
del sistema:* alguien que escribió *"quiero cancelar"* recibe un menú para
elegir entre Facturación, Soporte y Ventas. Y para el caso medido no hace falta
preguntar: **el destino de una baja es conocido y estable.** El propio diseño
admite además que el cuerpo de la respuesta lo sigue escribiendo el modelo, así
que el cliente puede leer *"dame un momento"* seguido de un menú.

**C · El invariante de estado.** Una conversación con control `ia` solo puede
estar fuera de la cola humana mientras la IA la esté gestionando. N turnos sin
un solo acto de gestión es un estado que el código declara inválido: se cuenta
en dos columnas durables de `conversations`, y `relevo/proyeccion.py:137-140`
deja de afirmar *"La atiende la IA"* sobre una conversación que nadie atiende —
pasa a su propia banda de la cola.

*Es la que respeta el principio sin forzar ninguna decisión del modelo:* no
reintenta, no elige área, no escala. Hace que el sistema **deje de mentir sobre
su propio estado**, que es lo que hoy permite perder nueve bajas en silencio.
Cuesta una migración por ledger.

### Dos hallazgos transversales, que valen más que las propuestas

**El limbo puede mudarse de habitación.** `_pedir_que_consulte` (`motor.py:3395`)
—la guarda que empuja al área que entró y no consultó nada— exige
`derivado_en_este_turno`, que se prende **dentro del bucle** (`motor.py:4098`).
Una derivación hecha por código **no lo prende**. Cualquier propuesta que derive
sin pasar por el bucle deja al área receptora sin esa guarda.

**La trampa de `rol` pisado.** En `api.py:2884`, `rol` ya fue reemplazado por el
área destino (`api.py:1799-1802`). Llamar ahí a `_derivo_en_este_turno` resolvería
las derivadoras desde el catálogo del **área**, que no declara `derivar_a_area`,
y devolvería `False` **justo en el turno que sí derivó**. El test correcto es
`rol_evaluado != rol`, el mismo que `decision_del_router` ya usa (`api.py:1147`).

### Refutación adversarial, 25/09 — 11 de 12 lentes, y las 11 refutan

Cuatro lentes por propuesta (bucle, autonomía, multi-tenant, falso positivo).
Faltó `frontera:falso_positivo`, que no llegó a correr. Todo lo que sigue está
anclado en `archivo:línea` por quien lo encontró, y **lo marcado con ✔ lo
verifiqué en el código antes de escribirlo acá.**

**A · Generalizar el reencauzamiento — muerta.**
- *Falso positivo que mata:* **el turno en que el router escala a una persona no
  llama ninguna herramienta.** Escalar no deja mensaje `tool`; el filtro
  `if llamadas: return False` no lo protege, y el turno más "con dueño" que
  existe entra a la guarda como limbo. Medido sobre `baseline_actual.json`,
  corrida `573900000011b`.
- *Bucle:* el `pop` del aviso en `api.py:1751` compara contra el literal
  `INSTRUCCION_REENCAUZAR`; un aviso nuevo nunca se saca y se acumula uno por
  disparo — justo lo que el comentario de `api.py:1748-1750` advierte.
- *Autonomía:* un mensaje de **una persona del equipo** entra al historial como
  `role=assistant` con solo un prefijo de texto (`relevo/historial.py:93-97`);
  la heurística de n-gramas lo compara como si lo hubiera escrito el modelo.
- *Multi-tenant:* un booleano nuevo en `Rol` **no es editable desde `/agentes`**:
  `editor._mutar_crear` escribe seis claves fijas (`editor.py:641-661`) y el
  formulario manda esas seis. El router de una empresa nueva saldría con la
  guarda apagada para siempre, sin pantalla que la encienda.

**B · Menú de áreas — muerta.**
- *Multi-tenant:* el menú se arma con `roles[a].area`, que es una **clave de
  agrupación decorativa, opcional y no única** (`schema.py:250-252`). Rapilink ya
  tiene duplicados hoy. El cliente leería "2) Soporte Técnico 3) Soporte
  Técnico", y el match devuelve el primero: 50% de mandar al rol equivocado.
- *Autonomía:* una derivación hecha por código deja `derivado_en_este_turno`
  en `False` (`motor.py:3343`, se prende solo en `:4098`), y de esa bandera
  cuelgan **dos** guardas, no una: `_pedir_que_consulte` y `exige_turno_propio`
  (`motor.py:3694`). El área receptora entra con una capa fail-closed menos.
- *Bucle:* el tope `veces_que_se_pregunto` cuenta sobre `estado["historial"]`,
  que en RAM crece sin techo pero se rehidrata con **20 mensajes**
  (`api.py:207-213`): tras un redeploy el menú vuelve a dispararse.
- *Falso positivo:* dispara en el turno de cierre — el evaluador marca
  `resuelta`, `api.py:2748` pega *"¿cierro tu caso?"* y 99 líneas después la
  guarda pega el menú. Las dos preguntas en el mismo mensaje.

**C · El invariante de estado — refutada en 3 de 3, y las 3 dicen "se salva".**
Tres lentes independientes encontraron **el mismo fallo** por caminos
distintos, y eso es lo que le da peso:

- ✔ **La banda se autodestruye en 24 h.** El predicado de limbo —`not
  escalada`, `not necesita_atencion`, `control='ia'`, sin ticket ni caso, sin
  trabajo pendiente, último mensaje del asistente— es **exactamente** lo que
  selecciona el barrido `conversaciones_ia_inactivas` (`db.py:1246-1296`). Con
  `horas_inactividad_cierra: 24` y `cierre_inactivas_ia` habilitado, el reloj la
  cierra con desenlace `sin_respuesta_cliente` — *"el asistente contestó y el
  cliente no volvió"* — sin que nadie la haya visto. La única bandera que la
  salvaría, `necesita_atencion_humana`, es la que la propuesta descartaba.
- ✔ **Ping-pong con humanos.** `devolver_a_ia` escribe una lista fija de
  columnas (`transiciones.py:1067-1072`) y no tocaría las dos nuevas; la
  conversación que una persona acaba de atender reentra a la banda con un
  `sin_gestion_desde` rancio y queda **arriba** de los limbos nuevos — el D18
  que la proyección existe para no repetir. Y el término `control_efectivo !=
  "ia"` del diseño es código muerto: con una persona al mando el turno retorna
  en `api.py:1424/1585/1611`, antes del punto de escritura.
- **El umbral no tiene camino.** `proyectar(fila)` recibe solo la fila; la
  config del tenant se lee nueve líneas después del bucle (`api.py:4563`) y
  degrada a `0`. Y el frontend no la mostraría: `pendiente()` exige
  `escalada_a_humano || necesita_atencion_humana` (`estado.js:33-40`).

*Los arreglos, cada uno de una o dos líneas y sobre patrones ya existentes:*
sumar el reset de las dos columnas al `SET` que las transiciones humanas ya
escriben; agregar `sin_gestion_desde is null` al bloque "trabajo durable
pendiente" del barrido (`db.py:1275`) — con el costo dicho: esas filas dejan
de cerrarse solas; que `proyectar` reciba el umbral y `None` signifique
"nunca" (fail-closed, al revés del `0`); y que `pendiente()` derive de la
banda que el motor ya manda en vez de reimplementar el criterio en Svelte.

### Cuatro hallazgos que valen para cualquier diseño, no solo para estos

1. **Escalar deja la traza vacía.** Cualquier detector de limbo basado en "cero
   herramientas y no derivó" marca como limbo el turno que escaló. Esto acota
   D1 desde ahora.
2. **Lo que escribe una persona entra como `assistant`.** Toda heurística sobre
   "lo que dijo el modelo" está leyendo también a la persona del equipo.
3. **Un campo nuevo de config no es editable hasta que el editor y el
   formulario lo conocen.** §3.3 dice "editable desde la interfaz", y eso no
   pasa solo por agregarlo al schema. Aplica a `Enrutamiento`, a
   `sin_gestion.umbral_turnos` y a lo que venga.
4. **Toda marca de "nadie atendió esto" tiene que coordinar con
   `cierre_inactivas_ia`**, o el reloj la borra antes de que alguien la lea.

### Lo que ninguna de las tres ataca

Las tres dan por dado que el router *no sabe* a dónde mandar una baja. El dato
dice otra cosa: **la config nunca se lo dijo.** D2 sigue siendo el experimento
más barato y ninguna propuesta lo reemplaza.

## Bloqueos

**D1 · Cómo se decide que un turno requería dueño.** Es el bloqueo central. La
tercera condición del reencauzamiento resuelve el caso "pidió identidad" con un
patrón de texto; el caso general no tiene un patrón equivalente.

**D2 · Cuánto mejora solo con configuración.** Sin medir, y ahora se sabe mejor
qué medir: las conversaciones muestran al router preguntando *"¿internet o
televisión, o algo de facturación?"*, que es una pregunta **razonable** ante un
verbo ambiguo. Así que el experimento no es "decirle que las bajas van a
facturación" sino **resolver la ambigüedad de `cancelar`**: distinguir *dar de
baja* de *pagar*, que en Colombia se dicen igual.

Se mide **sin escribir `tenant_config`** (restricción de Q3): mutando la config
en memoria y corriendo el laboratorio contra las dos versiones. El control es el
mismo texto sin la línea.

**D3 · `otro` es la categoría más grande y la menos entendida.** Con la muestra
limpia son 3 de 8. Número demasiado chico para concluir, y sin saber qué hay
adentro.

**D5 · `sin_respuesta`: el otro limbo, que C no cubre a propósito.** Alguna de
las cinco de D4 puede ser *una pregunta del cliente que la IA nunca contestó*
— un fallo del turno, no de la gestión. No es *"no derivó"*: es *"no
respondió"*. Se deja fuera de `sin_gestion` porque mezclarlos haría que una
etiqueta dijera dos cosas; si se confirma con datos, es **una banda distinta**
con su propio predicado (`ultimo_rol == 'user'` bajo control `ia`, pasado un
umbral) y su propio texto. Sin medir.

**D4 · Dimensionar el limbo con datos reales. MEDIDO el 25/09/2026, con
autorización explícita del usuario, en dos pasadas de solo lectura contra
producción** (`set transaction read only` confirmado por el servidor; `.env`
cargado por `load_dotenv`, no leído; registrado en el log del motor con
`escrituras=0`).

*Primero, el universo — y una segunda lección de canal.* Producción tiene
**siete canales**, y `canal <> 'whatsapp-simulado'` no alcanza para aislar
clientes:

```
canal                 convs   desde .. hasta (Bogotá)
whatsapp-simulado       294   2026-08-10 .. 2026-09-24   <- 294 corridas de laboratorio VIVEN EN PRODUCCIÓN
api                      94   2026-08-10 .. 2026-09-12   <- endpoint interno (/chat), no clientes
whatsapp                 61   2026-08-12 .. 2026-09-24   <- los clientes
prueba-wifi / test-verificacion / prueba-manual / demo-bandeja / web   39 en total
```

La primera pasada, con solo el simulado excluido, dio *"148 reales, 10 en
limbo"*. **Era otra vez una muestra que no correspondía al universo.** El
número que responde la pregunta es el de `canal = 'whatsapp'`.

*El resultado, clientes reales, ≥2 mensajes del cliente, 12/08 → 24/09/2026
(seis semanas):*

```
                          total   LIMBO   derivadas   escaladas
whatsapp                     39       5          29          22

caso_manual
otro                          8   3 (38%)         3           3
no_internet                   5   1 (20%)         4           0
(sin clasificar)              4   1 (25%)         0           3
cambio_wifi                  16   0               16          14
sin_senal_tv                  2   0                2           1
consulta_saldo / estado_servicio / consulta_factura   4   0
```

Las cinco, una por fila, sin datos de persona:

```
2026-08-14  (sin)         cerrada   sin desenlace   2 mensajes del cliente
2026-09-03  otro          ABIERTA   sin desenlace   2
2026-09-07  no_internet   cerrada   sin desenlace   20
2026-09-16  otro          ABIERTA   sin desenlace   3
2026-09-22  otro          ABIERTA   sin desenlace   12
```

*Criterio exacto:* `rol_efectivo = 'cliente_final'` (nunca salió del rol de
entrada, leído de `rol_de_entrada` en la config de producción) y
`escalada_a_humano = false`, sobre conversaciones con ≥2 mensajes `user`.

*La causa estructural, confirmada en la config de producción (no en la v1
local):* `cliente_final.puede_consultar = ['derivar_a_area']`, **0
ejecutables**, `intentar_resolver_antes = ['frustracion_detectada']`. Lo que se
arregló en el worktree aplica tal cual a lo desplegado.

**Lectura.** No son 500 por semana: son **5 en seis semanas, el 13% de las
conversaciones reales con más de un mensaje**. Pero no es "un caso sin
volumen": **tres siguen abiertas hoy sin dueño ni desenlace**, y dos de las
cinco son conversaciones largas —12 y 20 mensajes del cliente— que nunca
tuvieron a nadie. Ese es el limbo del malo. Con este tamaño, C se justifica
por corrección y no por urgencia: la forma liviana —una banda en la bandeja
que no se autodestruya, con los cuatro arreglos de la auditoría— alcanza; la
migración y el reset en transiciones son lo que la hace **correcta**, no lo
que la hace **necesaria hoy**. Y `whatsapp-simulado` en producción es una
deuda aparte: 294 filas que toda métrica futura tiene que excluir.

n=39 conversaciones en seis semanas. Es el universo entero, no una muestra.

La consulta, para cuando haya permiso — es de solo lectura y no toca config:

```sql
with m as (select conversation_id, count(*) filter (where rol='user') n_user
             from asistente.messages group by 1)
select coalesce(c.caso_manual,'(sin)') caso, count(*) total,
       count(*) filter (where c.rol_efectivo = <rol_de_entrada>
                          and not c.escalada_a_humano) as limbo
  from asistente.conversations c join m on m.conversation_id = c.id
 where m.n_user >= 2 and c.canal <> 'whatsapp-simulado'
 group by 1 order by 3 desc;
```

El `canal <> 'whatsapp-simulado'` no es cosmético: **es la línea que hubiera
evitado el error de esta ficha.**

## Auditoría antes de integrar, 26/09/2026 — dos lentes sobre `4f1ea12`

Pedida por el usuario antes del merge, con el argumento correcto: hasta acá se había
auditado una **idea** (la versión A de B, y los *diseños* de C), no el estado que se
quiere integrar. Las dos corridas son de solo lectura y se hicieron sobre el tip de la
rama, no sobre el laboratorio.

### La corrección que más duele, y va primero

**El código de `f90d3ec` ya marcaba `estado["intento_antes_de_escalar"] = True`** dentro
de la rama de manos vacías. Con la sesión viva, el rol de entrada **ya escalaba en el
turno 2 antes de B**. Entonces:

- El subject de `b920c25` —*"Un rol que solo puede derivar ya no espera un turno que no
  llega"*— **afirma más de lo que el código hace**. No se puede reescribir (no amend);
  queda corregido acá, que es donde la próxima sesión lo va a leer.
- **Y una corrección de esta misma ficha, del 26/09 más tarde.** Acá se escribió que el
  *"posponía SIEMPRE"* sobrevivía porque `intento_antes_de_escalar` vive en RAM
  (`_sesiones`, D4) y que *"un cliente que escribe una vez al día vuelve a recibir
  posposición cada vez"*. **Eso estaba mal planteado**, y se midió leyendo el código:
  `_sesiones` **no se vacía entre turnos** —sobrevive mientras el proceso viva y la
  conversación esté abierta (`api.py:1326`)— y solo se pierde por dos caminos:

  1. **Reinicio del motor.** Concede **un** intento extra y nada más: al turno siguiente la
     bandera vuelve a estar puesta. Es lo que el propio código declara como costo aceptable,
     y lo es.
  2. **Cierre por inactividad** (`api.py:1318`, `_sesiones.pop`). Ahí la conversación
     siguiente es **otra**, y que tenga su propia vuelta es la conducta correcta —la misma
     frontera que rige el anti-rebote y la identidad: *se continúa una conversación, no se
     recuerda a una persona para siempre*.

  Se evaluó **persistirlo** en la columna `datos_sesion` —el JSONB que ya existe para
  `areas_visitadas`, sin migración— y **se decidió NO hacerlo**, con el argumento medido:
  el comentario del código justifica la RAM por *"una lectura extra a la base en cada
  turno"*, y esa premisa es falsa (la lectura ya ocurre: `estado_de_conversacion_abierta`
  se llama igual y ya trae `datos_sesion`). Pero el beneficio que quedaba también es chico
  —quitar un mensaje extra ocasional tras un deploy— y el cambio pedía volver la hidratación
  sensible al tipo, porque hoy hace `list(valor)` sobre todo lo que persiste. **No se toca
  algo del camino del turno por un beneficio de ese tamaño.**

  Lo que sí queda anotado, porque no lo cubre ninguna de las dos guardas: una conversación
  con **un solo mensaje del cliente** que se cierra por inactividad no entra a la banda
  —`mensajes_cliente >= 2` la excluye— y su posposición no se hereda. Es angosto y
  probablemente correcto (un mensaje, el cliente no volvió, no hay nada que escalar), pero
  está dicho en vez de supuesto.
- Lo que B sí cambia **en código**: el gating del agendamiento automático (`api.py`, tras
  el evaluador) y la centralización de la decisión. Lo que cambia **por guía**: la nota,
  que pasa de pedirle algo imposible a pedirle lo único que puede. Por PRD §7.4 —*el
  prompt es guía, el código es la garantía*— la parte de B que cierra limbo es el gating;
  la nota es una mejora medida en n=5 sintéticos (3 de 5 derivaron), no una garantía.

### Tres hallazgos altos, los tres corregidos en la rama

**1 · La prueba de B no veía el enganche: cinco mutaciones de `api.py` la dejaban en
verde.** El auditor copió el árbol y mutó una cosa por vez; `prueba_6` afirmaba sobre el
*texto del fuente*, así que sobrevivió a las cinco —incluida `ya_intento=False`, que
pospone en cada turno y **no escala nunca**, el limbo original pero peor—.

Corregido volviendo el bloque **invocable**: `api._aplicar_posposicion(config, rol_cfg,
estado, *, forzado, motivo) -> bool`, con la decisión todavía entera en
`forzado.por_que_posponer`. `prueba_7` corre el mecanismo real **dos veces sobre el mismo
estado** y afirma que la segunda escala. Medido con el mismo método del auditor:

```
ROJO (la caza)   <- M1 ya_intento=False (pospone en CADA turno, no escala nunca)
ROJO (la caza)   <- M2 no se marca el intento (posposicion infinita)
ROJO (la caza)   <- M3 nunca se pospone
ROJO (la caza)   <- M5 la nota se descarta
ROJO (la caza)   <- M4 se pasa el primer rol del dict en vez de rol_cfg
```

Las cinco, donde antes eran cinco verdes. M4 se caza con una afirmación sobre el texto, y
está escrito en la prueba que lo es: que el sitio de llamada pase el rol **del turno** no
se puede medir sin conducir `_atender_turno` entero contra base.

**2 · La banda exceptuaba del cierre lo que no mostraba.** Con `sin_gestion_horas = 72` y
`limites.horas_inactividad_cierra = 24`, desde la hora 24 la fila deja de cerrarse y la
banda no la muestra hasta la 72: **48 horas invisibles**, 29 días con el máximo del
formulario. Medido por el auditor contra `dexter_local`: **25 de 25** filas exceptuadas y
sin banda con 72. Es el estado que el comentario del propio barrido dice querer evitar.

Corregido en `_mutar_ajustes_bandeja`: con el barrido habilitado, un umbral **mayor** que
`horas_inactividad_cierra` se rechaza con un mensaje que dice por qué. Con el barrido
apagado no hay ventana y el umbral es libre —la validación acota lo que hace daño, no lo
que se le parece—. El invariante quedó escrito en el contrato (§4.10).

**3 · La protección fallaba ABIERTA en el proceso que borra.** El reloj lee con
`fuente.cargar`, que cae al YAML de la imagen cuando la base no contesta; el YAML **no
declara `sin_gestion_horas`**, así que `operativo.py` calculaba `entrada = None`, la
excepción desaparecía y el barrido cerraba con `sin_respuesta_cliente` —que afirma que el
cliente no volvió— justo las filas que la banda protege. **No es teórico:** el YAML
semilla trae `habilitado: true`, `rollout_cutoff` y `24` horas, y el propio log del
fallback apareció en la corrida de §14 (`motivo=tenant_no_esta_en_la_base`).

Corregido donde estaba la causa: `TenantConfig._origen` marca de dónde salió la config
(`base` | `yaml`), `fuente.cargar` lo sella al degradar, y el barrido **exceptúa igual**
cuando no puede confirmar que la banda esté apagada. Dejar una conversación abierta es
reversible y se ve en la Bandeja; cerrarla afirmando algo del cliente, no.

### Dos silencios más del arquitecto, corregidos

- **Un umbral sin `rol_de_entrada` se guardaba y no hacía nada.** El campo es opcional en
  el esquema y la banda falla cerrado sin él: el formulario aceptaba el número, lo
  persistía, y la banda no existía. Rapilink lo declara; **lo pagaba el segundo ISP**, que
  es el razonamiento que §3.3 prohíbe repetir. Ahora se rechaza.
- **Y la otra puerta del mismo silencio, que el arquitecto no vio:**
  `guardar_rol_de_entrada(tenant, None)` permite **vaciarlo a propósito**. Encender la
  banda bien y vaciar el rol después la apagaba *y devolvía al barrido* las conversaciones
  protegidas. Ahora ese vaciado se rechaza mientras el umbral esté puesto, con el orden
  correcto en el mensaje.
- **El cuarto parámetro de `guardar_ajustes_bandeja` perdió su default.** Su `None`
  significa *borrar*: un llamador con la firma vieja apagaba la banda y reactivaba el
  cierre sin decir nada. Ahora es un `TypeError` al importar, y la prueba lo afirma como
  efecto llamando con tres argumentos.

Todo esto se afirma en `tests/test_editor_config.py::prueba_banda_sin_gestion` (13
afirmaciones, sobre los mutadores puros, sin base) y en
`tests/test_cierre_inactivas_ia.py` (config degradada exceptúa; config de la base con la
banda apagada no).

### Lo que las dos lentes buscaron y no encontró ninguna

El motor sigue genérico (`test_nucleo_sin_tenants`, 93 archivos); `rol_de_entrada` sale de
la config y no de un nombre de rol; la banda **no duplica** ningún mecanismo —se
descartaron cinco candidatas con su motivo: T19 `REVISAR_EVALUACION`, `sla_toma_minutos`,
`SIN_ASIGNAR`, el propio barrido y el reconciliador—; `sin_gestion_horas` está modelado de
punta a punta y ausente del YAML (la base manda, §3.2); vacío = apagar es coherente en las
cuatro capas; el número 3 compartido no rompe nada (ningún `banda === 3` en el frontend);
**0 apariciones nuevas** de `PRIVATE_ASISTENTE_TENANT` (D5); la SQL nueva no tiene el
`IndeterminateDatatype` de psycopg 3 (corrida en las cuatro combinaciones); y la regla 3b
del contrato coincide condición por condición con el código.

### Segunda pasada: auditoría del delta `4f1ea12..b3ce928`, 26/09/2026

El arreglo de los tres agujeros era código nuevo que nadie había auditado —~340 líneas,
una de ellas una extracción dentro de `_atender_turno`—, así que se auditó el delta solo.
Encontró **tres altos, y dos golpean justo lo que el commit anterior decía cerrar.**

**D1 · `cli/cargar_config.py` apagaba la banda en silencio.** `sin_gestion_horas` no estaba
en `SECCIONES_EDITABLES`, la lista que el cargador mira antes de sobrescribir la base con
el archivo. El YAML no declara el campo, así que el comando que §8 manda correr **después
de cada pull que toque el YAML** dejaba el umbral en `None`: banda apagada y las
conversaciones protegidas devueltas al barrido. La puerta más rutinaria de todas, y la
misma forma de fallar que la parrilla de canales. Corregido agregándolo a la lista, con la
afirmación que el repo ya usa para `guias_tv`.

**D2 · La regla del umbral valía por una sola puerta.** La validación cruzada vivía solo en
el editor; `cli/cargar_config.py` valida contra `TenantConfig` y nada más, así que el par
72/24 **entraba por el YAML** y la ventana invisible volvía. El auditor citó el criterio
del propio repo —*"la validación la hace el esquema, así vale por cualquier puerta"*— y en
eso tiene razón, pero **no en el remedio**: un validador cruzado puede volver **incargable
una config ya guardada**, y §8 dice qué pasa entonces (`fuente.cargar` cae al YAML de la
imagen). Sería cambiar una ventana de 48 horas por un motor sirviendo config que nadie
puede editar: un fail-open peor. Resuelto por el otro lado, con
`TenantConfig.sin_gestion_horas_efectivas()`: el umbral **efectivo** nunca es más tarde que
el cierre por inactividad, entre por donde entre el número, y ninguna config puede dejar de
cargar. El editor sigue rechazando el par para que la persona reciba el mensaje.

**D3 · La guarda del barrido no alcanzaba, y el caso peligroso no emitía señal.** La
primera versión exceptuaba el rol de entrada; si la semilla **no declara `rol_de_entrada`**
—y la de alta del segundo ISP no lo va a declarar, porque se fija desde la interfaz— no
había rol que exceptuar y el barrido cerraba igual. Peor: `resumen["config_degradada"]`
estaba dentro de `if degradada and entrada`, así que **en el caso peligroso no avisaba
nada**. Corregido con la decisión más simple y más fuerte: con la config degradada **no se
cierra nada**, y el resumen dice por qué. Un trabajo que borra no corre sobre una
configuración que nadie puede editar.

**Y tres del mismo tipo, cerradas:** el marcado del origen pasó al único lugar que lee el
YAML (`cargar_config`), así que vale por los doce usos de `cli/` y no solo por el camino
del reloj; el endpoint `/configuracion/bandeja` **exige la clave** `sin_gestion_horas`
aunque venga en `null` (JSON no tiene firma que lo obligue, y "ausente" no puede significar
"apagá la guarda"); y el tipo del cliente JS dejó de marcarla opcional.

**Las cinco mutaciones que el auditor mostró sobreviviendo, ahora mueren:**

```
ROJO (la caza)   <- N1 cargar_config deja de marcar el origen          [test_editor_config]
ROJO (la caza)   <- N5 el default del marcador pasa a 'yaml'           [test_editor_config]
ROJO (la caza)   <- N4 el barrido deja de mirar el origen              [test_cierre_inactivas_ia]
ROJO (la caza)   <- M7 forzado=False en el sitio de llamada            [test_escalada_del_rol_de_entrada]
ROJO (la caza)   <- A2b el umbral efectivo deja de acotarse            [test_editor_config]
```

M7 era el peor de los cinco: `forzado=False` en la llamada posterga una escalada **forzada
por una herramienta** —el incidente del 18/08/2026 que el comentario de `api.py` dice
evitar— y ninguna de las nueve pruebas que conducen el turno lo veía.

**Lo que el auditor verificó y salió limpio:** la extracción es semánticamente idéntica
(comparada línea por línea contra `4f1ea12`; `posponer` vale `False` sin excepción al
llegar al bloque, y `razon`/`nota` no se usan en las 630 líneas siguientes); el
`PrivateAttr` sobrevive a `model_copy`, `deepcopy` y `pickle`, no aparece en `model_dump`
—así que `extra="forbid"` no se rompe en el ida y vuelta del editor— y la caché de
`_config_de` no lo pierde; ningún camino real pone `"yaml"` sobre algo salido de la base;
las validaciones del editor resistieron seis mutaciones propias; el PUT devuelve 400 y no
500; y `prueba_6` sigue sirviendo después de la extracción, porque es la que caza pasarle
una copia del estado.

**Casos dorados, con su varianza medida.** `--humo` sobre la rama: **9/10 (90%, el mínimo
exigido)**; el único rojo es `BOTTLECRM_API_TOKEN`, que el contenedor local no expone. Una
corrida anterior dio 7/10 y **la causa era el entorno, no el código**: faltaba exportar
`WISPHUB_API_KEY`. Y el control sobre `4f1ea12` —el árbol *previo* al delta, mismo
entorno— dio **8/10**, fallando un caso que en la rama pasa. O sea que el set varía ±1 caso
entre corridas, tal como el propio comando avisa (pide ≥50 casos para ser criterio de
aceptación). No hay regresión atribuible al delta.

| # | Deuda que suma esta pasada | Por qué se deja |
|---|---|---|
| L9 | `sla_toma_minutos` y `umbral_rx_dbm` siguen expuestos a que `cli/cargar_config.py` los pise sin avisar: no están en `SECCIONES_EDITABLES` | Es previo y cuesta un veredicto en pantalla, no un cierre de conversación. Agregarlos hace frenar la carga a más tenants y merece su propia decisión |
| L10 | `resumen["config_degradada"]` no tiene consumidor: llega al log del reloj y al JSON del endpoint, y ninguna pantalla ni alerta lo lee | La banda de alertas del reloj es trabajo aparte; sin eso, agregar un consumidor a medias es peor |
| L11 | El camino degradado alcanzable es `tenant_no_esta_en_la_base` (base arriba, fila ausente), que es **persistente**: ahí el barrido no cierra nunca hasta que alguien lo vea | Es la dirección segura, y el aviso de `fuente.cargar` ya dice *"eso hay que verlo"*. Lo que falta es que alguien lo vea: ver L10 |
| L12 | `cargar_config` marcando `"yaml"` cambia el comportamiento de cualquier `cli/` que cargue del archivo y corra el barrido: ahora no cerraría | Correcto por diseño (un archivo no es la fuente de verdad), pero no lo medí en los doce usos de `cli/`: el único que barre es el reloj, y ese usa `fuente.cargar` |

### Tercera pasada: auditoría del delta `b3ce928..8659479`, 26/09/2026

Con una **regla de parada declarada antes de correrla**, porque si no la cadena no termina:
se audita de nuevo cuando el arreglo **agrega mecanismo** (caminos nuevos con modos de falla
nuevos), no cuando solo **acota** algo que ya existía. Ese delta agregaba tres mecanismos
—el umbral efectivo, el corte temprano del barrido y el 400 del endpoint—, así que
correspondía. Encontró **un alto y dos medios**, todos sobre lo agregado.

**T1 · La línea que arreglaba el agujero no tenía guarda, y su propio `hasattr` restituía la
conducta vieja en silencio.** Mutar `/conversaciones` para leer `sin_gestion_horas` crudo —un
renglón, con pinta de simplificación— devolvía la ventana de 48 horas **con toda la batería
en verde**: ninguna de las cuatro pruebas que pegan a ese endpoint declaraba el umbral, así
que la banda no existía en ninguna. Y el `else` del `hasattr` era, línea por línea, la
conducta previa al acotado.

Corregido en los dos frentes: el `hasattr` fuera (un renombre del método ahora es
`AttributeError`, no un silencio), y **la guarda vive donde el repo prueba ese borde de
verdad** — §14 de `tests/test_relevo_transiciones_base.py`, contra PostgreSQL real, con el
par 72/24 puesto y una fila en limbo de 30 horas. Cuatro afirmaciones nuevas, incluida la que
distingue acotar de *encender siempre* (con el barrido apagado vale el 72 pedido). Se intentó
primero en `test_cola_bandeja` —sin base, que sería mejor— y **no se puede**: importar `api`
exige credenciales y con variables ficticias el proceso se cuelga intentando conectar. Eso
está dicho en el comentario de la prueba, porque explica por qué la guarda no está donde
alguien la buscaría.

**T2 · El 400 del endpoint vigilaba una puerta por la que nadie entra.** El comentario
nombraba su amenaza —*"un formulario nuevo que reutilice este endpoint con dos campos"*— y ese
formulario **no llega al 400**: llega al helper de JavaScript, que convertía la ausencia en
`null`, o sea en "apagá la banda". Y había una prueba mía bendiciendo exactamente eso
(*"y si el llamador ni la manda, también viaja como null"*). La garantía estaba en el borde
equivocado, y la ficha afirmaba que el sistema lo cubría: cierto del endpoint, falso del
sistema. Corregido: el helper **revienta** si la clave falta, sin llegar a la red, y la prueba
ahora afirma eso y que no se hizo ningún PUT. Las otras cinco llamadas de esa suite pasan el
trío completo.

**T3 · El formulario mostraba 72 y la banda actuaba a las 24, sin ninguna señal.** Silencio
nuevo, introducido por el acotado: inevitable es que el efectivo difiera del guardado;
evitable es que la pantalla no lo diga. Corregido: `GET` y `PUT` de `/configuracion/bandeja`
devuelven **los dos** umbrales, y el formulario muestra un aviso cuando difieren, con qué
guardar para que lo que se ve sea lo que pasa. El campo sigue mostrando el guardado, para que
apretar Guardar no cambie nada sin pedirlo.

**Y la anotación que mentía:** `_aplicar_posposicion` declaraba `motivo: str` y recibe `None`
desde el 26/09 (`evaluacion.get("motivo")`). Corregida a `str | None`.

**Lo que el auditor verificó y salió limpio** (lo cito porque es lo que sostiene el acotado):
`sin_gestion_horas_efectivas()` no puede devolver 0 ni apagar la banda —los dos campos son
`ge=1` y el `min` de dos enteros ≥1 es ≥1—; y el acotado **no abre ninguna ventana en el otro
sentido**, ni con los dos relojes distintos que usan banda y barrido: el del barrido es
`max(creado_en)` sobre todos los mensajes y el de la banda excluye las notas, así que el
tiempo que ve la banda es siempre ≥ el que ve el barrido, y la banda muestra igual o antes de
que la fila deje de ser cerrable. También midió que el corte temprano del barrido no deja
mintiendo a ningún lector (las claves que no llena tienen dos lectores, los dos tolerantes) y
cerró L12 por medición: **ningún `cli/` corre el barrido**, así que marcar `"yaml"` en el
lector de archivos no cambia la conducta de ninguno.

| # | Deuda que suma esta pasada | Por qué se deja |
|---|---|---|
| L13 | **`habilitado: true` no es "el barrido corre":** falta `rollout_cutoff`. Con ese par el barrido no cierra ni exceptúa —no hay ventana— y sin embargo el acotado adelanta la banda, y el editor rechaza un 72 legítimo citando un cierre que no ocurre | Solo entra editando el YAML a mano (`cierre_inactivas_ia` no está en `SECCIONES_EDITABLES`) y la semilla de ejemplo lo trae apagado, así que el segundo ISP arranca seguro. Sumar `rollout_cutoff` a las dos condiciones es correcto y no urgente |
| L14 | **La igualdad de `TenantConfig` cambió:** pydantic v2 compara los atributos privados, así que la misma config leída del archivo y de la base ya no son `==`. **Medido: ningún lugar del repo compara instancias** —`diferencias_config.py` y `cargar_config.py` comparan volcados, y el marcador no viaja en el volcado— así que es latente, no activo | Neutralizarlo exige pisar `__eq__` del modelo central de configuración, que es superficie nueva en el archivo más delicado. El escenario queda escrito: el día que alguien escriba `config_repo == config_base` va a recibir "distintas" para siempre |
| L15 | La afirmación de `forzado=forzado` en el sitio de llamada es **sobre el texto del fuente**, y está declarado en la prueba. Sobrevive a cualquier mutación que sombree `forzado` antes, en el turno | Medirlo exige conducir `_atender_turno` entero contra base, que es el trabajo que T1 hizo para el otro parámetro; se puede repetir para este cuando haga falta |

### Checklist de salida (`guardia-de-release`), 26/09/2026 — el paso 7 del flujo

No es una cuarta auditoría: no mira código nuevo, mira la rama **como entregable**. Semáforo
**verde con tres avisos de despliegue**. Lo que midió y hay que conservar:

- **El merge es fast-forward.** `merge-base` = tip de origin, 12 commits en una dirección y
  **0 en la contraria**: la base no derivó. Los 12 con `+` en `git cherry` (comparación por
  contenido, no por hash — la regla del 24/09). Solape de archivos con
  `integrar-centro-mando`: **cero**, medido.
- **Cero migraciones, cero variables de entorno nuevas, cero cambios en el catálogo de
  herramientas** (`git diff -- tenants/ nucleo/herramientas/` = 0 líneas). `migrar_asistente.py`
  no aplica a este merge.
- **La puerta de `cargar_config.py` funciona, y se midió ejecutándola:** con el umbral
  guardado en la base y el YAML sin declararlo, el comando **se niega** nombrando el campo
  (`SystemExit`). Con la banda apagada no avisa nada, que es lo correcto. Consecuencia
  operativa que hay que respetar: **una vez encendido el umbral, `cargar_config.py --forzar`
  sobre ese tenant deja de ser rutina** — borrarlo no apaga una banda en pantalla, devuelve
  las conversaciones al barrido, que las cierra afirmando que el cliente no volvió.
- **`diferencias_config.py` lo va a reportar como `[i] solo la base lo tiene`**, que es la
  dirección normal y no hace fallar el comando. La que rompe —*el repo lo declara y la base
  no*— es imposible para este campo, porque el YAML no lo declara a propósito.
- **Qué hay que reiniciar y qué queda inerte:** el motor web (la banda), el reloj (la
  excepción del barrido) y el frontend (sin él la fila llega en la respuesta y **no aparece
  en ninguna pestaña**). Con `RELOJ_HABILITADO=0` la mitad del barrido queda inerte y no
  importa: si no corre, no hay nada que exceptuar. Y hay una **tercera puerta** que no pasa
  por ese interruptor: `POST /mantenimiento/cerrar-inactivas-ia`, que corre en el proceso web
  — ahí la excepción sí aplica.

**Tres riesgos de despliegue, y qué se hizo con cada uno:**

1. **Los contadores de la cabecera van a bajar de golpe** el minuto del deploy, y no es la
   banda: es el arreglo de L7 (la cabecera contaba sobre todas las conversaciones mientras la
   lista se filtraba por canal), con 294 corridas de laboratorio viviendo en producción. Es la
   corrección de una incoherencia real, pero **si nadie lo avisa se lee como "desaparecieron
   conversaciones"**. Queda dicho acá y en la entrega.
2. **Ventana motor↔frontend**, que era riesgo introducido por esta rama: el motor nuevo exigía
   la clave `sin_gestion_horas` y el formulario viejo no la manda, así que en esa ventana no
   se podía guardar **ninguno** de los tres ajustes. **Corregido** (`1b95550`): el 400 entra
   solo cuando hay un umbral guardado, o sea cuando "ausente" significaría apagar la guarda.
   Sin banda encendida no hay nada que perder y la omisión se acepta.
3. **L5, el rollback:** con el umbral guardado, volver el motor a una imagen anterior
   **rechaza la config entera** y el tenant deja de atender — medido cargando el schema previo
   con la clave puesta (`extra_forbidden`). Escrito en **`DESPLIEGUE.md` §7**, que es donde se
   busca, con las dos reglas de orden: encender después de desplegar, y apagar antes de
   revertir.

**Dos correcciones al informe del guardia**, para que el registro quede fiel:

- **vitest no está pendiente:** el guardia no pudo correrlo (este worktree no tiene
  `node_modules`), pero **yo lo corrí dos veces en contenedor limpio: 345/345** en las
  superficies tocadas, la última con el `throw` nuevo del helper y su prueba reescrita.
- **Alcance de `290eaab`:** ese commit trae 6 archivos de `SPEC/` que no son de B ni de C
  —entre ellos la ficha de otro objetivo, `contexto-por-capacidad-del-turno.md`, que está
  **propuesto y sin implementar**—. Son solo documentación, no existen en ninguna rama remota
  y no generan conflicto, pero es el gesto que §7 prohíbe. **Que nadie lea esa ficha como
  trabajo cerrado**; se deja porque partir el commit obligaría a rehacer el cherry-pick y
  revalidar con base.

**El hueco que queda, nombrado:** la corrida completa de los 56 casos dorados. La tabla de §6
la exige porque B cambió el texto que se le inyecta al modelo, y `--humo` son 10 casos con una
varianza medida de ±1 — o sea que **el humo no puede distinguir una regresión chica**. Es el
único paso del flujo §11.2 que el diff exige y no corrió. Los otros tres —`verificador-de-api`,
`auditor-de-frontera`, `revisor-de-pii`— quedaron descartados con su motivo medido: cero
cambios en el catálogo o en llamadas externas; cero apariciones de `frontera`, `critica(`,
`idempot`, `interruptor` o `irreversible` en el diff del núcleo, y los dos cambios que tocan
el camino de una acción con efecto **acotan** (el agendamiento se dispara menos, el barrido
cierra menos); y ninguna lista blanca ni campo de texto libre tocado, con
`test_registro_sin_pii` en verde.

### Los casos dorados completos, 26/09/2026 — corridos, y lo que resultó no medir

Decisión del usuario: correr el set completo antes del merge, porque `--humo` son 10 casos con
varianza de ±1 y no puede distinguir una regresión chica. Se corrió, y el resultado tiene dos
partes: un número, y un hallazgo sobre el instrumento que vale más que el número.

**Registro de la corrida.** Commit `f519af4`; set **88 casos**, no 56 (el dato de "56" que
circulaba en los resúmenes estaba viejo); config desde el YAML (no `--base`: eso exige
credenciales de producción); base `dexter_local`; credenciales presentes `DEEPSEEK_API_KEY` y
`WISPHUB_API_KEY`, **ausentes `SMARTOLT_API_KEY` y `BOTTLECRM_API_TOKEN`**, y **el RAG no
funciona en este entorno** (`recuperacion/embeddings.py:57`, `RuntimeError` en cada caso). El
informe JSON quedó fuera de git a propósito: sus trazas llevan respuestas crudas de la API de
WispHub, y §5 dice que eso no se persiste.

**El número, con su control.** No se puede leer solo:

| | Rama `f519af4` | Control `f90d3ec` (lo desplegado) |
|---|---|---|
| Casos OK | **70/88 (80%)** | **69/88 (78%)** |
| Fallan en las dos puntas | 16 | 16 |
| Fallan solo en esa punta | 2 | 3 |

Las dos corridas son en el **mismo entorno roto**, que es lo que las vuelve comparables. La
rama queda **un caso mejor** que lo desplegado, y los divergentes van en direcciones
opuestas (2 contra 3, casos distintos): eso es varianza del modelo, no regresión. De los 18
fallos de la rama, **4 son credenciales ausentes** (`SMARTOLT_API_KEY` ×3,
`BOTTLECRM_API_TOKEN` ×1) y buena parte del resto son cadenas que se rompen aguas arriba de
eso o piden el RAG que acá no responde. **El 80% no es el número del sistema sano**, y no se
puede usar como tal: es el número de este entorno, útil solo contra su propio control.

**El hallazgo que importa: los casos dorados no pueden ver a B.** Verificado en el código, no
inferido — `cli/evaluar.py` llama `motor.responder()` y *replica parte* de `atender_turno`
(lo dice su propio comentario), invoca `escalamiento.evaluar()` solo cuando el caso declara
una clave de escalada, y tiene **cero** apariciones de `por_que_posponer`,
`_aplicar_posposicion`, `intento_antes_de_escalar` y `nota_pendiente`:

```
$ grep -cE "por_que_posponer|_aplicar_posposicion|intento_antes_de_escalar|nota_pendiente" cli/evaluar.py
0
```

O sea que **la nota de B nunca llega al modelo por este camino**, y tampoco nada de C (banda,
proyección, editor, endpoint). La tabla de §6 manda correr `cli/evaluar.py` cuando cambia el
texto que se le inyecta al modelo, y para *este* cambio ese disparador apunta a un instrumento
estructuralmente ciego. Corresponde decirlo así y no fabricar una conclusión: **la corrida no
confirma ni desmiente la conducta de B; lo único que demuestra es que la rama no empeora lo
que el set sí mide.** El instrumento que sí alcanza este camino es `cli/bateria_flujos.py`
—que pasa por `atender_turno`— y su medición está más arriba en esta ficha: baseline 37/38 →
B 40/41, con la nota llevando a derivar en 3 de 5.

Es el mismo hueco de cobertura que esta ficha ya había anotado el 25/09 al abrir B1, ahora
medido de punta a punta y con su consecuencia práctica: **para un cambio en el camino del
turno, "corré los casos dorados" no es la verificación correcta.** Queda para el bloque de
métricas / cobertura, no para esta rama.

### Deuda declarada, con su motivo — no se arregla en esta rama

| # | Qué | Por qué se deja |
|---|---|---|
| L1 | `forzado.py` dice en su cabecera *"sin dependencias a propósito"* y después importa `escalamiento` en perezoso por un ciclo. **Un comentario que miente es peor que la deuda que oculta.** El arreglo existe y es chico: `merece_un_intento` es pura y se puede mover | Mover toca `escalamiento.py` y `test_escalamiento_paciente.py`, dos archivos fuera de este diff, por un beneficio que hoy nadie consume |
| L2 | La regla vive dos veces —Python en `proyeccion.py`, SQL en `db.py`— y **ninguna prueba afirma que coincidan**. La divergencia dañina (el umbral) quedó cerrada por validación; la estructural queda | Una prueba de equivalencia exige base y una matriz de filas; es el trabajo siguiente de esta guarda |
| L3 | `devolver_a_ia` **no limpia `tomada_por`** (`soltar` sí limpia los dos). Una devuelta a la IA con banda cae en «En atención», donde nadie la atiende, y el barrido tampoco la cierra: **permanente** | Cambiar la semántica de una transición del relevo dentro de la rama de integración es justo lo que §7 dice no hacer. Es defecto previo de `transiciones.py`, no de C |
| L4 | Un último mensaje de rol `'humano'` (legado) queda **protegida y sin banda**: `ultima_actividad` lo reporta como `ultimo_rol='humano'` y el barrido lo ve como `assistant` | Caso estrecho (rol de legado) y el arreglo correcto es unificar qué cuenta como "último visible", que toca las dos consultas |
| L5 | `TenantConfig` hereda `extra="forbid"`: una vez que el formulario escribe `sin_gestion_horas`, **volver el motor a una imagen anterior rechaza la config entera** y el asistente deja de atender | No es código: es una nota de despliegue. Vale para cualquier campo nuevo de config y hay que decirla al encender la banda |
| L6 | `estado.js` reconoce la banda por **literal** (`banda_nombre === 'sin_gestion'`) en una pantalla cuyo docstring dice que *"no clasifica nada"*. La próxima banda que el motor agregue será invisible hasta que alguien edite ese archivo | Usar `necesita_accion_de === 'humano'` es más limpio pero mueve los conteos de las bandas 1, 2 y 5, y esa medición no está en esta rama |
| L7 | `34412ac` incluye un arreglo que **no es de C**: el refactor `base` de `+layout.svelte`, que corrige que la cabecera contara sobre todas las conversaciones mientras la lista se filtraba por canal (el defecto del 07/09, repetido por canal) | Partir el commit exige rehacer el cherry-pick y revalidar con base. Queda anotado para la sesión de métricas, que es la que va a mirar ese lado |
| L8 | Los indicadores de consola (`criticas`, `esperaMaxima`, `Total`) ahora dependen de la vista: con la vista en «simulado» se lee *"Ninguna esperando"* habiendo clientes reales esperando | `vista` no persiste entre recargas, así que el riesgo muere con la pestaña, y el cambio corrige una incoherencia mayor |

## Siguiente bloque, decidido el 26/09/2026: métricas — no arrancado a propósito

> *"Normalizar métricas operativas usando `canales.REALES` como única
> definición de cliente real. Auditar los ocho puntos de conteo antes de
> modificar. No mezclar con la integración B/C."*

Se dejó para la próxima sesión con el estado en un punto de cierre limpio, y
porque ese bloque toca otra capa —`db.py` → conteos → reportes → decisiones
futuras— y hoy se midió cuánto pesa una métrica mal acotada. Merece el mismo
rigor que D4, en este orden y sin saltear ninguno:

1. mapa de los ocho lugares (ya hecho: `panorama_centro_mando` ×4,
   `tasa_escalamiento`, `/consumo`, `analista.detectar`, `medir_turnos`,
   `revision_g8`, más la cabecera de la bandeja);
2. qué cuenta hoy cada uno;
3. qué universo debería contar;
4. prueba de que los simulados no contaminan — afirmar el efecto, no la
   presencia del filtro;
5. commit.

Decisiones ya tomadas que no se reabren: **no** una lista de "canales de
laboratorio" en `tenant_config` (sería una lista de exclusión que se queda
corta con cada canal nuevo de prueba, y un campo nuevo no es editable hasta que
el editor lo conoce); la definición es de inclusión y vive en el motor:
`nucleo/canales/canal.REALES`. `cli/revision_g8.py` tiene una segunda lista
divergente que hay que unificar.

## Bitácora

| Fecha | Qué avanzó | Qué falta |
|---|---|---|
| 25/09/2026 | Mapeado el precedente y sus tres condiciones, el hueco de cobertura de los casos dorados, y que la config del router no menciona bajas en ninguna parte. Tres propuestas diseñadas | D1, D2, D3 |
| 25/09/2026 | **Retractada la medición del mismo día.** El "9 de 14 en limbo" eran corridas del propio laboratorio: la base local es 100% sintética y 1105 de sus 1139 conversaciones se crearon ese día. El instrumento se estaba contando a sí mismo | **D4**: dimensionar el limbo con datos reales, que exige permiso para consultar producción |
| 25/09/2026 | **Causa estructural hallada y corregida en dos formas.** `con_las_manos_vacias` posponía siempre la escalada del rol de entrada, que no tiene con qué intentar nada. A (`c63a019`, `fde6959`): no posponer. Auditoría de tres lentes: A anulaba `intentar_resolver_antes` y la prueba no veía el enganche (probado). B (`6c911fa`): posponer una vez con la nota que ese rol puede cumplir, decisión entera en `forzado.por_que_posponer`, prueba que importa la misma función y afirma que `_atender_turno` no la recompone. Batería: baseline 37/38 → A 39/41 → **B 40/41**, sin regresión; la nota llevó a derivar en 3 de 5 | D1 (el router que ni deriva ni pide escalar), D2 (ambigüedad de *cancelar*), D4, y **C**: el caso *lista de morosos* mostró en vivo la escalada pospuesta a la que nadie vuelve |
| 26/09/2026 | **C liviano implementado** (`8baefcf`): banda `sin_gestion` sin migración ni cierre automático, umbral por tenant de punta a punta, barrido exceptuando solo con la banda encendida, frontend y contrato. Verificado sin base, con base real (relevo §14 en verde por primera vez en la rama) y vitest (345/345 en las superficies tocadas; 63 fallos previos idénticos en HEAD). Correr la prueba con base destapó cinco dobles obsoletos —dos de B, tres previos— corregidos acá, y dos fallos previos (§11-12, guarda D25) que quedan anotados | Rapilink enciende `sin_gestion_horas` desde `/settings/bandeja`; métricas que cuentan simulados (`canal.REALES`); D5 `sin_respuesta`; baseline de escalación; las 294 filas simuladas de producción; que "saltado" no se vea igual que "pasó" en `cli/correr_pruebas.py` |
| 25/09/2026 | **D4 medido en producción, autorizado, solo lectura.** Clientes reales (`canal = 'whatsapp'`, ≥2 mensajes, seis semanas): **5 en limbo de 39 (13%)**, tres todavía abiertas sin dueño, dos de 12 y 20 mensajes. Causa estructural confirmada en la config desplegada. Segunda lección de canal: producción tiene siete canales y **294 corridas de laboratorio viven ahí**; solo `whatsapp` son clientes | Decidir la forma de **C** (por corrección, no por urgencia); D1; D2; regenerar baseline de escalación; limpiar o etiquetar las 294 filas simuladas de producción |
| 26/09/2026 | **Integrados B y C sobre `origin/fix` (`f90d3ec`)** en la rama `integracion/b-c-limbo`, ocho commits por cherry-pick, sin push. Dos conflictos reales en C (`+page.server.js`, `bandeja-config.test.js`) contra el refactor `35a6723` de `guardarAjustesBandeja(locals, fetch, valores)`, resueltos con la firma nueva. `test_registro_sin_pii` cazó una regresión de B que ninguna prueba propia veía: el evento del log de la posposición dejaba de ser texto fijo; corregido en `1642935` (evento fijo, la razón como campo). Verificado en la rama: las nueve pruebas rápidas de B y C en verde; relevo contra PostgreSQL con §14 en verde y solo §11-12 en rojo, **y esos dos fallan igual sobre `f90d3ec` puro** —medido con la prueba corregida encima, porque origin con su propia prueba ni llega: se cae en §5 por los tres dobles previos sin `origen`—; vitest con 63 rojos en las dos puntas (1049/1112 en origin puro, 1051/1114 en la rama), ninguno de la bandeja; `test_reloj` falla igual en origin puro (`fijar_nombre_cliente_externo` fuera de `importacion_io.HERRAMIENTAS`). Fuera de la rama a propósito: el laboratorio, `test_contexto_del_router.py` y los 18 commits de validación | Push y la línea en `DEXTER_ESTADO_ACTUAL.md`: sesión dueña. Después: métricas con `canales.REALES`, D5 `sin_respuesta` |
| 26/09/2026 | **Auditada antes de integrar, y corregida.** Dos lentes de solo lectura sobre `4f1ea12`: el `auditor-independiente` mato cinco mutaciones de `api.py` que dejaban la prueba de B en verde --una de ellas posposicion infinita-- y midio dos agujeros de C (48 h exceptuadas y sin banda con 72/24, 25 de 25 filas; la proteccion cayendose cuando el reloj lee el YAML); el `arquitecto-dexter` hallo que un umbral sin `rol_de_entrada` se guardaba sin efecto. **Los tres altos corregidos en la rama**: bloque extraido a `api._aplicar_posposicion` con prueba de dos vueltas que caza las cinco mutaciones, validacion cruzada del umbral contra `horas_inactividad_cierra`, `TenantConfig._origen` para que el barrido exceptue cuando no puede confirmar, y las dos puertas del vaciado silencioso cerradas. Corregido tambien lo que **B realmente hace**: el codigo previo ya escalaba en el turno 2 con la sesion viva, asi que el subject de `b920c25` afirma de mas. Verificado: nueve guardas en verde, relevo con base solo los dos rojos previos y §14 en verde, y casos dorados `--humo` 9/10 (90%, el minimo), con el unico rojo por una credencial local de BottleCRM | Ocho deudas declaradas con su motivo (L1..L8). Push y `DEXTER_ESTADO_ACTUAL.md`: sesion dueña |
| 26/09/2026 | **Segunda auditoria, sobre el delta del arreglo.** Los ~340 renglones que corrigieron los tres altos eran codigo sin auditar, y la pasada encontro tres mas: `cli/cargar_config.py` apagaba la banda en silencio (el umbral no estaba en `SECCIONES_EDITABLES`, y ese comando se corre tras cada pull); la regla del umbral valia por una sola puerta (el par 72/24 entraba por el YAML); y la guarda del barrido no alcanzaba si la semilla no declara `rol_de_entrada` --el caso del segundo ISP-- sin emitir ninguna señal. Corregidos: umbral en la lista protegida, `sin_gestion_horas_efectivas()` que acota el umbral por cualquier puerta sin poder volver incargable una config, y el barrido que **no cierra nada** con la config degradada. Mas el marcado del origen movido al lector de YAML, la clave obligatoria en el endpoint, y `forzado`/`motivo` fijados en el sitio de llamada (una mutacion del auditor postergaba una escalada FORZADA y ninguna de nueve pruebas lo veia). Las cinco mutaciones que sobrevivian ahora mueren. Verificado: once guardas rapidas verdes, relevo con base solo los dos rojos previos, vitest 345/345 en las superficies tocadas, y casos dorados 9/10 con la varianza medida contra `4f1ea12` (8/10 en el mismo entorno) | Cuatro deudas nuevas (L9..L12). Push y `DEXTER_ESTADO_ACTUAL.md`: sesion dueña |
| 26/09/2026 | **Tercera auditoria, con regla de parada declarada:** se audita lo que AGREGA mecanismo, no lo que solo acota. Encontro que la linea que arreglaba el agujero no tenia guarda --mutar `/conversaciones` al umbral crudo devolvia la ventana de 48 h con la bateria entera en verde-- y que su `hasattr` restituia la conducta vieja en silencio; que el 400 del endpoint vigilaba una puerta por la que nadie entra, porque el helper de JS convertia la ausencia en null (con una prueba mia bendiciendolo); y que el formulario mostraba 72 mientras la banda actuaba a las 24, sin señal. Corregidos los tres: guarda de efecto en §14 contra PostgreSQL --se intento sin base y no se puede, importar `api` exige credenciales--, el helper revienta sin llegar a la red, y el GET/PUT devuelven los dos umbrales con aviso en la pantalla. **La mutacion que sobrevivia ahora pone §14 en rojo (medido).** Verificado: once guardas verdes, vitest 345/345, relevo con §14 en verde y solo los dos rojos previos | Tres deudas nuevas (L13..L15). Push y `DEXTER_ESTADO_ACTUAL.md`: sesion dueña |
| 26/09/2026 | **Checklist de salida (`guardia-de-release`), el paso 7 del flujo.** Verde con tres avisos. Medido: el merge es fast-forward (la base no derivo, 0 commits en la direccion contraria, comparado por contenido), cero migraciones, cero variables nuevas, cero solape de archivos con `integrar-centro-mando`, y la puerta de `cargar_config.py` se NIEGA de verdad con el umbral guardado (ejecutada, no leida). **Riesgo propio corregido:** el 400 del endpoint rompia la ventana entre el motor nuevo y el bundle viejo --no se podia guardar ninguno de los tres ajustes--; ahora entra solo cuando hay una banda encendida. La trampa del rollback (L5) quedo escrita en `DESPLIEGUE.md` §7, que es donde se busca. Aviso que hay que dar antes del deploy: los contadores de la cabecera bajan de golpe por el arreglo de L7, y se lee como si desaparecieran conversaciones | **Hueco unico y nombrado: los 56 casos dorados completos**, que §6 exige porque la nota al modelo cambio y `--humo` no distingue una regresion chica. Push y `DEXTER_ESTADO_ACTUAL.md`: sesion dueña |
| 26/09/2026 | **Casos dorados completos corridos (88 casos, no 56), y el hueco que destaparon.** Rama `f519af4` **70/88**; control sobre `f90d3ec` en el MISMO entorno **69/88**: la rama queda un caso mejor, con 2 divergentes de un lado y 3 del otro --varianza del modelo, no regresion--. De los 18 fallos, 4 son credenciales ausentes (`SMARTOLT_API_KEY`, `BOTTLECRM_API_TOKEN`) y el RAG no responde en este entorno, asi que **el 80% no es el numero del sistema sano** y solo vale contra su propio control. **Y lo que importa mas: verificado en codigo que `cli/evaluar.py` NO ejercita la posposicion (cero apariciones de `por_que_posponer`, `_aplicar_posposicion`, `intento_antes_de_escalar`, `nota_pendiente`), asi que los casos dorados no pueden ver a B.** La corrida no confirma ni desmiente su conducta: solo que la rama no empeora lo que el set si mide. El instrumento correcto para este camino es `cli/bateria_flujos.py` (40/41 bajo B, mas arriba en esta ficha) | Para un cambio en el camino del turno, 'corre los casos dorados' NO es la verificacion correcta: va al bloque de cobertura. Push y `DEXTER_ESTADO_ACTUAL.md`: sesion dueña |
