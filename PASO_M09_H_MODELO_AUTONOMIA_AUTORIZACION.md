# PASO M09-H — Modelo de autonomía y autorización por herramienta

**Fecha:** 2026-09-17
**Naturaleza:** **diseño y auditoría**. No se modificó código, no se creó ninguna
migración, no se tocó producción, no se cambió el kill switch, no se ejecutó
ninguna herramienta. Lo único que se hizo contra producción fueron **lecturas**.

## Cómo leer este documento

Cada afirmación lleva una etiqueta, y la distinción es el punto del paso:

| Etiqueta | Significa |
|---|---|
| **[MEDIDO]** | Se comprobó contra el código o contra producción. Es un hecho. |
| **[DISEÑO]** | Propuesta. **No está implementado.** No existe en ningún archivo. |
| **[DEPENDENCIA]** | Otra cosa tiene que existir primero. |
| **[RIESGO]** | Puede salir mal. Se nombra para que no sorprenda. |
| **[PENDIENTE]** | Requiere una decisión humana que este documento no toma. |

> **Nada en este documento está construido.** Donde dice [DISEÑO], no hay código.

---

## 1. Inventario actual — qué existe y qué es solo conceptual

### 1.1 — La tabla del inventario

| Pieza | ¿Existe? | Dónde | Naturaleza real |
|---|:--:|---|---|
| `tenant_config` | **[MEDIDO] sí** | `asistente.tenant_config` | versionada; **v146** en producción; la base es la fuente de verdad, el YAML es semilla |
| `requiere_confirmacion` | **[MEDIDO] sí, pero** | `schema.py:1505` | **invariante de CONFIGURACIÓN**, no compuerta de ejecución — ver 1.2 |
| `aprobacion_humana` | **[MEDIDO] sí** | `schema.py:805`, `motor.py:3213` | **la compuerta real**, opt-in. **4 de 27** escrituras |
| `exige_previas` | **[MEDIDO] sí** | `motor.py::_previas_no_cumplidas` | precondiciones en código, fail-closed. **3 de 27** |
| `acciones_propuestas` | **[MEDIDO] sí** | `asistente.acciones_propuestas` | 40 filas: 36 pendientes, 4 aprobadas y ejecutadas |
| `PropuestaSupervisor` | **[MEDIDO] sí** | `operaciones_propuesta_supervisor` | RLS **habilitada y forzada**; 0 filas en producción |
| Kill switch | **[MEDIDO] sí** | `asistente.interruptor_autonomia` | **binario**: `(ACTIVO, DETENIDO)`. Fail-closed, sin caché |
| Idempotencia | **[MEDIDO] sí** | `asistente.operaciones_externas` | 0 filas; clave `origen\|herramienta\|hash(args resueltos)` |
| Permisos | **[MEDIDO] sí** | `ROLES_GESTION` | `{ADMIN, SUPERVISOR, OPERACIONES}` |
| Actor / usuario | **[MEDIDO] sí, doble** | `Activity.user` (FK Profile) y `frontera._Permiso.actor` (str) | **dos representaciones distintas** — ver 1.3 |
| **Autonomía por nivel** | **[MEDIDO] NO** | `PropuestaSupervisor.NIVELES` | **solo conceptual**: `choices` de un CharField del CRM. Cero presencia en el motor |
| Auditoría | **[MEDIDO] sí** | `common.Activity`, `asistente.audit_log`, `tool_calls` | tres registros, cada uno con su dominio |
| Ejecución externa | **[MEDIDO] sí** | `http.py::ejecutar`, `whatsapp.py::_post` | **exactamente dos caminos de escritura** — ver 1.4 |

### 1.2 — La corrección más importante del paso

M09-G registró *"27/27 con confirmación obligatoria"*. Es exacto como
descripción del campo, y **se presta a leerse como algo que no es**. La lectura
precisa:

**[MEDIDO]** `requiere_confirmacion` es una **invariante de configuración**:

```python
# nucleo/config/schema.py:1505
if not self.solo_lectura and not self.requiere_confirmacion:
    raise ValueError("... escribe y no exige confirmacion. Toda accion "
                     "de escritura requiere confirmacion humana explicita.")
```

Un catálogo con una escritura que no la declare **no se puede cargar**. Eso es
valioso y es real. Pero:

```
# nucleo/modelo/motor.py:34
- No hay mecanismo de confirmacion humana asincrona para escrituras.
  'requiere_confirmacion' se valida en schema.py pero no se aplica aca
```

**[MEDIDO]** La compuerta que sí detiene una ejecución en tiempo real es
`aprobacion_humana`, descrita en el propio código como *"el gate real, opt-in"*.
En producción:

```
con aprobacion_humana : 4 de 27   (crear_ticket, responder_ticket,
                                   actualizar_estado_ticket, agregar_promesa_pago)
con exige_previas     : 3 de 27   (reiniciar_ont, cambiar_tipo_onu, activar_catv)
sin ninguna de las dos: 20 de 27
```

**[MEDIDO]** ¿Qué protege hoy a esas 20? El kill switch y la frontera: las 27
están clasificadas como acción autónoma por `solo_lectura`, así que ninguna sale
sin permiso vigente. **Lo que no tienen es una compuerta de aprobación propia.**
Con el kill switch DETENIDO da igual; el día que se active, sí importa.

**[RIESGO]** Leer "27/27 con confirmación obligatoria" como "27 tienen
aprobación humana en ejecución" llevaría a activar autonomía creyendo que hay
una red que no está puesta bajo 20 de ellas.

### 1.3 — El actor tiene dos formas, y no son compatibles

**[MEDIDO]**

| Registro | Campo de actor | Tipo |
|---|---|---|
| `common.Activity` (CRM) | `user` | FK a `Profile` |
| `frontera._Permiso` (motor) | `actor` | `str` libre ("motor", un `origen`, un `run_id`) |

**[RIESGO]** Una auditoría unificada de autonomía no puede juntar las dos sin
perder información: un `str` no dice si detrás hay una persona, un servicio o el
propio motor. El §10 pide exactamente `actor` **y** `tipo de actor` — y este
hallazgo es la razón por la que hacen falta los dos campos.

### 1.4 — Solo hay dos caminos de escritura saliente

**[MEDIDO]** Módulos del núcleo capaces de emitir HTTP: **siete**. De ellos,
capaces de **escribir**: **dos**.

| Módulo | Escribe | ¿Frontera? |
|---|:--:|:--:|
| `herramientas/http.py` | **sí** (`requests.request(metodo, ...)`) | **sí** — `_exigir_frontera` al entrar |
| `canales/whatsapp.py` | **sí** (`_post`) | **no** |
| `herramientas/agregado.py` | no (6 GET) | n/a |
| `herramientas/estabilidad.py` | no (9 GET) | n/a |
| `herramientas/incidentes.py` | no (26 GET) | n/a |
| `herramientas/localidades.py` | no (9 GET) | n/a |
| `herramientas/sondeo.py` | no (3 GET) | n/a |

**[MEDIDO]** Y el motivo por el que el control está en el ejecutor y no en cada
llamador está escrito en el propio archivo:

> *"El control esta aca —y no en cada llamador— porque el paso 10.14 midio cinco
> caminos distintos que llegaban a escribir sin pasar por el gate del motor.
> Ponerlo en el ejecutor lo vuelve inevitable: un modulo nuevo que escriba afuera
> pasa por aqui aunque no sepa que esto existe."*

Esa propiedad es la base de todo el §5.

### 1.5 — Colisión de nombres que hay que evitar

**[MEDIDO]** Ya existe un `nivel` en el núcleo: `nucleo/seguridad/verificacion.py`
lo usa para **verificación de identidad** (0 = desconocido, 1 = verificado por
posesión del número). No tiene nada que ver con autonomía.

**[DISEÑO]** Todo lo que este documento propone se llama **`nivel_autonomia`**,
nunca `nivel` a secas. Dos ejes distintos con el mismo nombre terminarían
comparándose por accidente.

---

## 2. Los niveles 0–4, formalizados

**[DISEÑO]** Ninguno de estos niveles existe hoy como mecanismo.

### Nivel 0 · Observar

| | |
|---|---|
| **Puede** | leer, detectar, registrar métricas y señales |
| **NO puede** | proponer una acción; escribir nada fuera de sus propias tablas |
| Crear propuesta | **no** |
| Modificar actividad / programación | no / no |
| Llamar herramienta | solo `solo_lectura: true` |
| Aprobación | no aplica |
| Evidencia | la observación con fuente, id, dato y hora |
| Auditoría | registro de detección |

### Nivel 1 · Recomendar — **donde está Rapilink hoy**

| | |
|---|---|
| **Puede** | todo lo de nivel 0 + crear una `PropuestaSupervisor` con evidencia |
| **NO puede** | **ejecutar nada.** Ni interno, ni reversible, ni "pequeño" |
| Crear propuesta | **sí** |
| Modificar actividad / programación | no / no |
| Llamar herramienta | solo `solo_lectura: true` |
| Aprobación | la propuesta la revisa un humano; la revisión **no ejecuta** |
| Evidencia | obligatoria — `CheckConstraint propuesta_exige_evidencia` |
| Auditoría | creación + decisión humana (`APPROVED`/`REJECTED`/`UPDATE`) |

**[MEDIDO]** Garantizado por tres cosas a la vez: `ejecutada` no es un estado
posible, `ejecutar_propuesta` levanta siempre, y ninguna ruta de `operaciones/`
contiene `ejecutar`.

### Nivel 2 · Coordinar

| | |
|---|---|
| **Puede** | ejecutar herramientas de **efecto interno** y reversible |
| **NO puede** | **ningún efecto externo.** Ni un ticket en WispHub, ni un mensaje |
| Crear propuesta | sí |
| Modificar actividad | **sí**, si M02 es dueño del efecto y lo autoriza |
| Modificar programación | **no** — eso es efecto sobre personas reales |
| Llamar herramienta | las internas autorizadas **una por una** |
| Aprobación | no por ocurrencia; sí autorización previa por herramienta |
| Evidencia | la de la propuesta + los **argumentos resueltos** |
| Auditoría | **auditoría de ejecución** (§10), distinta de la de propuesta |

### Nivel 3 · Ejecutar acciones reversibles autorizadas

| | |
|---|---|
| **Puede** | efectos **externos reversibles**, sobre herramientas autorizadas una por una |
| **NO puede** | nada irreversible; ninguna comunicación a una persona; ningún cierre; nada que toque facturación |
| Crear propuesta | sí |
| Modificar actividad / programación | sí / **sí**, con M03 como dueño |
| Llamar herramienta | las autorizadas, **y solo si todas sus condiciones se cumplen** |
| Aprobación | no por ocurrencia; **sí** autorización vigente y no vencida |
| Evidencia | propuesta + argumentos resueltos + clave de idempotencia + **plan de reversión** |
| Auditoría | completa (§10) + resultado + validación |

### Nivel 4 · Acción crítica con aprobación humana

| | |
|---|---|
| **Puede** | **nada por sí solo** |
| **NO puede** | ejecutar sin una aprobación humana **de esa ocurrencia concreta** |
| Crear propuesta | sí |
| Llamar herramienta | solo tras la aprobación explícita |
| Aprobación | **obligatoria, por ocurrencia.** No existe autorización permanente de nivel 4 |
| Evidencia | todo lo de nivel 3 + la identidad de quien aprobó |
| Auditoría | completa + quién aprobó, cuándo y con qué motivo |

### La regla que evita el error clásico

**[DISEÑO]**

> **Un nivel superior NO habilita automáticamente las herramientas de los niveles
> inferiores, ni ninguna otra.** El nivel es un **techo**, no una llave.
>
> `nivel_autonomia_org = 3` no significa "puede ejecutar todo lo de nivel ≤ 3".
> Significa "**puede**, para las herramientas que además estén autorizadas
> individualmente, y que además cumplan sus condiciones".
>
> Una organización en nivel 3 con **cero** herramientas autorizadas ejecuta
> **cero** herramientas. Y eso debe ser el estado inicial.

---

## 3. Autorización por herramienta

**[DISEÑO]** Un registro conceptual por (organización, herramienta):

| Atributo | Qué declara |
|---|---|
| `nivel_requerido` | el nivel mínimo que esta herramienta exige |
| `tipo_efecto` | dato / comunicación / infraestructura / financiero |
| `interno_externo` | quién percibe el efecto |
| `reversible` | existe operación que restituye, **y deja rastro de ambas** |
| `condiciones` | lista de precondiciones que deben cumplirse **todas** |
| `aprobacion_por_ocurrencia` | si cada ejecución necesita un humano |
| `evidencia_requerida` | qué debe acompañar la solicitud |
| `idempotencia_requerida` | si exige origen estable |
| `kill_switch_requerido` | siempre `true` para escrituras |
| `auditoria_requerida` | siempre `true` |
| `vigencia` | hasta cuándo vale la autorización |

**[DISEÑO]** Y la evaluación es una **conjunción**, nunca una comparación sola:

```
permitido  =  kill_switch == ACTIVO
          AND tenant válido y coincidente
          AND nivel_autonomia_org  >=  nivel_requerido
          AND existe autorización explícita (org, herramienta)
          AND autorización vigente (no vencida)
          AND todas las condiciones se cumplen
          AND idempotencia disponible si la herramienta la exige
          AND evidencia presente si la herramienta la exige
```

### La pregunta del §3, respondida

> ¿Qué sucede si `nivel autorizado >= nivel requerido` pero una condición
> adicional no se cumple?

**[DISEÑO]** **NO SE EJECUTA.** Y hay que ser explícito sobre por qué, porque es
la tentación de diseño más peligrosa de todo el modelo:

El nivel es **necesario y no suficiente**. Tratarlo como suficiente convierte
"subir el nivel" en un atajo que abre todas las puertas a la vez — que es
exactamente el problema estructural que M09-G encontró en el interruptor binario,
reintroducido con más pasos.

El rechazo debe registrar **cuál** condición falló, no un "no autorizado"
genérico: un rechazo que no dice qué faltó obliga a adivinar, y quien adivina
termina relajando la condición equivocada.

---

## 4. Autorización ≠ ejecución

**[DISEÑO]** Siete etapas. Hoy la cadena se corta —a propósito— en la segunda.

```
PROPUESTA ─► DECISIÓN ─► AUTORIZACIÓN ─► EJECUCIÓN ─► RESULTADO ─► VALIDACIÓN ─► CIERRE
   IA         humano        técnica        sistema      del tercero   medición     humano
              │
              └── HOY LA CADENA TERMINA AQUÍ
```

| Etapa | Quién | Qué produce |
|---|---|---|
| Propuesta | IA | una fila con evidencia |
| **Decisión humana** | Jefe de Operaciones | una opinión registrada |
| **Autorización técnica** | el sistema | un permiso, evaluando la conjunción del §3 |
| Ejecución | el sistema | una llamada |
| Resultado | el tercero | una respuesta (o silencio) |
| Validación | el sistema | `CONFIRMADA` / `NO_CONFIRMADA` / `NO_VERIFICABLE` |
| Cierre | humano | el problema resuelto |

### Por qué aceptar no debe ejecutar

**[MEDIDO]** Hoy no puede: `ejecutar_propuesta` levanta y `ejecutada` no existe.

**[DISEÑO]** Y cuando exista ejecución, **tampoco debe encadenarse**, por tres
razones que no son de estilo:

1. **La decisión y la autorización responden preguntas distintas.** El humano
   dice *"esto que propones tiene sentido"*. La autorización técnica dice *"y
   además el kill switch está activo, el tenant coincide, la herramienta está
   autorizada, hay idempotencia y las condiciones se cumplen"*. Un humano no
   puede responder la segunda: no la ve.
2. **El tiempo entre las dos no es cero.** Alguien puede aceptar una propuesta y
   ejecutarla tres horas después. En el medio el kill switch pudo detenerse, la
   condición pudo desaparecer, o el caso pudo cerrarse por otra vía. La
   autorización se evalúa **en el instante de ejecutar**, no en el de aceptar.
3. **Si aceptar ejecutara, el revisor cargaría con la responsabilidad técnica.**
   Aceptar pasaría a significar *"me hago cargo de que el sistema está en
   condiciones"*, que no es algo que un Jefe de Operaciones pueda saber.

**[DISEÑO]** Una propuesta aceptada debería producir, como mucho, una **fila en
`asistente.acciones_propuestas`** —la tabla que ya existe— en estado
`pendiente`. Esa fila, y no la propuesta, sería lo ejecutable.

**[MEDIDO]** El campo puente ya está declarado y vacío:
`PropuestaSupervisor.accion_propuesta_ref`, *"Vacío en Shadow Mode"*.

---

## 5. La frontera — y dónde tiene que estar físicamente

**[DISEÑO]** Secuencia conceptual:

```
  request ─► actor/contexto ─► tenant ─► nivel_autonomia ─► autorización herramienta
                                                                      │
      resultado ◄── auditoría ◄── ejecución ◄── idempotencia ◄── kill switch
```

### Dónde va, y por qué ahí

**[MEDIDO]** El paso 10.14 midió **cinco caminos distintos** que llegaban a
escribir sin pasar por el gate del motor. La solución no fue tapar los cinco: fue
mover el control **al ejecutor**, `nucleo/herramientas/http.py::ejecutar`, donde
es inevitable.

**[DISEÑO]** Las comprobaciones de nivel y de autorización por herramienta deben
ir **en ese mismo punto**, no en el motor:

| Si se pone en… | Qué pasa |
|---|---|
| el motor (`motor.py`) | un endpoint nuevo que llame al ejecutor directo **se la salta** — es literalmente lo que pasó en 10.14 |
| cada llamador | hay que acordarse cada vez; el que se olvide abre el agujero |
| **el ejecutor (`http.py`)** | **un módulo nuevo pasa por ahí aunque no sepa que existe** |

**[DISEÑO]** Regla estructural que debería quedar escrita:

> **Todo efecto externo se emite desde un único punto por transporte.**
> HTTP: `http.py::ejecutar`. Mensajería: un equivalente en `whatsapp.py` (§7).
> Un transporte nuevo (SMTP, un SDK, un socket) **es un punto nuevo, y nace sin
> frontera**: agregarlo obliga a construirle la suya. Eso debería ser parte de la
> definición de "terminado" de cualquier integración futura.

**[RIESGO]** La frontera no puede proteger de lo que no pasa por ella. Hoy el
único transporte de escritura fuera de `http.py` es WhatsApp.

**[DISEÑO]** Una guarda de arquitectura —del mismo tipo que
`tests/test_nucleo_sin_tenants.py`— que falle si aparece un `requests.post/put/
patch/delete` en cualquier módulo del núcleo que no sea uno de los puntos
declarados. Es barata y convierte la regla en algo que se rompe solo.

---

## 6. Bypass — qué es bypass real y qué no

**[DISEÑO]** El criterio:

> Es **bypass real** cuando el sistema produce un efecto externo **sin que una
> persona lo haya pedido en ese momento** y sin pasar por la frontera.
>
> Es **operación humana reactiva** cuando hay una persona que acaba de pedirlo
> —un cliente que escribió, un operador que apretó enviar— y el sistema responde.
> Someterla al kill switch de autonomía sería frenar a la empresa, no a la IA.

| Vía | Estado | Clasificación |
|---|---|---|
| `tenant = None` | **[MEDIDO]** cerrado: `ACCION_EXTERNA_SIN_TENANT` | era bypass real |
| `tenant = ""` | **[MEDIDO]** cerrado, mismo código | era bypass real |
| Llamada directa al ejecutor | **[MEDIDO]** cerrado: el control está **en** el ejecutor | era bypass real (10.14) |
| Endpoint HTTP nuevo | **[MEDIDO]** cubierto si usa el ejecutor | **[RIESGO]** no cubierto si estrena transporte |
| Scheduler | **[MEDIDO]** registro cerrado, **0 trabajos**; sin registro dinámico | no explotable hoy |
| `threading.Thread` | **[MEDIDO]** ContextVar **no** se hereda → sin permiso → falla cerrado | cerrado, y a favor |
| `asyncio` | **[MEDIDO]** ContextVar **sí** se copia → el permiso viaja | **[RIESGO]** correcto hoy; a revisar si se abren tareas de larga vida |
| Operaciones internas | **[MEDIDO]** la frontera decide por `solo_lectura`, no por `tipo` | cubiertas |
| **WhatsApp** | **[MEDIDO]** sin frontera; **9 puntos, los 9 reactivos** | **operación humana reactiva** hoy; §7 |
| Ejecutor HTTP | **[MEDIDO]** es el punto de cumplimiento | cubierto |
| Herramientas que no usan el motor | **[MEDIDO]** 5 módulos con HTTP, **todos GET** | sin capacidad de escritura |
| `aprobacion_humana` ausente en 20 de 27 | **[MEDIDO]** | **no es bypass** —el kill switch cubre— pero **es una red que falta** |

**[RIESGO]** El bypass que no está en la lista es el que todavía no existe: un
transporte nuevo. Por eso el §5 propone la guarda de arquitectura.

---

## 7. WhatsApp — el contrato

**[MEDIDO]** Se conserva íntegra la conclusión de M09-G: los nueve puntos de
llamada son reactivos. **No se modificó `whatsapp.py`.**

**[DISEÑO]** El contrato que debería regir cualquier comunicación futura:

| Tipo | Definición | Frontera |
|---|---|---|
| **Reactiva** | existe un mensaje entrante del destinatario, o una acción de un operador, **en esta misma conversación y turno** | **no** pasa. No debe bloquearse |
| **Proactiva** | todo lo demás: recordatorio, seguimiento, notificación, campaña, reintento diferido | **sí** pasa, con `nivel_autonomia ≥ 3` y autorización por plantilla |

**[DISEÑO]** Cómo se haría cumplir sin tocar los nueve puntos existentes:

> Una función **nueva y separada** para el envío proactivo, que nazca con la
> frontera adentro. Las funciones reactivas actuales se quedan como están.
>
> Se elige así, y no poniendo la frontera dentro de `enviar_texto`, por una razón
> concreta: si el control viviera en la función compartida, alguien tendría que
> decidir *en cada llamada* si ese envío es reactivo o proactivo — y esa decisión,
> tomada nueve veces por nueve autores distintos, es donde se cuela el error.
> Dos funciones distintas hacen que la clasificación sea **una propiedad del
> código**, no un juicio que se repite.

**[PENDIENTE]** Si el envío proactivo debe además exigir plantilla aprobada por
Meta: probablemente sí fuera de la ventana de 24 h, pero es una restricción del
proveedor que hay que verificar, no asumir.

---

## 8. Fallbacks — todos fail-closed

**[DISEÑO]** Una sola regla, sin excepciones:

> **NO EJECUTAR + REGISTRAR el motivo concreto.** Reintentar o escalar **solo**
> según una política autorizada por escrito. Sin política, no ejecutar.

| Condición | Comportamiento | ¿Existe hoy? |
|---|---|:--:|
| Tenant inexistente | no ejecutar; `ACCION_EXTERNA_SIN_TENANT` | **[MEDIDO]** ✔ |
| Tenant vacío | ídem | **[MEDIDO]** ✔ |
| Tenant distinto al del permiso | `ACCION_EXTERNA_TENANT_DISTINTO` | **[MEDIDO]** ✔ |
| **Nivel no configurado** | tratar como **nivel 0**, no como "sin límite" | **[DISEÑO]** |
| **Herramienta no registrada** | no ejecutar | **[DISEÑO]** |
| **Herramienta sin nivel declarado** | no ejecutar. Un `null` **no es** nivel 0 permisivo | **[DISEÑO]** |
| Kill switch detenido | no ejecutar | **[MEDIDO]** ✔ |
| Kill switch ilegible | **no ejecutar** — *sin control no es autorización* | **[MEDIDO]** ✔ |
| Idempotencia ausente | no ejecutar si la herramienta la exige | **[DISEÑO]** (hoy se registra la limitación) |
| Evidencia ausente | no proponer siquiera | **[MEDIDO]** ✔ |
| Permiso de rol insuficiente | 403 | **[MEDIDO]** ✔ |
| Contexto inválido | no ejecutar | **[MEDIDO]** ✔ |
| Herramienta desconocida | no ejecutar | **[MEDIDO]** ✔ |
| Timeout externo | **no reintentar** — la llamada pudo salir | **[MEDIDO]** ✔ |
| Error externo | no reintentar solo; registrar | **[MEDIDO]** ✔ |
| Resultado ambiguo | `NO_VERIFICABLE`, **nunca** `NO_CONFIRMADA` | **[MEDIDO]** ✔ |
| Concurrencia | la primera decisión gana; 409 | **[MEDIDO]** ✔ |
| **Autorización vencida** | no ejecutar; **no renovar sola** | **[DISEÑO]** |

**[DISEÑO]** Los tres que más importan porque son donde un descuido se disfraza
de valor por defecto:

- **Nivel no configurado ⇒ 0.** Si un tenant nuevo naciera "sin nivel" y eso se
  interpretara como "sin restricción", el alta de un cliente sería el agujero.
  Igual que el kill switch, que **nace DETENIDO** por política.
- **Herramienta sin nivel ⇒ no ejecutar.** Un `null` en la columna es un dato que
  falta, no un permiso.
- **Autorización vencida ⇒ no ejecutar, y no renovar sola.** Una autorización que
  se renueva sola no es una autorización: es un permiso permanente con un campo
  de fecha decorativo.

---

## 9. Autoridad

**[DISEÑO]** Quién puede qué:

| Acción de gobierno | Quién |
|---|---|
| Cambiar `nivel_autonomia` de una organización | **ADMIN**, con motivo obligatorio y auditado |
| Autorizar una herramienta | **ADMIN**, una por una, con vigencia |
| Revocar la autorización de una herramienta | **ADMIN**; y **cualquier rol de gestión** debería poder revocar en emergencia |
| **Activar** el kill switch (permitir) | **ADMIN** |
| **Detener** el kill switch | **cualquier rol de gestión** — detener es la dirección segura |
| Modificar condiciones de una herramienta | **ADMIN** |
| Aprobar una acción nivel 4 | **ADMIN o Jefe de Operaciones**, por ocurrencia |

**[DISEÑO]** La asimetría es deliberada: **parar debe ser más fácil que
arrancar.** Exigir el mismo rol para detener que para activar significa que en
una emergencia la única persona que puede frenar puede estar durmiendo.

**[MEDIDO]** `interruptor.py` ya tiene la función de detener separada de la de
activar (`_mover` a `DETENIDO` / a `ACTIVO`), así que la asimetría es
expresable sin rediseñar nada.

### Lo que la IA nunca puede hacer

| Prohibido | Garantía hoy |
|---|---|
| Elevar su propio nivel | **[MEDIDO]** ninguna herramienta escribe `interruptor_autonomia`; `nivel_autonomia_requerido` no está en `CAMPOS_MODIFICABLES` |
| Autorizarse | **[MEDIDO]** `ContextVar` privado; `_Permiso` lo construye **solo** `frontera`. No hay `autorizado=True` que un llamador pueda pasar |
| Modificar el kill switch | **[MEDIDO]** `autonomia_operador` es `NOLOGIN NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; `autonomia_detener` solo **detiene** |
| Modificar permisos | **[MEDIDO]** `supervisor.py` no toca `Profile` — es una **ausencia de código**, no una regla escrita |
| Modificar tenant | **[MEDIDO]** se exige y se compara |
| Modificar sus condiciones de ejecución | **[DISEÑO]** el registro de autorización debe ser inescribible desde cualquier ruta del motor |

**[DISEÑO]** La autorización por herramienta debería vivir **donde la IA no
escribe**. Ponerla dentro de `tenant_config` —que un editor de agentes ya
modifica— sería darle a la configuración del asistente la capacidad de ampliar
sus propios permisos.

**[PENDIENTE]** Dónde vive exactamente: tabla propia en `asistente`, con grants
que excluyan al rol del motor. Requiere decisión.

---

## 10. Auditoría — dos registros, no uno

**[DISEÑO]** La auditoría de **propuesta** y la de **ejecución** responden
preguntas distintas y deben separarse: una propuesta puede no ejecutarse nunca, y
una ejecución puede no venir de ninguna propuesta (una acción humana directa).
Mezclarlas obliga a dejar media tabla vacía en los dos casos.

### Auditoría de PROPUESTA — **[MEDIDO]** ya existe

`common.Activity` + `PropuestaSupervisor`: organización, actor, propuesta,
evidencia, decisión, estado anterior/nuevo, motivo, timestamp. Validada en M09-F.

### Auditoría de EJECUCIÓN — **[DISEÑO]**

| Campo | ¿Existe hoy? |
|---|---|
| organización | **[MEDIDO]** ✔ |
| herramienta | **[MEDIDO]** ✔ `tool_calls` |
| **nivel solicitado** | **falta** |
| **nivel autorizado** | **falta** |
| actor | **[MEDIDO]** ✔ |
| **tipo de actor** (persona / servicio / motor) | **falta** — ver 1.3 |
| propuesta de origen | **[MEDIDO]** ✔ `accion_propuesta_ref` (vacío hoy) |
| evidencia | **[MEDIDO]** ✔ |
| decisión humana previa | **[MEDIDO]** ✔ |
| **autorización aplicada** (cuál regla permitió) | **falta** |
| estado del kill switch al ejecutar | **falta** |
| idempotency key | **[MEDIDO]** ✔ |
| resultado | **[MEDIDO]** ✔ |
| timestamp | **[MEDIDO]** ✔ |
| **motivo de rechazo** (cuál condición falló) | **falta** |
| error | **[MEDIDO]** ✔ `codigo_error` |
| **recurso afectado** (qué cliente, qué ticket) | **falta** |

**[DISEÑO]** Seis campos nuevos. **No hace falta un registro nuevo**: cabe en lo
que ya existe. Un cuarto registro solo agregaría un lugar más donde buscar.

**[RIESGO]** `recurso afectado` tiene que guardar **un identificador, nunca el
dato**. Las respuestas crudas de WispHub no se persisten: traen contraseñas, GPS
y cédula. Un campo "recurso afectado" mal diseñado sería la puerta por la que
eso entre a una tabla de auditoría.

---

## 11. Relación con los módulos

**[DISEÑO]** Sin crear módulos nuevos.

| Módulo | Rol en el modelo de autonomía |
|---|---|
| **M02** Actividades | **dueño** del efecto sobre actividades, compromisos y dependencias. **[DEPENDENCIA]** sin datos reales, nada autónomo aquí |
| **M03** Programación | **dueño** de programar, asignar y reasignar. **[DEPENDENCIA]** `operaciones_disponibilidad` = 0 filas |
| **M09** Supervisor | **recomienda. Dueño de ningún efecto.** Propone que M03 reasigne; **no reasigna** |
| **M10** Seguridad | **quién puede autorizar y auditar**; RLS y aislamiento. **[DEPENDENCIA]** bloquea toda autonomía sobre `campo_*` |
| **M11** Métricas | consume la auditoría de ejecución. **[DEPENDENCIA]** de los seis campos del §10 |

**[DISEÑO]** Regla de gobierno:

> **La acción autónoma se ejecuta en el módulo dueño del efecto, no en M09.**
> M09 no debe crecer hasta ser el lugar donde pasa todo — es el error que M09-G
> nombró y este documento no debe deshacer.

---

## 12. Hallazgos M10 — abiertos

**[MEDIDO]** Ninguno resuelto. Ninguno se declara resuelto.

| # | Hallazgo | Estado |
|---|---|---|
| 1 | **7 tablas `campo_*` sin RLS ni políticas** | **abierto** |
| 2 | **69 de 135 tablas `public` sin política** | **abierto** |
| 3 | Aislamiento de las OT depende **del ORM** | **abierto** |
| 4 | Defecto B.4 (`test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay`) | **abierto** |
| 5 | Ejecutor del motor no instrumentado en el contenedor de M09-E | **abierto** |
| 6 | **20 de 27 escrituras sin `aprobacion_humana` ni `exige_previas`** | **nuevo en M09-H** |

**[DEPENDENCIA]** El hallazgo 1 bloquea, por sí solo, cualquier autonomía que
escriba sobre órdenes de trabajo: una acción autónoma es precisamente el caso
donde no hay una persona comprobando que el filtro del ORM se aplicó.

---

## 13. Matriz final

Nivel = **[DISEÑO]** nivel propuesto · Aprob = aprobación humana por ocurrencia
Estado actual = **[MEDIDO]** · Todas: kill switch ✔, auditoría ✔, tenant obligatorio

| Sistema | Herramienta | Efecto | I/E | Rev | Nivel | Aprob | Evidencia | Idem | Estado actual | Candidato | Condiciones |
|---|---|---|:--:|:--:|:--:|:--:|:--:|:--:|---|---|---|
| WispHub | `registrar_pago` | financiero | E | no | **4** | **sí** | completa | exige | `aprobacion_humana`=no | **no** | ninguna |
| WispHub | `agregar_promesa_pago` | financiero | E | parc | **4** | **sí** | completa | exige | `aprobacion_humana`=**sí** | **no** | ninguna |
| interna | `reportar_comprobante_pago` | financiero | I | sí | **4** | **sí** | completa | exige | sin gate propio | **no** | alimenta cobranza |
| WispHub | `cerrar_ticket_operativo` | dato | E | no | **4** | **sí** | completa | exige | sin gate propio | **no** | cierre definitivo |
| WispHub | `completar_ticket_instalacion` | dato | E | no | **4** | **sí** | completa | exige | sin gate propio | **no** | cierre definitivo |
| CRM | `cerrar_caso_crm` | dato | E | no | **4** | **sí** | completa | exige | sin gate propio | **no** | cierre definitivo |
| CRM | `cancelar_solicitud_servicio` | dato | E | no | **4** | **sí** | completa | exige | sin gate propio | **no** | cancelación |
| WispHub | `responder_ticket` | comunicación | E | no | **4** | **sí** | completa | exige | `aprobacion_humana`=**sí** | **no** | lo lee el cliente |
| WispHub | `responder_ticket_operativo` | comunicación | E | no | **4** | **sí** | completa | exige | sin gate propio | **no** | lo lee el cliente |
| WhatsApp | envío **proactivo** | comunicación | E | no | **4** | **sí** | completa | exige | **no existe** | **no** | §7 |
| SmartOLT | `cambiar_tipo_onu` | infraestructura | E | no | **4** | **sí** | completa | exige | `exige_previas` | **no** | red crítica |
| SmartOLT | `activar_catv` | infraestructura | E | parc | **4** | **sí** | completa | exige | `exige_previas` | **no** | servicio facturable |
| SmartOLT | `reiniciar_ont` | infraestructura | E | sí | **4** | **sí** | completa | exige | `exige_previas` | **no** hoy | solo con confirmación del cliente |
| WispHub | `actualizar_estado_ticket` | dato | E | sí | **3** | no | propuesta+args | exige | `aprobacion_humana`=**sí** | condicional | nivel + origen + rollback |
| WispHub | `reasignar_ticket_instalacion` | dato | E | sí | **3** | no | propuesta+args | exige | sin gate propio | condicional | ídem + M03 |
| WispHub | `crear_ticket` | dato | E | parc | **3** | no | propuesta+args | **exige** | `aprobacion_humana`=**sí** | condicional | origen estable |
| WispHub | `crear_ticket_caso` | dato | E | parc | **3** | no | propuesta+args | **exige** | sin gate propio | condicional | origen estable |
| WispHub | `crear_ticket_instalacion` | dato | E | parc | **3** | no | propuesta+args | **exige** | sin gate propio | condicional | origen + M03 |
| WispHub | `agendar_visita_tecnica` | dato | E | parc | **3** | no | propuesta+args | **exige** | sin gate propio | condicional | origen + M03 |
| WispHub | `agendar_visita_internet` | dato | E | parc | **3** | no | propuesta+args | **exige** | sin gate propio | condicional | origen + M03 |
| CRM | `registrar_solicitud_servicio` | dato | I | parc | **3** | no | propuesta+args | exige | sin gate propio | condicional | decisión comercial |
| CRM | `importar_caso_externo` | dato | I | sí | **2** | no | propuesta | exige | sin gate propio | condicional | origen estable |
| CRM | `sincronizar_respuestas_externas` | dato | I | sí | **2** | no | propuesta | exige | sin gate propio | condicional | origen estable |
| CRM | `crear_caso_soporte` | dato | I | parc | **2** | no | propuesta | exige | sin gate propio | condicional | origen estable |
| interna | `registrar_pedido_wifi` | dato | I | sí | **2** | no | propuesta | no exige | sin gate propio | condicional | ninguna técnica |
| CRM | `reconciliar_caso_externo` | dato | I | parc | **2** | no | propuesta | exige | sin gate propio | futura | regla versionada |
| CRM | `crear_tag_crm` | dato | I | sí | **2** | no | propuesta | no exige | sin gate propio | futura | decisión de producto |
| interna | `proponer_herramienta` | dato | I | sí | **2** | no | propuesta | no exige | sin gate propio | futura | el borrador sigue exigiendo aprobación |
| varios | **las 42 de solo lectura** | consulta | I | n/a | **0–1** | no | n/a | n/a | **en uso** | ya son 0/1 | — |

**No se recomienda automatizar ninguna herramienta.** La columna "candidato"
repite la clasificación de M09-G; no es un orden de mérito ni una sugerencia.

---

## 14. Resultado

### 14.1 — Resumen ejecutivo

El modelo de autonomía granular **se puede diseñar sobre lo que ya existe**: seis
de los ocho pasos de la frontera están construidos y probados, la auditoría no
necesita un registro nuevo, y el punto físico donde poner el control ya fue
encontrado y validado en el paso 10.14.

Lo que falta es **una capa de autorización por (organización, herramienta)** y
**un techo de nivel por organización** — más seis campos de auditoría.

Tres hallazgos de este paso cambian cómo hay que diseñarlo:

1. **`requiere_confirmacion` no es una compuerta de ejecución.** Es una invariante
   de configuración. La compuerta real es `aprobacion_humana`, y la declaran
   **4 de 27** escrituras. **20 de 27 no tienen ninguna red propia** más allá del
   kill switch.
2. **Solo hay dos caminos de escritura saliente** en todo el núcleo: `http.py`
   (con frontera) y `whatsapp.py` (sin ella, reactivo). Los otros cinco módulos
   con HTTP son de solo lectura. La superficie a proteger es más chica de lo que
   parecía — **y el riesgo real es el transporte que todavía no existe**.
3. **El actor tiene dos representaciones incompatibles** — FK a `Profile` en el
   CRM, `str` libre en el motor. Por eso la auditoría de ejecución necesita
   `actor` **y** `tipo de actor`.

Y la regla de diseño que atraviesa todo: **el nivel es un techo, no una llave.**
Una organización en nivel 3 con cero herramientas autorizadas ejecuta cero
herramientas, y ese debe ser el estado inicial de toda organización.

### 14.2 — Decisiones que requieren aprobación

| # | Decisión | Por qué no la toma este documento |
|---|---|---|
| P-1 | **Dónde vive la autorización por herramienta** | Debe ser inescribible desde el motor. Ponerla en `tenant_config` le daría al editor de agentes la capacidad de ampliar sus propios permisos |
| P-2 | ¿La revocación de emergencia la puede hacer cualquier rol de gestión? | Es política, no técnica. La propuesta es sí — parar debe ser más fácil que arrancar |
| P-3 | ¿Las autorizaciones vencen? ¿Cada cuánto? | Sin vigencia, una autorización de prueba queda viva para siempre |
| P-4 | ¿`aprobacion_humana` debe volverse obligatoria en las 20 que no la tienen? | Cambiaría el comportamiento de herramientas en uso hoy |
| P-5 | ¿El envío proactivo de WhatsApp exige plantilla aprobada por Meta? | Restricción del proveedor: hay que **verificarla**, no asumirla |
| P-6 | ¿Qué organización, si alguna, sería la primera con nivel > 1? | Fuera del alcance: M09-G ya dijo que no se empieza eligiendo una herramienta |

### 14.3 — Riesgos abiertos

| # | Riesgo |
|---|---|
| R-1 | **[MEDIDO]** 20 de 27 escrituras sin compuerta de aprobación propia |
| R-2 | **[MEDIDO]** 7 tablas `campo_*` sin RLS — bloquea autonomía sobre OT |
| R-3 | **[MEDIDO]** 69 de 135 tablas `public` sin política |
| R-4 | **[MEDIDO]** El camino saliente de WhatsApp no consulta el kill switch |
| R-5 | **[RIESGO]** Un transporte nuevo nace sin frontera |
| R-6 | **[RIESGO]** Confundir `nivel` (identidad) con `nivel_autonomia` |
| R-7 | **[RIESGO]** Tratar el nivel como llave y no como techo |
| R-8 | **[MEDIDO]** M02/M03 sin datos reales: autonomía a ciegas |
| R-9 | **[MEDIDO]** Sin origen estable, la idempotencia solo cubre el turno |
| R-10 | **[MEDIDO]** Timeout sin respuesta: nadie sabe si el tercero aplicó |
| R-11 | **[MEDIDO]** Defecto B.4 abierto |
| R-12 | **[MEDIDO]** Ejecutor del motor sin instrumentar |

### 14.4 — Qué debería construirse después (sin implementarlo)

En este orden, y el orden importa:

| # | Qué | Por qué va aquí |
|---|---|---|
| 1 | **Guarda de arquitectura**: falla si aparece un `requests.post/put/patch/delete` fuera de los puntos declarados | Es lo único barato de la lista y protege todo lo demás. No necesita ninguna decisión pendiente |
| 2 | **Los seis campos de auditoría de ejecución** | Sin ellos no se puede medir nada de lo que venga después. Aditivo, sin cambio de comportamiento |
| 3 | **Registro de autorización (org, herramienta)** | Requiere **P-1** |
| 4 | **`nivel_autonomia` por organización**, con default 0 y fail-closed | Requiere 3: un techo sin puertas no sirve |
| 5 | **Evaluación de la conjunción del §3 en `http.py::ejecutar`** | Requiere 3 y 4 |
| 6 | **Función separada de envío proactivo de WhatsApp** | Requiere **P-5** |
| 7 | **RLS de `campo_*`** (M10) | Bloquea toda autonomía sobre OT |

**Los pasos 1 y 2 no dependen de ninguna decisión pendiente** y no cambian el
comportamiento de nada: son aditivos y medibles. Los pasos 3 a 6 están
bloqueados por decisiones humanas, no por dificultad técnica.

**Nada de esto está construido. Este documento no autoriza a construirlo.**

---

### Anexo — qué se midió en este paso

| Medición | Resultado |
|---|---|
| `grep requiere_confirmacion --include=*.py nucleo/` | validado en `schema.py:1505`; `motor.py:34` dice que **no se aplica** en ejecución |
| `aprobacion_humana` en producción (v146) | **4 de 27** |
| `exige_previas` en producción | **3 de 27** |
| Escrituras sin ninguna de las dos | **20 de 27** |
| Módulos del núcleo con HTTP saliente | **7** |
| De ellos, capaces de escribir | **2** (`http.py` con frontera, `whatsapp.py` sin ella) |
| Los otros 5 | solo GET |
| `nivel` preexistente en el núcleo | `verificacion.py` — **identidad**, no autonomía |
| Representaciones de actor | **2**, incompatibles |

Producción al cerrar el paso, sin cambios respecto de M09-F y M09-G:

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
40 acciones_propuestas · operaciones_externas 0 · 192 django_migrations
tenant_config v146 · {ADMIN: 1, USER: 4}
```
