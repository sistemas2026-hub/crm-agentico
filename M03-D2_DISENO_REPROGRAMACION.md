# M03-D2 — Diseño técnico de reprogramación

**Fecha:** 2026-09-18
**Alcance:** diseño. **0 código, 0 modelos, 0 migraciones, 0 endpoints, producción solo `SELECT`.**

---

## 0. Dos correcciones a lo que yo mismo escribí

Antes del diseño, dos cosas de M03-D1 que la inspección de código desmiente. Las
dos cambian lo que M03-D3 debe implementar, así que no son cosméticas.

### 0.1 La regla R-8 estaba mal justificada

**M03-D1 decía:** *"El historial se escribe ANTES de mover la fecha […] si eso se
escribe al final y algo falla, lo que se pierde es justo la parte que no se puede
reconstruir."*

**[MEDIDO]** Eso es falso dentro de una transacción única: si cualquier escritura
falla, **todas** se deshacen, en cualquier orden. M03-B ya lo demostró — su prueba
de rollback rompe el **último** paso y no queda nada.

**[DISEÑO] R-8' — la regla correcta:**

> **Los valores anteriores se CAPTURAN de la fila bloqueada antes de mutarla.**
> El orden de las escrituras dentro de la transacción es indiferente para la
> atomicidad; lo que no es indiferente es **leer antes de sobrescribir**.

Lo que había que proteger no era el orden de los `INSERT`: era no perder
`programada_para`, `dia` y `programacion_id` al pisarlos.

### 0.2 R-2' se puede anclar en algo mejor que el nombre del evento

**[MEDIDO]** `_aplicar_transicion` (`transiciones.py:313`) escribe en **todos** los
eventos de transición:

```python
datos={"estado_anterior": estado_actual,
       "nuevo_estado": nuevo_estado,
       "revision": orden.revision, **metadatos}
```

> Anclar R-2' en `datos.nuevo_estado ∈ {en_camino, en_sitio}` en vez de en una
> lista de nombres de evento es **más robusto**: si mañana se agrega una acción
> operativa nueva, `nuevo_estado` la captura sola, mientras que una lista de
> `tipo` habría que mantenerla.

---

## 1. Estado actual medido

**[MEDIDO]** Producción, `read_only = True`:

```
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
OrdenTrabajo 3 (en_sitio ×2, completada_campo ×1) · programada_para 0/3
AsignacionTrabajo 3 · EventoTrabajo 12 · Activity 592 (Case 564, Lead 28)
```

**[RIESGO]** Las 3 órdenes están **las tres con la vuelta actual iniciada**:
hoy **ninguna** entraría por la ruta normal ni por la de corrección. La
contingencia es la única ruta con casos reales.

### Inventario de lo que se reutiliza

| Pieza | Ubicación exacta | Qué aporta |
|---|---|---|
| `programar_orden` | `operaciones/programacion.py` | patrón de lock + transacción + coherencia |
| `publicar_programacion` | `operaciones/programacion.py` | patrón de transición con lock |
| `revisar_coherencia` | `operaciones/programacion.py` | verificación línea ↔ orden |
| `_lineas_vigentes` | `operaciones/programacion.py` | definición de "vigente" |
| `ErrorProgramacion`, `YaProgramada`, `PlanNoPublicable`, `PlanIncoherente` | idem | jerarquía de errores |
| `_exigir_gestion` | `campo/despacho_views.py:50` | 403 por rol |
| `_orden_o_404` | `campo/despacho_views.py:66` | 404 estricto entre organizaciones |
| `manejar_idempotencia` | `campo/services/idempotencia.py:34` | idempotencia por cabecera |
| `_aplicar_transicion` | `campo/services/transiciones.py:268` | **no se usa**: reprogramar no transiciona |
| `EventoTrabajo` | `campo/models.py:380` | `tipo` texto libre + `datos` JSONB |
| `NovedadOperativa` | `operaciones/models.py:469` | causa + fecha anterior/nueva + actor |

**[MEDIDO]** Catálogo exacto de `tipo` de `EventoTrabajo` que el código escribe
hoy — ninguno colisiona con los nombres nuevos:

```
orden_creada · asignacion · reasignacion · programacion · datos_actualizados
evidencia_confirmada · accion_marcar_en_camino · accion_marcar_llegada
accion_iniciar · accion_cancelar · trabajo_completado_campo
presentado_a_validacion · validacion_aprobada · correccion_requerida
reapertura_correccion · orden_cerrada
```

---

## 2. Arquitectura de la operación

**[DISEÑO]** **Dos operaciones y un clasificador**, no una sola función que
adivine.

```
operaciones/programacion.py          (el módulo que ya existe)

    clasificar_ruta(orden) -> "normal" | "correccion" | "contingencia"
        lectura pura, sin efectos. La expone la API para que la pantalla
        sepa qué formulario mostrar ANTES de enviar nada.

    reprogramar_orden(...)     normal + corrección
        si la vuelta actual ya inició -> levanta RequiereContingencia

    registrar_contingencia(...)  la ruta excepcional, explícita
```

**[DISEÑO] Por qué no una sola función:** si `reprogramar_orden` registrara una
contingencia por su cuenta al ver una OT en vuelo, **haría algo distinto de lo que
le pidieron** y devolvería 2xx. Levantar `RequiereContingencia` obliga a que la
contingencia sea un acto deliberado — que es exactamente lo que la decisión
aprobada dice que es.

### Entradas

**[DISEÑO]** Tras revisar el código, lo mínimo necesario:

| Parámetro | Obligatorio | Nota |
|---|:--:|---|
| `org` | sí | de `request.org`, **nunca del cliente** |
| `orden` | sí | resuelta por `_orden_o_404` |
| `programada_para` | sí | con zona horaria (M03-B ya lo exige) |
| `programacion_destino` | sí | acotada a `org` |
| `actor` | sí | `request.profile`; sin default |
| `causa` | condicional | valor de `NovedadOperativa.TIPOS`; obligatorio según §4 |
| `motivo` | condicional | texto libre → `NovedadOperativa.descripcion` |
| `contexto` | no | `{"novedad_id": …, "propuesta_id": …}` → `datos` |

**No hace falta** `zona`, `prioridad` ni `secuencia`: reprogramar cambia **cuándo**,
y M03-E es el dueño de la secuencia. **No hace falta** `vuelta`: se lee.

### Errores

**[DISEÑO]** Extienden la jerarquía existente (`ErrorProgramacion` es
`ValueError`):

| Excepción | HTTP | Cuándo |
|---|:--:|---|
| `NoEstaProgramada` | **409** | no había programación previa → esto es **programar** (M03-B) |
| `RequiereContingencia` | **409** | la vuelta actual ya inició |
| `YaEnEsaFecha` | **409** | misma fecha y mismo plan → ver §10 |
| `PlanNoPublicable` *(existente)* | 409 | plan destino cerrado |
| `ErrorProgramacion` *(existente)* | 400 | organización, zona horaria, semana, motivo faltante |

---

## 3. Ruta normal

**Aplica a:** vuelta actual **no iniciada** y **sin** `reapertura_correccion`
previa. En la práctica: `estado_operativo = asignada`.

### 3.1 Validaciones, en orden

```
 1. actor no es None                                    -> ErrorProgramacion
 2. programada_para no es None y trae tzinfo            -> ErrorProgramacion
 3. orden.org_id == org.id                              -> ErrorProgramacion
 4. programacion_destino.org_id == org.id               -> ErrorProgramacion
 5. LOCK orden (select_for_update) y releer
 6. LOCK programacion_destino (select_for_update)       <- ver §9, orden fijo
 7. clasificar_ruta(orden) == "normal"                  -> RequiereContingencia
 8. estado_operativo no terminal (cerrada/cancelada)    -> ErrorProgramacion
 9. HAY programación previa                             -> NoEstaProgramada
10. plan destino en {borrador, publicada}               -> PlanNoPublicable
11. localtime(programada_para).date() dentro de la
    semana del plan destino                             -> ErrorProgramacion
12. no existe ya una línea de esta OT en el destino     -> ErrorProgramacion
13. si el plan destino está PUBLICADO: causa presente   -> ErrorProgramacion
14. destino != (fecha actual, plan actual)              -> YaEnEsaFecha
```

**[MEDIDO]** El paso 9 distingue reprogramar de programar: *"hay programación
previa"* = `orden.programada_para IS NOT NULL` **o** existe una línea vigente. Son
las dos vías que M03-B ya comprueba en su guarda `YaProgramada`.

### 3.2 Captura (R-8')

```
anterior = {
  "programada_para": fresca.programada_para,
  "dia":             linea_vigente.dia            if hay línea else None,
  "hora_inicio":     linea_vigente.hora_inicio    if hay línea else None,
  "plan":            linea_vigente.programacion_id if hay línea else None,
  "plan_estado":     linea_vigente.programacion.estado if hay línea else None,
  "linea":           linea_vigente.id             if hay línea else None,
}
```

**Se lee de la fila bloqueada**, no del objeto que llegó por parámetro.

### 3.3 Escrituras

**Caso A — mismo plan** *(misma semana)*

**[MEDIDO]** `unique(programacion, orden)` impide una segunda línea en el mismo
plan. Por tanto:

```
linea_vigente.dia         = dia_nuevo
linea_vigente.hora_inicio = hora_nueva
linea_vigente.save(update_fields=["dia","hora_inicio","updated_by","updated_at"])
```

> **[DISEÑO] No se pierde historial**: el `dia` anterior queda en
> `EventoTrabajo.datos`. Lo que no se sobrescribe es **el registro**, no la fila —
> la fila no puede duplicarse.

**Caso B — otro plan** *(otra semana, o la misma reorganizada)*

```
linea_vigente.estado = REPROGRAMADA
linea_vigente.save(update_fields=["estado","updated_by","updated_at"])

linea_nueva = ProgramacionOrden.objects.create(
    org=org, programacion=destino, orden=fresca,
    dia=dia_nuevo, hora_inicio=hora_nueva,
    zona=linea_vigente.zona, prioridad=linea_vigente.prioridad,
    estado=PLANIFICADA)
```

**[MEDIDO]** `REPROGRAMADA` existe en el modelo y **ningún código la escribe hoy**
— M03-D3 sería su primer escritor.

**Común a A y B**

```
fresca.programada_para = programada_para
fresca.revision += 1
fresca.save(update_fields=["programada_para","revision","updated_by","updated_at"])
```

**[MEDIDO]** `revision` se sube por el mismo motivo que en M03-B y en
`despacho.asignar`: es el control optimista de la cola offline del técnico, y el
día del trabajo cambió.

**[DISEÑO]** **`estado_operativo` NO se toca.** Reprogramar no es una transición;
`_aplicar_transicion` **no se usa**.

### 3.4 Traza

```
EventoTrabajo(tipo="reprogramacion", profile=actor, datos={...§7})
NovedadOperativa(...)   si hay causa   -> §7.2
```

---

## 4. Ruta corrección

**[DECISIÓN APROBADA]** Aplica cuando existe `reapertura_correccion` y **la
vuelta actual no ha empezado**.

### 4.1 Cómo se identifica la vuelta actual — solo con eventos existentes

**[MEDIDO]** Los dos hechos que lo permiten:

```
requerir_correccion()  ->  EventoTrabajo tipo="reapertura_correccion"
                           (y vuelta += 1, en la misma transacción)

cualquier inicio       ->  EventoTrabajo con datos["nuevo_estado"] ∈
                           {"en_camino", "en_sitio"}
```

**[DISEÑO] Definición operativa de `clasificar_ruta`:**

```
ultima_reapertura = EventoTrabajo
      .filter(orden=orden, tipo="reapertura_correccion")
      .order_by("-created_at").first()

if ultima_reapertura is None:
    #  nunca hubo devolución: la regla se comporta como la anterior
    return "contingencia" if orden.iniciada_en else "normal"

inicio_posterior = EventoTrabajo.objects.filter(
      orden=orden,
      datos__nuevo_estado__in=["en_camino", "en_sitio"],
      created_at__gt=ultima_reapertura.created_at).exists()

return "contingencia" if inicio_posterior else "correccion"
```

**[MEDIDO]** El fallback es exacto: sin devoluciones, `iniciada_en IS NOT NULL`
equivale a haber entrado alguna vez en `en_camino`/`en_sitio`
(`transiciones.py:293`). **La regla nueva contiene a la vieja.**

**[RIESGO]** `datos` es JSONB **sin índice**. Con 12 filas en producción es
irrelevante; si la bitácora creciera mucho por orden, la consulta se degrada. Una
alternativa equivalente y indexable es filtrar por
`tipo__in=("accion_marcar_en_camino","accion_marcar_llegada","accion_iniciar")`,
a costa de mantener la lista. **Se recomienda `nuevo_estado`** y se deja anotado
el coste.

### 4.2 Diferencias con la ruta normal

| | Normal | **Corrección** |
|---|---|---|
| precondición | sin devolución previa, sin iniciar | **con** `reapertura_correccion`, vuelta sin empezar |
| `programada_para` | se actualiza | **se actualiza** |
| línea de plan | A o B según el plan | **igual** |
| causa/motivo | solo si el plan está publicado | **SIEMPRE obligatorio** |
| `EventoTrabajo.tipo` | `reprogramacion` | **`reprogramacion_por_correccion`** |
| `datos.vuelta` | informativo | **obligatorio** |

**[DECISIÓN APROBADA]** **`iniciada_en` NO se modifica.** El código lo trata como
el primer inicio histórico (`and not orden.iniciada_en`), y reescribirlo borraría
cuándo empezó realmente el trabajo.

**[DECISIÓN APROBADA]** **No se borra ni se modifica ningún evento.** La bitácora
es append-only; la corrección **agrega**.

---

## 5. Ruta contingencia

**Aplica a:** la vuelta actual **ya inició**.

### 5.1 Qué hace

```
NovedadOperativa(org, tipo=<causa>, descripcion=<motivo>,
                 orden=orden, registrada_por=actor,
                 programada_anterior=orden.programada_para,
                 programada_nueva=None)          <- no hay fecha nueva

EventoTrabajo(tipo="contingencia", profile=actor, datos={...})
```

### 5.2 Qué NO hace

**[DECISIÓN APROBADA]**

```
programada_para .... NO se toca
línea de plan ...... NO se toca
estado_operativo ... NO se toca
revision ........... NO se sube (nada que la app deba re-sincronizar)
```

**[DISEÑO] Y es coherente, no una limitación:** `programada_para` dice lo que se
**planificó**; `iniciada_en` y `completada_campo_en` dicen lo que **pasó**. Un
trabajo que se complicó no necesita que le reescriban el plan: necesita que quede
por qué.

### 5.3 Diferencia frente a corrección

| | Corrección | **Contingencia** |
|---|---|---|
| la vuelta actual | **no** empezó | **sí** empezó |
| cambia la fecha | **sí** | **no** |
| escribe línea de plan | sí | **no** |
| `NovedadOperativa` | obligatoria | **obligatoria** |
| `programada_nueva` | la fecha nueva | **`None`** |

### 5.4 Lo que queda pendiente

**[PENDIENTE]** **La contingencia no tiene salida.** Es un registro, no un
estado: nada marca "esta orden tiene una contingencia abierta" ni la cierra. Con
las estructuras actuales, verlo exige consultar `NovedadOperativa` por orden.

> No se inventa un estado ni una bandera. Si operaciones necesita una bandeja de
> contingencias abiertas, **es una decisión y probablemente un campo nuevo**.

---

## 6. Plan publicado

**[DECISIÓN APROBADA]** Publicado no está congelado, pero nada cambia en
silencio.

| Caso | Operación | `EventoTrabajo.tipo` | Causa | Qué queda en `datos` |
|---|---|---|:--:|---|
| **A** · cambiar una OT **dentro** de un plan publicado | `reprogramar_orden`, caso A | `reprogramacion` | **sí** | `dia` ant./nuevo, plan (el mismo), `plan_estado="publicada"`, causa, motivo |
| **B** · **agregar** una OT nueva a un plan publicado | **`programar_orden` (M03-B)**, ajustado | **`adicion_a_plan_publicado`** | **sí** | plan, `dia`, causa, motivo. **Sin "anterior": no existe** |
| **C** · mover a **otra semana** desde un publicado | `reprogramar_orden`, caso B | `reprogramacion` | **sí** | plan ant. y nuevo, ambos estados, línea ant. marcada `reprogramada` |
| **D** · cambiar el **plan destino** | idéntico a C | `reprogramacion` | **sí** | idem |

**[DISEÑO] El único cambio que el caso B exige en M03-B:** cuando
`programacion.estado == PUBLICADA`, exigir causa y escribir
`tipo="adicion_a_plan_publicado"` en lugar de `"programacion"`. **`tipo` es texto
libre — sin migración.** Es un cambio aditivo dentro de `programar_orden`.

**[RIESGO]** Ese ajuste toca M03-B, que está VALIDADO. M03-D3 deberá volver a
correr su suite completa (29 pruebas) y comprobar que el caso "plan borrador"
sigue sin exigir causa.

---

## 7. Modelo de trazabilidad

### 7.1 `EventoTrabajo.datos` — el contenido exacto

**[DISEÑO]** Todo en JSONB. **Ningún campo de modelo nuevo.**

```jsonc
{
  "ruta": "normal" | "correccion" | "contingencia",
  "vuelta": 2,

  "anterior": {
    "programada_para": "2026-10-07T09:00:00+00:00",
    "dia": "2026-10-07",
    "hora_inicio": "09:00:00",
    "plan": "<uuid>",
    "plan_estado": "publicada",
    "linea": "<uuid>"
  },
  "nuevo": {
    "programada_para": "2026-10-20T14:30:00+00:00",
    "dia": "2026-10-20",
    "hora_inicio": "14:30:00",
    "plan": "<uuid>",
    "plan_estado": "borrador",
    "linea": "<uuid>"
  },

  "causa": "ausencia",
  "motivo": "el técnico quedó incapacitado",
  "novedad": "<uuid>",

  "contexto": { "propuesta": "<uuid>" },

  "sla": { "evaluado": false, "razon": "la orden no tiene caso vinculado" }
}
```

**[DISEÑO]** `anterior` y `nuevo` con la misma forma a propósito: leer la
bitácora no debería exigir recordar en qué ruta se escribió cada clave.

En contingencia, `nuevo` es `null` y `anterior` conserva la fecha vigente.

### 7.2 `NovedadOperativa` — la causa

**[DECISIÓN APROBADA]**

```
tipo                 = LA CAUSA  (ausencia | bloqueo | falta_material |
                                  dependencia | cambio_de_prioridad |
                                  dato_incompleto | demora_sin_causa_registrada)
                       NUNCA "reprogramacion"
descripcion          = el motivo en texto libre
orden                = la OT
registrada_por       = el actor
programada_anterior  = la fecha que regía
programada_nueva     = la nueva  (None en contingencia)
```

**[MEDIDO]** `NovedadOperativa` **no tiene `JSONField`** ni FK a plan: el plan
viaja en `EventoTrabajo.datos`. Es la razón por la que la bitácora es la
superficie canónica.

### 7.3 Las siete preguntas de la decisión C

| Pregunta | Se responde con |
|---|---|
| qué causó el cambio | `NovedadOperativa.tipo` + `descripcion` |
| qué cambio ocurrió | `EventoTrabajo.tipo` + `datos.anterior/nuevo` |
| cuándo ocurrió | `EventoTrabajo.created_at` |
| quién lo realizó | `EventoTrabajo.profile` + `NovedadOperativa.registrada_por` |
| fecha anterior | `datos.anterior.programada_para` + `programada_anterior` |
| fecha nueva | `datos.nuevo.programada_para` + `programada_nueva` |
| qué plan estaba involucrado | `datos.anterior.plan` y `datos.nuevo.plan` |

### 7.4 `common.Activity`

**[MEDIDO]** **No se usa.** `ENTITY_TYPE_CHOICES` (`common/models.py:672`) no
incluye ninguna entidad de M03, y declararla es una migración. Producción lo
confirma: sus 592 filas son `Case` (564) y `Lead` (28).

**No se fuerza** (§AUDITORÍA del encargo).

---

## 8. Invariantes verificables

**[DISEÑO]** Expresadas como consultas, para que M03-D3 pueda comprobarlas:

| # | Invariante | Verificación |
|:--:|---|---|
| **I-1** | una OT tiene **como máximo una** línea vigente | `count(ProgramacionOrden where orden=X and estado in (planificada,confirmada)) <= 1` |
| **I-2** | la línea vigente y `programada_para` dicen el mismo día | `linea.dia == localtime(X.programada_para).date()` |
| **I-3** | ninguna línea cambia de plan: se marca y se crea otra | el `programacion_id` de una línea **nunca** se actualiza |
| **I-4** | la bitácora no pierde eventos | `EventoTrabajo` solo recibe `INSERT` |
| **I-5** | un plan publicado no cambia en silencio | toda escritura con `plan_estado="publicada"` tiene `causa` no vacía |
| **I-6** | una OT con la vuelta iniciada no entra por la ruta normal | `clasificar_ruta` se evalúa **después** del lock |
| **I-7** | una corrección abre vuelta lógica nueva | `datos.vuelta == orden.vuelta` y hay `reapertura_correccion` previa |
| **I-8** | el SLA no se modifica | ninguna escritura toca `Case` |

**[DISEÑO]** **I-1 e I-2 son extensibles a `revisar_coherencia`** de M03-C, que
ya comprueba I-2 sobre las líneas de un plan. Añadir I-1 haría que publicar
detectara una reprogramación mal hecha.

**[PENDIENTE]** La bicondicional *"`programada_para` no nulo ⟺ hay línea
vigente"* **no es una invariante hoy**: `despacho.crear_orden` puede fijar
`programada_para` sin crear línea. Convertirla en invariante exigiría decidir qué
hacer con esas órdenes.

---

## 9. Concurrencia

### 9.1 Qué se bloquea, y en qué orden

**[DISEÑO]**

```
1. OrdenTrabajo          select_for_update()     SIEMPRE
2. ProgramacionSemanal   select_for_update()     el plan DESTINO
```

**El orden es fijo: OT primero, plan después.** No es arbitrario:

**[MEDIDO]** M03-B bloquea **solo la OT**; M03-C bloquea **solo el plan**. Con el
orden OT→plan, M03-D3 no cierra ningún ciclo con ninguna de las dos, porque
ninguna espera por la otra. **Invertirlo sí podría producir un interbloqueo** con
una operación futura que bloqueara el plan primero.

### 9.2 Por qué no hacen falta más locks

**[DISEÑO]** `ProgramacionOrden` **no se bloquea por separado**: toda operación
que toque la programación de una OT pasa por el lock de esa OT
(`programar_orden`, `reprogramar_orden`, `registrar_contingencia`). **El lock de
la orden es el punto de serialización de todo lo que programa esa orden.**

### 9.3 Las cuatro carreras

| Carrera | Sin protección | Con el diseño |
|---|---|---|
| dos reprogramaciones simultáneas | dos fechas incompatibles | la 2ª relee tras el lock y ve la fecha de la 1ª |
| doble línea para la misma OT | I-1 violada | serializadas por el lock de la OT |
| pérdida de actualización | la 2ª pisa a la 1ª sin verla | se relee **después** del lock, nunca del objeto recibido |
| plan publicado entre medias | se valida contra un estado viejo | el plan destino también se bloquea |

**[MEDIDO]** El mecanismo está probado: M03-B y M03-C verificaron su lock
**desarmándolo** y comprobando que la prueba falla. M03-D3 debe hacer lo mismo
(prueba 10 del §14).

---

## 10. Idempotencia

### 10.1 El mecanismo existente, medido

**[MEDIDO]** `manejar_idempotencia` (`campo/services/idempotencia.py:34`):

| | |
|---|---|
| clave | cabecera `Idempotency-Key` o `X-Idempotency-Key` |
| ámbito | `(org, idempotency_key)` |
| compara además | `http_method`, `endpoint`, `request_hash` (SHA256 de JSON canónico) |
| misma clave, payload distinto | **409 `IDEMPOTENCY_KEY_REUSED`** |
| en curso | **409 `OPERACION_EN_CURSO`** |
| completada | **replay** de la respuesta guardada, con cabecera `Idempotent-Replay: true` |
| **sin cabecera** | **se ejecuta normal, sin protección** |

### 10.2 Decisión

**[DISEÑO]** **Se reutiliza tal cual, con `@manejar_idempotencia` sobre la vista**
— igual que `ProgramarTrabajoView` y `AsignarTrabajoView`. **No se crea un segundo
sistema.** La clave lógica es la que el cliente envía; el servidor no la inventa.

### 10.3 La idempotencia semántica, que es otra cosa

**[DISEÑO]** Sin cabecera, un doble clic reprogramaría dos veces. La segunda
llamada pediría mover a la fecha que **ya rige**, así que:

> **`YaEnEsaFecha` → 409**, sin escribir nada, cuando el destino coincide con la
> fecha **y** el plan vigentes.

**[DISEÑO] Por qué rechazar y no aceptar como no-op:** aceptarla escribiría un
evento `reprogramacion` con `anterior == nuevo` — ruido en la bitácora que esta
operación entera existe para mantener limpia.

**[PENDIENTE]** Que el negocio prefiera **registrar** el intento nulo en vez de
rechazarlo es una decisión que no está en A–F. Se recomienda rechazar.

---

## 11. Permisos

**[MEDIDO]** Sin roles nuevos:

```
ROLES_GESTION = {"ADMIN", "SUPERVISOR", "OPERACIONES"}      campo/permissions.py:9
```

**[DECISIÓN APROBADA]** Un solo acto: **solicitar = autorizar = ejecutar**.

**[DISEÑO]** Las tres operaciones cuelgan del recurso orden, reutilizando el
patrón de M03-B:

```
POST /api/campo/trabajos/<uid:pk>/reprogramar/     reprogramar_orden
POST /api/campo/trabajos/<uid:pk>/contingencia/    registrar_contingencia
GET  /api/campo/trabajos/<uid:pk>/                 ya expone la orden; clasificar_ruta
                                                   puede sumarse a su respuesta
```

**[MEDIDO]** Vivir en `campo/` tiene una consecuencia concreta: **la guarda de
rutas de M09-F no se toca**, porque fija el inventario de `operaciones/`
(`test_m09f_gobernanza.py:722`). M03-C sí tuvo que actualizarla; M03-D3 no.

**[DISEÑO]** Cada vista: `permission_classes=[IsCampoAuthenticated]` +
`_exigir_gestion(request)` + `_orden_o_404(request, pk)` + `@manejar_idempotencia`.

---

## 12. Multi-tenant

**[DISEÑO]**

| Control | Mecanismo |
|---|---|
| organización | **`request.org`**, nunca del cuerpo. El serializador **no declara** `org` |
| la orden | `_orden_o_404` filtra por `org` → **404**, no 403 |
| el plan destino | `.filter(id=…, org=request.org)` → **404** |
| en el servicio | se revalidan **las dos** pertenencias, sin confiar en la vista |

**[MEDIDO]** El servicio revalida porque M03-B y M03-C ya lo hacen y tienen prueba
de ello (`test_b3b`, `test_c3b`): la vista filtra, el servicio no da por hecho que
lo hizo.

**[RIESGO]** **`campo_orden_trabajo` y `campo_evento_trabajo` no tienen RLS** —
`relrowsecurity = false`, **0 políticas** (medido en producción). El aislamiento
lo da **solo la aplicación**, y **B-7 no lo cambia**: la causa es
`ORG_SCOPED_TABLES` (`common/rls/__init__.py:34`), que no lista ninguna `campo_*`.
Una reprogramación escribe a la vez en tablas con RLS (`operaciones_*`) y sin ella.

---

## 13. SLA

**[DECISIÓN APROBADA]** Reprogramar **no extiende, no reinicia, no modifica** el
SLA.

**[MEDIDO]** No hay nada que impedir: `Case._sla_deadline` (`cases/models.py:454`)
camina horas hábiles desde `Case.created_at` más el tiempo en `Pending`. **No lee
`programada_para`.**

**[DECISIÓN APROBADA]** **No se crea vínculo OT→Case ni motor nuevo.**

**[DISEÑO]** Y como no se crea el vínculo, la evaluación no puede hacerse. Lo que
se registra es **eso mismo**, explícitamente:

```jsonc
"sla": { "evaluado": false, "razon": "la orden no tiene caso vinculado" }
```

> **[DISEÑO] Registrar la ausencia de evaluación es mejor que omitir la clave.**
> Una clave ausente se lee como "nadie lo pensó"; ésta dice que se pensó y por qué
> no se pudo.

**[PENDIENTE]** Evaluar de verdad si la fecha nueva supera el vencimiento exige el
vínculo OT ↔ Case, que la decisión F **prohíbe crear aquí**. Queda fuera de
M03-D3.

---

## 14. Plan de pruebas para M03-D3

| # | Precondición | Operación | Resultado esperado | Evidencia que debe persistir |
|:--:|---|---|---|---|
| **1** | OT `asignada` programada el mié, plan borrador | reprogramar al vie, mismo plan | **200**; la línea **se actualiza** (no hay 2ª) | `dia` nuevo; evento `reprogramacion` con `anterior.dia`=mié y `nuevo.dia`=vie; `programada_para` = vie |
| **2** | igual, plan A semana 1 | reprogramar a plan B semana 2 | **200** | línea A en **`reprogramada`**; línea B nueva `planificada`; `datos.anterior.plan` ≠ `datos.nuevo.plan` |
| **3** | plan **borrador**, sin causa | reprogramar | **200** | evento sin `causa`; **0** `NovedadOperativa` |
| **4** | plan **publicado**, sin causa | reprogramar | **400** | **nada escrito**: `programada_para`, línea y estado intactos |
| **5** | plan **publicado**, OT no programada | `programar_orden` con causa | **201** | evento **`adicion_a_plan_publicado`**; sin `anterior` |
| **6** | OT con `reapertura_correccion`, sin inicio posterior | reprogramar con causa | **200** | evento **`reprogramacion_por_correccion`**; `datos.vuelta == orden.vuelta` |
| **7** | tras la corrección de la prueba 6 | `marcar_en_camino`, luego reprogramar | **409 `RequiereContingencia`** | nada cambia; el evento de inicio **sigue existiendo** |
| **8** | OT `en_sitio`, nunca devuelta | reprogramar | **409 `RequiereContingencia`** | `programada_para` intacto; **0** líneas nuevas |
| **9** | igual que 8 | `registrar_contingencia` con causa | **201** | `NovedadOperativa` con `tipo`=causa y `programada_nueva=None`; evento `contingencia`; **`programada_para` intacto** |
| **10** | OT programada; **dos peticiones a la vez** | reprogramar a dos fechas distintas | `[200, 409]`; **nunca dos 200** | **1** línea vigente; `dia` == `localtime(programada_para).date()`. **Repetir sin `select_for_update`: debe FALLAR** |
| **11** | OT programada | reprogramar con fallo inyectado en la última escritura | excepción | leído **por conexión independiente**: `programada_para`, línea y estado **sin cambios**; **0** eventos nuevos |
| **12** | OT de org A, plan de org B | reprogramar desde A | **404** | 0 escrituras en B; y simétrico B→A |
| **13** | OT `asignada` **sin** programación | reprogramar | **409 `NoEstaProgramada`** | nada escrito; el mensaje debe decir que eso es *programar* |
| **14** | OT ya con línea en el plan destino | reprogramar a ese plan | **400** | 0 líneas nuevas; `unique(programacion, orden)` no llega a dispararse |
| **15** | OT sin caso vinculado, fecha nueva lejana | reprogramar | **200**, **no se bloquea** | `datos.sla.evaluado == false` con la razón |
| **16** | OT programada, misma `Idempotency-Key` ×2 | reprogramar dos veces | 1ª **200**; 2ª **replay** con `Idempotent-Replay: true` | **1** evento `reprogramacion`, no dos |
| **17** | *(extra)* OT programada | reprogramar a la **misma** fecha y plan | **409 `YaEnEsaFecha`** | **0** eventos: la bitácora no registra un cambio que no ocurrió |

**[DISEÑO]** Las pruebas 10 y 11 deben seguir el método ya usado en M03-B y
M03-C: **verificar el lock desarmándolo** y **leer la persistencia con una
conexión independiente del ORM**.

**[DISEÑO]** Regresión obligatoria: **536 passed** es el baseline medido en
M03-C, más la suite nueva. El ajuste del caso B (§6) obliga a volver a correr las
**29 pruebas de M03-B**.

---

## 15. Dependencias

| Con | Qué | ¿Bloquea D3? |
|---|---|:--:|
| **M03-B** | el caso B (§6) lo modifica: causa obligatoria y `tipo` distinto en plan publicado | **no**, pero exige re-correr su suite |
| **M03-C** | `revisar_coherencia` podría extenderse con I-1 | **no** |
| **M09 / H-05** | la huella de H-05 incluye la fecha → reprogramar **reemite**, conducta declarada en `_ya_propuesta`. Una transacción única evita los falsos positivos de `orden_sin_programar` y `dato_incompleto` | **no** |
| **M03-E** (secuencia) | mover una OT deja huecos de `secuencia` en origen y destino | **no** |
| **M03-F / M03-G** | reprogramar no toca `AsignacionTrabajo`; sin capacidad no hay nada que recalcular | **no** |
| **B-7** | `campo_*` sin RLS | **no**, **[RIESGO]** |

---

## 16. GAPs restantes

| # | GAP | Tipo | ¿Bloquea D3? |
|:--:|---|---|:--:|
| **R-1** | La **contingencia no tiene salida**: nada marca ni cierra una contingencia abierta (§5.4) | decisión + probable campo | **no** |
| **R-2** | **`YaEnEsaFecha`**: ¿rechazar o registrar el intento nulo? (§10.3) | decisión | **no** — se recomienda rechazar |
| **R-3** | La bicondicional `programada_para` ⟺ línea vigente **no es invariante** hoy (§8) | decisión | **no** |
| **R-4** | **SLA no evaluable**: falta el vínculo OT ↔ Case, que F prohíbe crear | **[DEPENDENCIA]** | **no** |
| **R-5** | `datos` JSONB **sin índice** para `clasificar_ruta` (§4.1) | rendimiento | **no** |
| **R-6** | **`campo_*` sin RLS** — B-7 no lo resuelve | seguridad | **no** |
| **R-7** | Catálogo de motivos **no ampliado**: clima, cliente reagenda, acceso denegado | decisión + migración | **no** |
| **R-8** | `NovedadOperativa` sin FK a plan → el plan solo viaja en `datos` | modelo | **no** |

> **Ninguno bloquea M03-D3.** Los ocho se sostienen sobre la misma razón que ya
> tenía M03-D1.1: **`EventoTrabajo` absorbe la trazabilidad sin tocar el esquema.**

---

## 17. Alcance exacto de M03-D3

### Se implementa

| | Qué |
|---|---|
| **1** | `clasificar_ruta(orden)` — lectura pura, con el fallback medido a `iniciada_en` |
| **2** | `reprogramar_orden(...)` — rutas **normal** y **corrección**, casos A y B |
| **3** | `registrar_contingencia(...)` — sin tocar programación |
| **4** | Ajuste de `programar_orden` para el caso B del §6 (`adicion_a_plan_publicado`) |
| **5** | 4 excepciones nuevas: `NoEstaProgramada`, `RequiereContingencia`, `YaEnEsaFecha`, y el mapeo HTTP |
| **6** | 2 vistas en `campo/despacho_views.py` + 2 rutas en `campo/urls.py` |
| **7** | Traza: `EventoTrabajo` (`reprogramacion`, `reprogramacion_por_correccion`, `contingencia`, `adicion_a_plan_publicado`) + `NovedadOperativa` con la **causa** |
| **8** | Suite de 17 pruebas del §14, con lock desarmado y conexión independiente |

### NO se implementa

```
tabla de historial nueva ....... EventoTrabajo alcanza
modelos / migraciones .......... 0
roles nuevos ................... 0
flujo solicitar/autorizar ...... decisión E: un solo acto
vínculo OT -> Case ............. decisión F lo prohíbe
motor SLA ...................... decisión F lo prohíbe
catálogo de motivos ampliado ... R-7
bandeja de contingencias ....... R-1
transición de estado_operativo . reprogramar no transiciona
llamadas externas .............. ninguna
```

### Verificación previa obligatoria

**[DISEÑO]** Antes de escribir código, M03-D3 debe confirmar
`makemigrations --check --dry-run` → **"No changes detected"**, igual que M03-B y
M03-C. **Si aparece una migración, el diseño estaba mal y hay que detenerse.**

---

```
código ......... 0     modelos ....... 0     migraciones ... 0
endpoints ...... 0     roles ......... 0     tablas ........ 0
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
