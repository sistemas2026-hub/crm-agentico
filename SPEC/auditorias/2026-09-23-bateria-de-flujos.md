# Auditoría adversarial · batería de flujos y afirmaciones nuevas

> 23/09/2026. Sobre `cli/bateria_flujos.py` (`b66dba9`), las afirmaciones
> `bloquea_con`/`no_bloquea_con` de `cli/evaluar.py` y los casos dorados
> reescritos (`6bebbb9`), más lo desplegado ese día.

**Cómo se hizo, y su límite.** El agente `auditor-independiente` del repo **no
se pudo invocar**: sus definiciones llegaron con el rebase del mismo día y la
sesión había cargado su lista de agentes al arrancar. Se aplicó su método a
mano —los cinco huecos que el proyecto ya pagó— con un agente genérico. Hay que
rehacerla con el agente cuando esté cargado.

Doce hallazgos. Los tres primeros se arreglaron el mismo día (`81677b4`); el
resto queda anotado acá con su motivo, que es lo que exige el criterio 9 del
objetivo.

---

## Resueltos (`81677b4`)

**1 · La batería daba verde con el turno caído.** Se atrapaba la excepción, se
imprimía `ERROR` y se seguía a juzgar. Con la traza vacía, todo caso que sólo
afirme cosas negativas pasaba: **5 de 21 en verde con el sistema entero caído**.
Y el camino silencioso era peor — `atender_turno` no lanza cuando no consigue
cupo, devuelve `{"respuesta": "", "sin_turno": True}`, así que el caso recorría
sus turnos sin que nadie lo atendiera y terminaba verde sin imprimir una línea.
→ Un caso que no ocurrió ya no se juzga: se reporta roto.

**2 · `deriva_a` medía otra cosa.** Leía `rol_solicitante` de `tool_calls`, que
**no es quien pidió la herramienta**: es el rol en que terminó el turno.
`_atender_turno` reasigna `rol = sesion.rol_siguiente` antes de que el hilo de
traza cierre sobre la variable, y `db.py` escribe ese único escalar en todas las
filas. La fila de `derivar_a_area` llamada por el router quedaba etiquetada con
el área destino. Afectaba a 9 de 21 casos. Tampoco sirve `parametros`: la traza
los guarda enmascarados y el área vuelve como `'...ntas'`.
→ Se lee el rol activo de la sesión.

**3 · La garantía de seguridad era falsa.** *"Ninguna acción queda fuera de
`pendiente`"* sólo miraba `acciones_propuestas`, donde cae únicamente lo que
declara `aprobacion_humana`: **14 de las 30 herramientas de escritura**. Las
otras 16 ejecutan directo y no dejan fila. Una tanda con `--todos` dentro del
contenedor podía abrir una visita técnica real y salir en verde.
→ Se afirma sobre `es_escritura`, excluyendo lo que quedó propuesto (una
propuesta también figura con `exito=true`).

---

## Anotados, con su motivo

**4 · Dos códigos de compuerta no están clasificados como bloqueo.**
`CODIGOS_DE_BLOQUEO` tiene 30 códigos y le faltan al menos dos:

```
DECLARACION_NO_ALCANZA    motor.py:3734 -- "fail-closed en codigo", es un gate
AUTONOMIA_2_NO_ACTIVA     llega como "AccionExternaNoAutorizada: AUTONOMIA_2_..."
```

El segundo **no lo ve `tests/test_bloqueos_en_traza.py`**, que escanea las
asignaciones `codigo_error = "..."` de `motor.py`: este código llega por el
`except` **genérico** (`f"{type(e).__name__}: {e}"`) en vez del que preserva
`e.codigo`. Se encontró midiendo una tanda real, no leyendo.

Consecuencias, y por eso importa: una llamada frenada por estos gates viaja
como **error** y no como bloqueo, así que (a) un caso con `sin_errores: true`
sale **rojo con la protección funcionando** —el falso rojo que la columna
`es_bloqueo` vino a eliminar el 08/09— y (b) `bloquea_con` no los puede
afirmar nunca.

*Motivo para no arreglarlo acá:* cambia qué cuenta como error en toda la
evaluación, así que exige medir los casos dorados antes y después. Es un
objetivo propio, chico y bien acotado. `tests/test_bloqueos_en_traza.py` está
**rojo en la rama** por esto desde antes de este bloque.

**5 · `motivo` obligatorio garantiza la clave, no el contenido.** El esquema de
`_esquema_evaluacion` lo exige, pero `{"escalar": true, "motivo": ""}` pasa sin
validación: el chequeo de campos vacíos de `escalamiento.py` mira
`siguiente_paso` y `no_se_pudo_comprobar`, **no `motivo`**. El cliente recibe
entonces el texto genérico, que es exactamente el estado del 23/09 que el
cambio decía haber cerrado — ahora sin siquiera el `null` visible.

Y su guarda (`tests/test_saludo_y_motivo.py`) afirma que `"motivo" in
requeridos`: **presencia del mecanismo, no efecto**. Sobrevive intacta a una
inversión de la conducta.

*Motivo para no arreglarlo acá:* la restricción del objetivo prohíbe cambiar
conducta. Ningún caso dorado cubre el motivo elegido por el modelo — los dos
que afirman `escala_motivo` esperan `solicitud_explicita`, que **lo fuerza el
código**, no el modelo.

**6 · El caso reescrito ya no mide lo que su nombre dice.** *"sin el serial
cargado **no se le pide la cédula**"* ahora sólo comprueba que el gate clasificó
bien. Si alguien revierte la `instruccion_interna` de
`falta_un_dato_de_la_sesion` a la versión vieja dejando el código intacto, el
caso sigue **verde con el síntoma del 15/09 vivo**.

*Motivo:* la versión anterior (`responde_sin: [cedula]`) medía el efecto pero
marcaba rojo una respuesta correcta que dijera *"no necesito tu cédula"* —4 de
5—. Lo correcto es tener **las dos**: `bloquea_con` más un `responde_sin`
estrecho (`"pasame tu cedula"`, `"me pasas tu cedula"`) que no castigue la
negación. Queda pendiente.

**7 · El reencauzamiento borra la traza de la vuelta que lo provocó.**
`api.py` reasigna `registro_herramientas` con el resultado de la segunda pasada,
y el hilo de traza cierra sobre la lista final: las llamadas de la primera
**nunca se persisten**. La guarda nació de un caso donde *"la traza tenía lo que
se ejecutó: nada"*, y cuando dispara destruye la evidencia de qué hizo mal el
modelo.

*Hoy no pierde efectos* —el único rol que se reencauza es `cliente_final`, sin
herramientas de escritura— pero sí auditoría. Relacionado: el sufijo
`:reencauzado` del origen produce **dos claves de idempotencia distintas**
(`idempotencia.clave_de` la arma con el origen), así que la misma operación
externa intentada en las dos vueltas se ejecutaría dos veces. Inalcanzable hoy,
por lo mismo.

**8 · Un camino donde la identidad se resuelve sin dejar evento.** Al retomar
una conversación abierta, `api.py` restaura `verificado` e `id_cliente` desde la
base **sin ninguna llamada a herramienta**, y `evento_identidad` sólo emite si
hay bloqueo o si la herramienta verifica/confirma. Tras un reinicio del motor,
esa conversación queda en `identidad_eventos` con un `bloqueo` y ningún
`verificacion_ok` → `cli/embudo_identidad.py` la cuenta como abandono. **La
métrica que la tabla existe para bajar se infla sola con cada reinicio.**

*Motivo:* no hay tráfico real todavía, así que el sesgo no distorsiona ninguna
decisión hoy. Antes de usar el embudo para decidir la Fase 2, hay que cerrarlo.

**9 · La batería no distingue intento de ejecución exitosa.** `usadas` se arma
ignorando `exito` y `codigo_error`, que la traza **sí trae**. `usa:
["consultar_estado_ont"]` da verde con la herramienta devolviendo 500. Es el
mismo falso verde del 12/09 que motivó `no_intenta` en `cli/evaluar.py`,
reintroducido en la batería.

**10 · Claves mal escritas en `espera`: silencio en los dos arneses.** Ni
`_juzgar` ni `correr_caso` validan el conjunto de claves. `propuesta:` en vez de
`propone:`, `derivar_a:` en vez de `deriva_a:` → ignorada, verde. Hoy no hay
ninguna clave huérfana en los 21 casos ni en los 92 del YAML (verificado), así
que es latente. Lo hace más probable que el contrato de la batería documente
`propone` y **ningún caso la use**. Además `{"escala": "no"}` da verde contra
`escalada_a_humano=True`, porque `bool("no")` es `True`.

**11 · La franja horaria puede estar dando UTC.** Si la imagen no trae `tzdata`,
`ZoneInfo('America/Bogota')` falla siempre y el respaldo es la hora del
servidor. A las 20:00 de Bogotá el prompt diría *"mañana, de madrugada"* — el
bug del 14/08 al revés, y adelantado, que es el lado que hace hablar de un corte
que todavía no pasó. **No medido.** Se comprueba en un comando:

```
docker exec <contenedor-motor> python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('America/Bogota'))"
```

**12 · Los números de aceptación no coincidían con lo que la batería corre.**
Decía 20 y son 21 (19 locales, 2 de CRM). Corregido en `81677b4`; el objetivo
quedó con el desvío anotado.

---

## Lo que el auditor probó y le pareció sólido

- El aislamiento del canal `whatsapp-simulado` es real: clave de sesión propia.
- El whitelist de estados de la comprobación de seguridad es fail-closed de
  verdad (`'aprobada'`, `'Pendiente'`, `''` y `None` salen todos rojos).
- `identidad_eventos` cumple su promesa de no llevar PII: los motivos son
  vocabulario fijo, y los enum del `check` cubren exactamente lo que produce
  `evento_identidad`.
- `entorno()` se **mide** resolviendo `backend:8000` en vez de declararse.
- Numerar cada tanda con sufijo aleatorio evita el arrastre de conversación.

## Lo que quedó sin auditar

- No se corrieron `bateria_flujos.py` ni `evaluar.py` desde el agente (exigen
  base de producción y llamadas al modelo): **no se sabe con qué frecuencia
  ocurre cada falso verde** en una tanda real.
- La carrera entre el hilo de traza y la lectura de la batería: necesita
  medirse contra la base real.
- `tzdata` en la imagen (hallazgo 11): exige levantar el contenedor.
