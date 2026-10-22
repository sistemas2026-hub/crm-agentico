# PASO M09-G — Catálogo y frontera de autonomía

**Fecha:** 2026-09-17
**Naturaleza:** documento de **diseño y gobierno**. No se ejecutó ninguna acción,
no se llamó a WispHub ni a SmartOLT, no se tocó el kill switch, no se modificó
producción, no se creó ninguna migración.
**Lo único que se hizo contra producción fueron lecturas** (`read_only=True`)
para que el catálogo salga de medir el sistema y no de recordarlo.

---

## 1. Qué es una acción

Once conceptos que este proyecto venía usando como sinónimos en conversación y
que aquí quedan separados, porque la clasificación de autonomía depende de la
distinción.

| Concepto | Definición operativa | Dónde vive hoy |
|---|---|---|
| **Señal** | Un hecho observado y normalizado. Todavía no afirma qué hacer. | `supervisor.Senal` |
| **Recomendación** | Una señal analizada + una acción propuesta + evidencia + prioridad. **No es una acción.** | `PropuestaSupervisor` |
| **Decisión humana** | Un humano con rol de gestión dice aceptar / modificar / rechazar. **Tampoco es una acción.** | `supervisor.revisar` |
| **Acción** | Una operación que cambia el estado de algún sistema. | `Herramienta` con `solo_lectura: false` |
| **Efecto interno** | El cambio queda dentro de la base del CRM/asistente. Nadie fuera lo ve. | tablas `public.*`, `asistente.*` |
| **Efecto externo** | El cambio sale de nuestra frontera: otro sistema, o una persona, lo recibe. | WispHub, SmartOLT, WhatsApp |
| **Cambio reversible** | Existe una operación que restituye el estado anterior **y** deja rastro de las dos. | ej. reasignar un ticket |
| **Cambio irreversible** | No existe esa operación, o el efecto ya lo percibió un tercero. | ej. enviar un mensaje, registrar un pago |
| **Comunicación** | El destinatario es una persona. Lo irreversible no es el registro: es que ya lo leyó. | `whatsapp.enviar_*`, `responder_ticket` |
| **Modificación de datos** | Cambia un registro de negocio. | casos, tickets, órdenes |
| **Modificación de infraestructura** | Cambia el comportamiento de un equipo o de la red. | SmartOLT |

> **Una propuesta NO es una acción ejecutada.** Está garantizado en código, no
> prometido: `ejecutada` no existe entre los estados de `PropuestaSupervisor`, y
> `supervisor.ejecutar_propuesta` levanta `EjecucionNoPermitida` siempre.

---

## 2. Catálogo de acciones actuales

### 2.1 — Inventario medido

Fuente: `asistente.tenant_config` **de producción** (`rapilink`, `config_version`
**146**), no el YAML semilla. Coinciden exactamente.

```
herramientas declaradas       : 69
de solo lectura               : 42
de ESCRITURA                  : 27
con requiere_confirmacion     : 27 / 27   (el 100% de las escrituras)
tenants con config            : 1 (rapilink)
```

Por sistema destino:

| Sistema | Herramientas | De escritura |
|---|---:|---:|
| WispHub (`api.wisphub.io`) | 32 | **13** |
| SmartOLT (`SMARTOLT_SUBDOMINIO`) | 11 | **3** |
| CRM propio (`backend:8000`) | 13 | **8** |
| Internas del motor | 12 | **3** |
| Sin base declarada | 1 | 0 |

### 2.2 — Las 27 acciones de escritura

Reversible = existe una operación que restituye el estado anterior.
Idemp. = la clave de `asistente.operaciones_externas` protege el reintento
(`origen|herramienta|hash(argumentos resueltos)`), y vale **lo que valga el
`origen`**: sin un origen estable solo protege el reintento dentro del turno.

| # | Acción | Sistema | Efecto | Revers. | Impacto |
|---|---|---|---|:--:|---|
| 1 | `reiniciar_ont` | SmartOLT | reinicia el equipo del cliente | sí | corta el servicio ~1–2 min |
| 2 | `cambiar_tipo_onu` | SmartOLT | cambia el aprovisionamiento de la ONU | **no** | puede dejar al cliente sin servicio |
| 3 | `activar_catv` | SmartOLT | habilita el puerto de TV | parcial | habilita un servicio facturable |
| 4 | `crear_ticket` | WispHub | crea un ticket | parcial | genera trabajo real |
| 5 | `crear_ticket_caso` | WispHub | ídem, desde un caso | parcial | ídem |
| 6 | `crear_ticket_instalacion` | WispHub | ticket de instalación | parcial | compromete una cuadrilla |
| 7 | `agendar_visita_tecnica` | WispHub | ticket con fecha | parcial | compromete una cuadrilla |
| 8 | `agendar_visita_internet` | WispHub | ídem | parcial | ídem |
| 9 | `responder_ticket` | WispHub | **texto que lee el cliente** | **no** | comunicación |
| 10 | `responder_ticket_operativo` | WispHub | ídem | **no** | comunicación |
| 11 | `cerrar_ticket_operativo` | WispHub | **cierra** el ticket | **no** | cierre definitivo |
| 12 | `completar_ticket_instalacion` | WispHub | marca completada | **no** | cierre definitivo |
| 13 | `actualizar_estado_ticket` | WispHub | cambia el estado | sí | coordinación |
| 14 | `reasignar_ticket_instalacion` | WispHub | cambia el técnico | sí | coordinación |
| 15 | `registrar_pago` | WispHub | **asienta un pago** | **no** | **facturación** |
| 16 | `agregar_promesa_pago` | WispHub | compromiso financiero | parcial | **facturación** |
| 17 | `cerrar_caso_crm` | CRM | **cierra** el caso | **no** | cierre definitivo |
| 18 | `cancelar_solicitud_servicio` | CRM | **cancela** la solicitud | **no** | cancelación |
| 19 | `crear_caso_soporte` | CRM | crea un caso | parcial | registro interno |
| 20 | `registrar_solicitud_servicio` | CRM | crea una solicitud | parcial | inicia un proceso comercial |
| 21 | `crear_tag_crm` | CRM | crea una etiqueta | sí | catálogo interno |
| 22 | `importar_caso_externo` | CRM | trae un caso externo | sí | ingesta |
| 23 | `reconciliar_caso_externo` | CRM | concilia duplicados | parcial | ingesta |
| 24 | `sincronizar_respuestas_externas` | CRM | trae respuestas | sí | ingesta |
| 25 | `registrar_pedido_wifi` | interna | registra un pedido | sí | registro interno |
| 26 | `reportar_comprobante_pago` | interna | registra un reporte | sí | registro interno, **toca cobranza** |
| 27 | `proponer_herramienta` | interna | guarda un borrador | sí | catálogo del asistente |

**Datos comunes a las 27**, medidos y no supuestos:

- **Tenant:** obligatorio. Sin tenant válido la frontera levanta `ACCION_EXTERNA_SIN_TENANT` — *"sin control" no es autorización*.
- **Frontera externa:** las 27 pasan. La frontera decide por `solo_lectura`, **no por `tipo`**, así que las tres internas también quedan cubiertas.
- **Kill switch:** las 27. `interruptor.es_accion_autonoma` usa el mismo campo que `frontera.escribe`, para que las dos capas no puedan discrepar.
- **Autorización actual:** `requiere_confirmacion: true` en las 27. Ninguna se ejecuta sin una puerta humana o un permiso explícito.
- **Auditoría:** `tool_calls` (metadatos, nunca la respuesta cruda) + `asistente.operaciones_externas`.
- **Idempotencia:** disponible para todas; su fuerza depende del `origen`.

### 2.3 — Acciones que NO son herramientas

El catálogo de `Herramienta` no agota lo que el sistema puede hacer. Tres
familias más, y la primera es un hallazgo de este paso.

#### 2.3.1 — Comunicaciones WhatsApp: **fuera de la frontera**

```
nucleo/canales/whatsapp.py: enviar_texto, enviar_media,
                            enviar_plantilla, enviar_plantilla_aprobada
menciones de interruptor / frontera / kill switch en ese archivo:  0
```

**El camino de salida de WhatsApp no consulta el kill switch.** Se midió, no se
dedujo.

Ahora la otra mitad, que es la que impide llamarlo "bypass": se revisaron los
**nueve** puntos de llamada, y todos son **reactivos** —

- responder a un mensaje que el cliente acaba de enviar (`api.py:5424`, `5445`),
- la respuesta de alta/baja del canal (`5340`, `5345`),
- un operador apretando enviar en el CRM (`4018`, `4192`, `5696`, `5892`).

Ninguno es el motor decidiendo escribirle a alguien por su cuenta. Y el proyecto
tiene una decisión explícita y medida de que el canal **siga contestando** aun
con la conversación escalada (CLAUDE.md, 12/09/2026).

**La conclusión correcta no es "está cubierto" sino:**

> El canal de salida es hoy un **contrato de respuesta**, no una acción autónoma,
> y por eso vive fuera de la frontera. En el momento en que exista un camino
> donde la IA **inicie** un mensaje —una notificación proactiva, un seguimiento,
> un recordatorio— ese camino **atravesaría el kill switch sin verlo**. Es un
> control que falta (§17.E), no un defecto activo.

#### 2.3.2 — El programador: cerrado y vacío

```
asistente.job_schedule_state: 0 filas
```

El registro `job_code → función` es un diccionario literal congelado al importar:
sin `importlib`, sin registro dinámico, sin nombre de módulo que venga de afuera.
**Hoy no hay ningún trabajo registrado.** Si alguien agregara `cerrar_vencidas`
al catálogo de producción, el coordinador lo vería, no lo encontraría, y lo
contaría como omitido con motivo — *no hay forma de encenderlo por
configuración*. `cerrar_vencidas` además está bloqueado por no ser idempotente.

#### 2.3.3 — Operaciones humanas del CRM

Rutas que ya existen y que **opera una persona** (§8): crear / asignar / validar
/ completar una orden de trabajo, subir evidencias, decidir una solicitud,
revisar propuestas M09. Ninguna es candidata a nada en este paso: son la puerta
humana, y deben seguir funcionando exactamente igual.

---

## 3. Clasificación por autonomía — y la infraestructura que no existe

| Nivel | Nombre | Significa |
|:--:|---|---|
| **0** | Observar | Detecta y registra. No propone acción. |
| **1** | Recomendar | Propone una acción y prepara el contexto. **No la ejecuta.** |
| **2** | Coordinación controlada | Ejecuta efectos **internos** y reversibles, sin salir al exterior. |
| **3** | Ejecución reversible autorizada | Ejecuta efectos **externos** reversibles, con autorización vigente. |
| **4** | Acción crítica | Nunca sola. Aprobación humana explícita, siempre. |

### El hallazgo estructural de este paso

> **Los niveles 0–4 no existen en el motor.** Existen únicamente como `choices`
> de un campo del CRM (`PropuestaSupervisor.NIVELES`), es decir como una
> **etiqueta descriptiva de lo que una propuesta habría requerido** — no como un
> mecanismo que autorice o impida nada.

Medido:

```
grep NIVEL_COORDINAR / NIVEL_EJECUTAR_REVERSIBLE / NIVEL_CRITICO
  -> solo django-crm/backend/operaciones/models.py

nucleo/seguridad/interruptor.py:  ESTADOS = (ACTIVO, DETENIDO)
nucleo/seguridad/frontera.py:30:  "no implementa niveles: el modelo sigue
                                   siendo binario, DETENIDO / ACTIVO"
```

**Consecuencia concreta y no negociable:** hoy **no hay forma de activar nivel 2
sin activar también el 3 y el 4**. El interruptor es por tenant y es
todo-o-nada. Cualquier etapa de autonomía por niveles exige construir esa
granularidad primero (§17.D).

---

## 4. Qué significa NIVEL 1 en Rapilink

Definición inequívoca, y se escribe en negativo primero porque es donde está el
malentendido caro:

> **Nivel 1 NO incluye ejecutar. Ni una acción reversible, ni una interna, ni
> una "pequeña". Cero ejecución.**

**Nivel 1 en Rapilink es:**

> La IA detecta una condición, la analiza, **propone una acción concreta**,
> adjunta la **evidencia que la sostiene** —con fuente, identificador, dato y
> hora de lectura—, explica **por qué** y **cómo se calculó su prioridad**, y
> **deja todo preparado para que una persona decida**. La persona decide. El
> sistema registra la decisión. **Nada sale de la frontera.**

Tres propiedades que hacen la definición comprobable, no declarativa:

1. **La evidencia es obligatoria** — `CheckConstraint propuesta_exige_evidencia`.
2. **El único camino declarado a la ejecución levanta** — `ejecutar_propuesta`.
3. **`ejecutada` no es un estado posible** del modelo.

Es exactamente lo que M09-D implementó y M09-E/M09-F validaron. **Rapilink ya
está en nivel 1.** Este documento no lo cambia.

---

## 5. Candidatas a autonomía futura

Tres categorías, sin ranking, sin score, sin "mejor/peor". La categoría describe
**qué condiciones faltan**, no cuánto vale la acción.

### 5.1 — NO CANDIDATA (16 acciones)

Ver §6: cada una con su justificación por efecto.

### 5.2 — CANDIDATA CONDICIONAL (8 acciones)

Efecto acotado y reversible o repetible, pero **con condiciones que hoy no se
cumplen**.

| Acción | Por qué es candidata | Condiciones que faltan |
|---|---|---|
| `actualizar_estado_ticket` | cambio de estado, reversible, sin comunicación al cliente | granularidad de nivel; origen estable; rollback probado |
| `reasignar_ticket_instalacion` | reversible; el efecto es coordinación interna | ídem + M03 con datos reales de disponibilidad |
| `crear_ticket`, `crear_ticket_caso` | aditivo; un ticket de más es visible y corregible | origen estable (hoy 34 de los 36 pendientes son de esta herramienta) |
| `crear_ticket_instalacion` | aditivo | ídem + M03 |
| `importar_caso_externo` | ingesta, idempotente por diseño | origen estable |
| `sincronizar_respuestas_externas` | ingesta, repetible | ídem |
| `crear_caso_soporte` | registro interno, aditivo | ídem |

Para cada una, los diez puntos que el §5 exige:

- **Reversibilidad** — parcial: se corrige creando/cambiando, no deshaciendo. Nadie borra un ticket.
- **Evidencia** — la misma que ya exige `PropuestaSupervisor`, más los argumentos **resueltos** que se enviarían.
- **Autorización** — hoy `requiere_confirmacion: true`. Para autonomía haría falta una autorización *por herramienta y por nivel*, que no existe.
- **Idempotencia** — disponible; **su fuerza depende del `origen`**, y hoy el origen estable solo existe en tres caminos (wamid, `run_id`, `Idempotency-Key`).
- **Auditoría** — `tool_calls` + `operaciones_externas`. No hay que construir nada.
- **Kill switch** — cubre las ocho. Binario.
- **Tenant** — obligatorio y fail-closed.
- **Rollback** — **ninguna tiene rollback automático probado.** Es la condición que más falta.
- **Riesgos** — duplicación si el origen no es estable; trabajo real generado a una cuadrilla.
- **Condición transversal** — M02/M03 siguen **sin datos reales** (M09-E). Sin eso, cualquier autonomía sobre programación opera a ciegas.

### 5.3 — CANDIDATA FUTURA (3 acciones)

Efecto interno, reversible, sin tercero que lo perciba.

| Acción | Por qué | Condiciones |
|---|---|---|
| `crear_tag_crm` | catálogo interno; una etiqueta de más se borra | ninguna técnica; falta la decisión de producto |
| `reconciliar_caso_externo` | concilia duplicados internos | necesita regla de conciliación versionada |
| `proponer_herramienta` | guarda un **borrador**, no lo activa | ninguna técnica |

`proponer_herramienta` merece una nota: **guarda un borrador que un humano tiene
que aprobar**. Eso la vuelve estructuralmente distinta — su "efecto" es crear
otra propuesta. No es una puerta para que la IA amplíe su propio catálogo: sería
exactamente lo que el §10 prohíbe, y la aprobación humana es lo que lo impide.

---

## 6. Acciones que NUNCA deben ser autónomas

Justificadas **por el efecto**, no por la categoría.

| Acción | Por qué nunca |
|---|---|
| `registrar_pago` | **Facturación.** Asienta dinero. Un asiento equivocado es una disputa con el cliente y un descuadre contable; no hay "deshacer" que reponga la confianza |
| `agregar_promesa_pago` | **Facturación.** Compromete a la empresa frente al cliente en una fecha |
| `reportar_comprobante_pago` | interna, pero alimenta cobranza: un reporte falso suspende o no suspende a alguien |
| `cerrar_ticket_operativo` | **Cierre definitivo.** Cerrar lo que no se resolvió hace desaparecer el problema del tablero sin resolverlo. `ACCION_CONFIRMADA` ≠ el cliente tiene internet |
| `completar_ticket_instalacion` | **Cierre definitivo** de un trabajo que alguien debía verificar en sitio |
| `cerrar_caso_crm` | **Cierre definitivo** |
| `cancelar_solicitud_servicio` | **Cancelación.** Cancela un proceso comercial de una persona |
| `responder_ticket`, `responder_ticket_operativo` | **Comunicación.** Lo irreversible no es la fila: es que el cliente ya lo leyó |
| `whatsapp.enviar_*` (proactivo) | **Comunicación**, ídem. El camino reactivo es otra cosa (§2.3.1) |
| `cambiar_tipo_onu` | **Infraestructura crítica.** Reaprovisionar mal deja al cliente sin servicio, y la corrección exige intervención |
| `activar_catv` | habilita un **servicio facturable**: es una decisión comercial disfrazada de cambio técnico |
| `reiniciar_ont` | **corta el servicio** ~1–2 min. Que sea reversible no lo vuelve inocuo: el cliente lo percibe, y si estaba en una llamada, lo perdió |
| Eliminación de datos | no existe ninguna herramienta que borre — **y no debe existir**. WispHub sí permite borrar un cliente con nuestra misma clave; la protección es que ninguna herramienta lo declare |
| Cambios de permisos / roles | la IA no toca `Profile` |
| Cambios de tenant | cruzar tenants es la falla más grave posible en un SaaS multi-tenant |
| Credenciales | ningún camino las escribe |
| Kill switch | §10 |
| Sanciones | no existen como concepto en este sistema, y no deben introducirse por la puerta de la autonomía |

**Sobre `reiniciar_ont`**, que es la tentación obvia: es la más reversible y la
mejor verificada del catálogo (`last_status_change`, un sello discreto, medido
dos veces). Aun así queda aquí — **puede reclasificarse a CANDIDATA CONDICIONAL
si y solo si** existe confirmación explícita del cliente en la conversación
antes de cada reinicio. Sin esa confirmación, la IA le corta el servicio a
alguien que no lo pidió.

---

## 7. Efecto interno vs efecto externo

| Efecto INTERNO | Efecto EXTERNO |
|---|---|
| crear una `PropuestaSupervisor` | crear/modificar un ticket en WispHub |
| crear una `ActividadOperativa` | enviar un WhatsApp |
| **recomendar** una programación | **modificar** la programación real |
| registrar una decisión humana | responder un ticket que el cliente lee |
| escribir auditoría | reiniciar una ONU |
| calcular una prioridad | registrar un pago |

**La línea:** un efecto es externo cuando **alguien fuera de nuestra base lo
percibe** — otro sistema o una persona. No es "sale por HTTP": `crear_caso_soporte`
sale por HTTP hacia nuestro propio backend y es **interno**; `whatsapp.enviar_texto`
es externo aunque el registro quede en nuestra base.

Todo lo que M09 hace hoy está en la columna izquierda. **Las 52 propuestas de la
réplica de M09-E produjeron 0 llamadas externas**, contadas con un espía que
levanta.

---

## 8. Operaciones humanas existentes

Deben seguir funcionando **sin cambio alguno**, activa o no la autonomía.

| Operación | Dónde | Quién |
|---|---|---|
| Crear / asignar / validar / completar una orden | `campo/urls.py` | despacho y técnicos |
| Subir y confirmar evidencias | `campo/urls.py` | técnicos |
| Decidir una solicitud de servicio | `solicitudes/urls.py` | comercial |
| Revisar propuestas M09 | `operaciones/urls.py` | Jefe de Operaciones |
| Responder por WhatsApp desde el CRM | `canales/api.py` | agentes |
| Aprobar `asistente.acciones_propuestas` | motor | autorizado |

**Puerta humana ≠ puerta autónoma.** Ya están separadas en el código: la
frontera tiene dos entradas distintas —`frontera.humana(...)`, que exige actor y
evidencia, y `frontera.autonoma(...)`, que consulta el interruptor. Una acción
humana **no** debe quedar bloqueada porque el kill switch esté detenido: el kill
switch existe para frenar a la IA, no para frenar a la empresa.

> Dato histórico que lo ilustra: de las 40 filas de `asistente.acciones_propuestas`,
> **4 están aprobadas y las 4 tienen `resultado_ejecucion`** — se ejecutaron por
> la puerta humana. Las **36 pendientes** (34 `crear_ticket`, 2
> `agregar_promesa_pago`, la más vieja del **19/08/2026**) son la demostración de
> a dónde lleva una cola sin revisar, y el motivo por el que M09 tiene expiración.

---

## 9. Frontera de autonomía futura (conceptual)

**No se implementó nada.** Esto describe la secuencia que una acción autónoma
debería atravesar, y **seis de los ocho pasos ya existen**.

```
  SOLICITUD ──► AUTORIZACIÓN ──► TENANT ──► KILL SWITCH ──► IDEMPOTENCIA
                                                                  │
                                      RESULTADO ◄── AUDITORÍA ◄── EJECUCIÓN
```

| Paso | ¿Existe hoy? | Qué falta |
|---|:--:|---|
| Solicitud | ✔ | — |
| Autorización | parcial | **por nivel y por herramienta**: hoy es binaria |
| Tenant | ✔ | — (fail-closed, probado) |
| Kill switch | ✔ | **granularidad por nivel** |
| Idempotencia | ✔ | **origen estable** en más caminos |
| Ejecución | ✔ | — |
| Auditoría | ✔ | dos campos (§13) |
| Resultado | ✔ | — (`verificacion_accion`) |

### Evidencia que debería acompañar a una acción autónoma futura

Además de la que ya exige una propuesta:

1. Los **argumentos resueltos** que se enviarán (no los que propuso el modelo).
2. La **clave de idempotencia** y su `origen`, con el origen nombrado.
3. El **nivel** requerido y el nivel **vigente** en el momento de decidir.
4. La **versión de la regla** o del documento de conocimiento aplicado.
5. La **decisión humana previa**, si el nivel la exige.
6. El **plan de reversión**: qué operación concreta desharía esto.
7. La **condición de éxito medible** — y no puede ser una mejora del ping: está
   medido dos veces que el mismo equipo sano devuelve 1/3, 2/3 y 3/3 en corridas
   seguidas.

---

## 10. Autorización

| Nivel | Quién autoriza |
|:--:|---|
| 0 · Observar | el sistema (no hay acción que autorizar) |
| 1 · Recomendar | el sistema propone; **ADMIN / SUPERVISOR / OPERACIONES** revisan |
| 2 · Coordinar | ADMIN, por herramienta, con el kill switch activo |
| 3 · Ejecutar reversible | ADMIN, por herramienta, + kill switch + idempotencia con origen estable |
| 4 · Crítica | **aprobación humana explícita en cada ocurrencia.** No hay autorización permanente |

Los roles son los que existen: `ROLES_GESTION = {ADMIN, SUPERVISOR, OPERACIONES}`.
**No se inventó ninguno.** Los niveles 2 y 3 se reservan a ADMIN porque
`Profile.save()` deriva `is_organization_admin = (role == "ADMIN")` y es el único
rol que ya implica administración.

### Lo que la IA nunca puede hacer

| Prohibido | Cómo está garantizado hoy |
|---|---|
| Elevar su propia autonomía | ninguna herramienta escribe `interruptor_autonomia`; `autonomia_detener` solo **detiene** |
| Autorizarse | `frontera` usa un `ContextVar` privado con un `_Permiso` que **solo ese módulo construye**. No hay `autorizado=True` que un llamador pueda pasar |
| Cambiar el kill switch | ídem; el rol `autonomia_operador` es `NOLOGIN NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` |
| Cambiar permisos | `supervisor.py` no toca `Profile` |
| Cambiar de tenant | el tenant se exige y se compara; distinto tenant → `ACCION_EXTERNA_TENANT_DISTINTO` |
| Modificar su propio nivel | `nivel_autonomia_requerido` no está en `CAMPOS_MODIFICABLES` (M09-F) |

Y una propiedad que conviene no perder: **`supervisor.py` no tiene ninguna
función que toque `Profile`, permisos, roles ni el interruptor.** La garantía no
es una regla escrita: es una ausencia de código.

---

## 11. Resultados — seis estados, no uno

```
PROPUESTA ──► DECISIÓN ──► EJECUCIÓN ──► RESULTADO ──► VALIDACIÓN ──► CIERRE
   IA          humano        sistema       del tercero    medición      humano
                  │
                  └── hoy la cadena se corta AQUÍ
```

| Distinción | Por qué importa |
|---|---|
| **ACEPTADA ≠ EJECUTADA** | Aceptar registra una opinión humana. Hoy `ejecutar_propuesta` levanta y `ejecutada` no es un estado |
| **EJECUTADA ≠ VALIDADA** | Que la llamada salga no prueba el efecto. Ya está modelado: `VERIFICACION_PENDIENTE`, `ACCION_CONFIRMADA`, `ACCION_NO_CONFIRMADA`, **`NO_VERIFICABLE`** — y el cuarto no es el tercero: *"no se pudo medir" no es "no funcionó"* |
| **VALIDADA ≠ CERRADA** | `ACCION_CONFIRMADA` significa que el equipo reinició y volvió. **Que la casa tenga internet no lo dice ningún endpoint**: lo sabe el cliente, y hay que preguntárselo |

Esa última fila es la razón por la que ningún cierre está en las candidatas.

---

## 12. Fallback — una sola regla

> **Ante cualquier condición de abajo: NO EJECUTAR + REGISTRAR.**
> Escalar o reintentar **solo** según una política autorizada por escrito. En
> ausencia de política, la respuesta es no ejecutar.

| Condición | Comportamiento exigido | ¿Ya se comporta así? |
|---|---|:--:|
| Kill switch detenido | no ejecutar; registrar `CODIGO_BLOQUEO` | ✔ |
| Kill switch ilegible | **no ejecutar** — *sin control no es autorización* | ✔ |
| Tenant inválido/ausente | no ejecutar; `ACCION_EXTERNA_SIN_TENANT` | ✔ |
| Tenant distinto | no ejecutar; `ACCION_EXTERNA_TENANT_DISTINTO` | ✔ |
| Sin permiso vigente | no ejecutar; `ACCION_EXTERNA_SIN_AUTORIZAR` | ✔ |
| Evidencia insuficiente | no proponer siquiera | ✔ (`CheckConstraint`) |
| Idempotencia no disponible | **no ejecutar**, y decirlo | parcial — hoy se registra la limitación del `origen` en vez de fingir cobertura |
| Permiso de rol insuficiente | 403 | ✔ |
| Servicio externo caído | no reintentar solo; registrar | ✔ |
| Timeout | **no reintentar** — la llamada pudo haber salido | ✔ |
| Resultado ambiguo | `NO_VERIFICABLE`, nunca `NO_CONFIRMADA` | ✔ |
| Concurrencia | primera decisión gana; 409 | ✔ (M09-F) |
| Dato contradictorio | no ejecutar; escalar a humano | **falta** |

El caso del **timeout** es el más importante y el que no tiene solución técnica:
si la llamada salió y la respuesta se perdió, **nadie sabe si el tercero la
aplicó**. Está dicho en `idempotencia.py` en vez de disimularse. Una política de
reintento automático sobre efectos externos duplicaría tickets y pagos.

---

## 13. Auditoría de una acción autónoma futura

**No hace falta una auditoría nueva.** Ya hay tres registros, cada uno con su
dominio: `common.Activity` (CRM), `asistente.audit_log` (motor),
`asistente.operaciones_externas` (idempotencia) + `tool_calls` (metadatos).
Un cuarto solo agregaría un lugar más donde buscar.

| Campo exigido | Dónde está hoy | |
|---|---|:--:|
| actor / contexto | `Activity.user`, `frontera._Permiso.actor` | ✔ |
| organización | `Activity.org`, `organization_id` | ✔ |
| **nivel de autonomía** | — | **falta** |
| evidencia | `PropuestaSupervisor.evidencia` | ✔ |
| herramienta | `tool_calls.herramienta` | ✔ |
| argumentos | `tool_calls.parametros` (metadatos; las respuestas crudas **no** se persisten: traen contraseñas, GPS y cédula) | ✔ |
| idempotency key | `operaciones_externas` (PK) | ✔ |
| resultado | `resultado_ejecucion`, `codigo_error` | ✔ |
| timestamps | `creado_en`, `created_at` | ✔ |
| decisión | `Activity` APPROVED/REJECTED/UPDATE | ✔ |
| **versión de regla/conocimiento** | `conocimiento_version` existe pero **está vacío** | **falta poblarlo** |

Dos huecos, los dos pequeños: **el nivel** y **la versión de la regla**.

---

## 14. Dependencias — quién es dueño del efecto

> **M09 detecta y recomienda. M09 no es dueño de ningún efecto.**
> Convertirlo en dueño de todos los procesos sería exactamente el error que este
> catálogo existe para evitar.

| Módulo | De qué es dueño | Relación con las candidatas |
|---|---|---|
| **M02** Actividades | actividades, compromisos, dependencias | dueño del efecto de `actividad_*` |
| **M03** Programación | programación semanal, disponibilidad, asignación | **dueño de reasignar y reprogramar** |
| **M04** Campo | órdenes, evidencias, estados operativos | dueño de completar/validar |
| **M05** Novedades | bloqueos y sus causas | dueño de `actividad_bloqueada` |
| **M06–M08** | — | sin candidatas identificadas |
| **M09** Supervisor | **señales, recomendaciones, evidencia** | dueño de **nada** ejecutable |
| **M10** Seguridad/RLS | aislamiento, políticas | **bloquea** toda autonomía sobre `campo_*` |
| **M11** | — | sin candidatas |

Regla de gobierno que se deriva: **una acción autónoma futura debe ejecutarse en
el módulo dueño del efecto, no en M09.** M09 propone que se reasigne; M03
reasigna.

---

## 15. Hallazgos M10 — se mantienen, no se resuelven aquí

| # | Hallazgo | Estado |
|---|---|---|
| 1 | **7 tablas `campo_*` sin RLS** | abierto |
| 2 | **69 de 135 tablas `public` sin política** | abierto |
| 3 | El aislamiento de `campo_*` depende hoy **del ORM** | abierto |
| 4 | Defecto B.4 (`test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay`) | abierto |
| 5 | Ejecutor del motor no montado en el contenedor de M09-E | abierto |

**Consecuencia directa para este catálogo:** ninguna acción autónoma sobre
órdenes de trabajo puede diseñarse antes de cerrar el hallazgo 1. Una acción
autónoma que escriba en `campo_*` tendría como único aislamiento el filtro del
ORM — y una acción autónoma es precisamente el caso donde no hay una persona
mirando si el filtro se aplicó.

---

## 16. Matriz final

Int/Ext = efecto interno o externo · Rev = reversible · Aut = autonomía conceptual
KS = cubierto por kill switch · Idem = idempotencia disponible · Aud = auditada

| Acción | Sistema | Int/Ext | Rev | Aut | Revisor | Evid. | Idem | KS | Aud | Candidata | Condiciones |
|---|---|:--:|:--:|:--:|---|:--:|:--:|:--:|:--:|---|---|
| `registrar_pago` | WispHub | Ext | no | 4 | ADMIN | sí | sí | ✔ | ✔ | **NO** | ninguna: facturación |
| `agregar_promesa_pago` | WispHub | Ext | parc | 4 | ADMIN | sí | sí | ✔ | ✔ | **NO** | ninguna: facturación |
| `reportar_comprobante_pago` | interna | Int | sí | 4 | ADMIN | sí | sí | ✔ | ✔ | **NO** | alimenta cobranza |
| `cerrar_ticket_operativo` | WispHub | Ext | no | 4 | Jefe Ops | sí | sí | ✔ | ✔ | **NO** | cierre definitivo |
| `completar_ticket_instalacion` | WispHub | Ext | no | 4 | Jefe Ops | sí | sí | ✔ | ✔ | **NO** | cierre definitivo |
| `cerrar_caso_crm` | CRM | Ext | no | 4 | Jefe Ops | sí | sí | ✔ | ✔ | **NO** | cierre definitivo |
| `cancelar_solicitud_servicio` | CRM | Ext | no | 4 | ADMIN | sí | sí | ✔ | ✔ | **NO** | cancelación |
| `responder_ticket` | WispHub | Ext | no | 4 | Jefe Ops | sí | sí | ✔ | ✔ | **NO** | comunicación |
| `responder_ticket_operativo` | WispHub | Ext | no | 4 | Jefe Ops | sí | sí | ✔ | ✔ | **NO** | comunicación |
| `whatsapp.enviar_*` (proactivo) | WhatsApp | Ext | no | 4 | ADMIN | — | no | **✘** | parc | **NO** | sin frontera (§2.3.1) |
| `cambiar_tipo_onu` | SmartOLT | Ext | no | 4 | ADMIN | sí | sí | ✔ | ✔ | **NO** | red crítica |
| `activar_catv` | SmartOLT | Ext | parc | 4 | ADMIN | sí | sí | ✔ | ✔ | **NO** | servicio facturable |
| `reiniciar_ont` | SmartOLT | Ext | sí | 3/4 | Jefe Ops | sí | sí | ✔ | ✔ | **NO** hoy | solo con confirmación del cliente |
| `actualizar_estado_ticket` | WispHub | Ext | sí | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | nivel + origen + rollback |
| `reasignar_ticket_instalacion` | WispHub | Ext | sí | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | ídem + M03 con datos |
| `crear_ticket` | WispHub | Ext | parc | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen estable |
| `crear_ticket_caso` | WispHub | Ext | parc | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen estable |
| `crear_ticket_instalacion` | WispHub | Ext | parc | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen + M03 |
| `agendar_visita_tecnica` | WispHub | Ext | parc | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen + M03 |
| `agendar_visita_internet` | WispHub | Ext | parc | 3 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen + M03 |
| `importar_caso_externo` | CRM | Int | sí | 2 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen estable |
| `sincronizar_respuestas_externas` | CRM | Int | sí | 2 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen estable |
| `crear_caso_soporte` | CRM | Int | parc | 2 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | origen estable |
| `registrar_solicitud_servicio` | CRM | Int | parc | 2 | ADMIN | sí | sí | ✔ | ✔ | **CONDICIONAL** | decisión comercial |
| `registrar_pedido_wifi` | interna | Int | sí | 2 | Jefe Ops | sí | sí | ✔ | ✔ | **CONDICIONAL** | ninguna técnica |
| `reconciliar_caso_externo` | CRM | Int | parc | 2 | Jefe Ops | sí | sí | ✔ | ✔ | **FUTURA** | regla versionada |
| `crear_tag_crm` | CRM | Int | sí | 2 | Jefe Ops | sí | sí | ✔ | ✔ | **FUTURA** | decisión de producto |
| `proponer_herramienta` | interna | Int | sí | 2 | ADMIN | sí | sí | ✔ | ✔ | **FUTURA** | el borrador sigue exigiendo aprobación |
| **Las 42 de solo lectura** | varios | Int | n/a | **0–1** | — | n/a | n/a | n/a | ✔ | ya son nivel 0/1 | — |

Sin ranking, sin puntuación, sin orden de mérito. El orden es por categoría.

---

## 17. Decisión

### A. Acciones aptas únicamente para Shadow Mode

Las **10 señales** de M09 y las **42 herramientas de solo lectura**. Detectan,
consultan, proponen. Producen efecto **cero** fuera de la base. Es donde el
sistema está hoy, y donde debe quedarse hasta que exista lo de D y E.

### B. Acciones candidatas a futuro

**8 CONDICIONALES** + **3 FUTURAS** = 11 de 27. Ninguna es candidata *hoy*:
las once dependen de al menos una pieza de infraestructura que no existe.

### C. Acciones que permanecen humanas

**16 de 27**, más el camino proactivo de WhatsApp. Justificadas por efecto en
§6: facturación (3), cierres definitivos (3), cancelación (1), comunicación (3),
infraestructura de red (3), y las categorías que ni siquiera tienen herramienta
—borrado, permisos, credenciales, tenant, kill switch, sanciones— que deben
**seguir sin tenerla**.

### D. Infraestructura que falta

| # | Qué | Por qué bloquea |
|---|---|---|
| D-1 | **Granularidad de nivel en el interruptor** | hoy es binario: no se puede activar nivel 2 sin activar 3 y 4 |
| D-2 | **Autorización por herramienta** | hoy `requiere_confirmacion` es un booleano global |
| D-3 | **Origen estable** en más caminos | sin él la idempotencia solo cubre el reintento del turno |
| D-4 | **RLS en `campo_*`** | sin ella, autonomía sobre órdenes sin aislamiento de base |
| D-5 | **Rollback probado** | ninguna candidata tiene uno |
| D-6 | **Datos reales en M02/M03** | 9 de 10 detectores sin cobertura real |

### E. Controles que faltan

| # | Qué |
|---|---|
| E-1 | **El camino saliente de WhatsApp no consulta el kill switch** (§2.3.1) |
| E-2 | No se audita el **nivel de autonomía** vigente |
| E-3 | `conocimiento_version` existe y **está vacío** |
| E-4 | No hay política de **dato contradictorio** |
| E-5 | No hay **confirmación del cliente** como precondición de una acción que le afecte |
| E-6 | El **ejecutor del motor** sigue sin instrumentarse (M09-E) |

### F. Riesgos

| # | Riesgo |
|---|---|
| F-1 | **Confundir nivel 1 con ejecutar.** El §4 lo cierra: nivel 1 es cero ejecución |
| F-2 | **Creer que los niveles existen.** Son un `choices` de un campo, no un mecanismo |
| F-3 | **Duplicación por origen débil.** 34 de las 36 pendientes son `crear_ticket` |
| F-4 | **Timeout sin respuesta**: nadie sabe si el tercero aplicó la llamada |
| F-5 | **Convertir M09 en dueño de los efectos** (§14) |
| F-6 | **Tomar `ACCION_CONFIRMADA` por "el cliente está bien"** |
| F-7 | Activar autonomía con M02/M03 vacíos: operar a ciegas |

### G. Dependencias

```
M10 (RLS campo_*)  ──bloquea──►  toda autonomía sobre órdenes
M03 (datos reales) ──bloquea──►  reasignar, reprogramar, agendar
M02 (datos reales) ──bloquea──►  actividades y compromisos
D-1, D-2           ──bloquean─►  cualquier nivel > 1
D-3                ──bloquea──►  cualquier creación autónoma
```

---

### Conclusión

## GO PARA DISEÑAR LA ETAPA DE AUTONOMÍA

El catálogo está suficientemente definido: las 27 acciones de escritura están
inventariadas contra la configuración **real de producción**, clasificadas por
efecto, con su reversibilidad, su sistema, su cobertura de kill switch y sus
condiciones. Las que nunca deben ser autónomas están justificadas por el efecto
y no por la categoría. La frontera conceptual tiene seis de sus ocho pasos ya
construidos y probados.

**Este GO no activa autonomía, y no autoriza a activarla.** Significa
exactamente una cosa: que ya se puede **diseñar** la etapa siguiente.

**Lo que este GO NO autoriza:** activar autonomía en ningún nivel, tocar el kill
switch, crear rutas ejecutables, desplegar código, aplicar migraciones, ni
ejecutar ninguna de las 27 acciones catalogadas.

**Y una condición que no es negociable:** la etapa de autonomía **no puede
empezar por elegir una acción**. Tiene que empezar por D-1 y D-2 — la
granularidad de nivel y la autorización por herramienta. Sin ellas, "activar
nivel 2" significa, literalmente hoy, activar también el 3 y el 4.

---

### Anexo — qué se midió y cómo

Todo lo cuantitativo de este documento sale de estas lecturas:

| Medición | Fuente | Resultado |
|---|---|---|
| Catálogo de herramientas | `asistente.tenant_config` (producción, v146) | 69 / 27 escrituras / 27 con confirmación |
| Cobertura de la frontera | `grep frontera.(puerta\|autonoma\|humana\|exigir)` | 8 puntos, decide por `solo_lectura` |
| WhatsApp saliente | `grep interruptor\|frontera\|kill\|autonom whatsapp.py` | **0 menciones**; 9 puntos de llamada, todos reactivos |
| Trabajos programados | `asistente.job_schedule_state` | **0 filas**; registro cerrado |
| Niveles 0–4 | `grep NIVEL_* --include=*.py` | solo en `operaciones/models.py` |
| Estados del interruptor | `nucleo/seguridad/interruptor.py` | `(ACTIVO, DETENIDO)` — binario |
| Cola histórica | `asistente.acciones_propuestas` | 36 pendientes / 4 aprobadas y ejecutadas |
| Ledger de idempotencia | `asistente.operaciones_externas` | **0 filas** |

Estado de producción al cerrar el paso, sin cambios respecto de M09-F:

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
40 acciones_propuestas · 192 django_migrations · {ADMIN: 1, USER: 4}
```
