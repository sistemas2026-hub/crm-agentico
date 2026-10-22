# Paso M09-C.1 — Cierre de las condiciones del diseño funcional

**Fecha:** 17/09/2026 · **Sin código, sin migraciones, sin despliegue.**
Producción intacta: ledger 50 · kill switch **DETENIDO** · 0 filas `activo` ·
`PropuestaSupervisor` 0 filas · `acciones_propuestas` 40 (histórico intacto).

---

## Corrección de lo que afirmé en M09-C

M09-C dijo que **«no existe el rol Jefe de Operaciones»** y lo llamó «el hueco
más importante». Auditando el backend, esa frase era **imprecisa en una
dirección que importa**: lo que existe es bastante más de lo que reporté.

| Ya existe | Dónde |
|---|---|
| `EsJefeDeOperaciones` (clase de permiso DRF) | `operaciones/permissions.py` |
| `ROLES_GESTION = {ADMIN, SUPERVISOR, OPERACIONES}` | `campo/permissions.py:9` — **importado**, no copiado |
| Endpoints de revisión (listar, detalle, revisar, ciclo) | `operaciones/urls.py` + `views.py`, con `permission_classes = [EsJefeDeOperaciones]` |
| Módulo de auditoría (`registrar`, `historial`) | `operaciones/auditoria.py` |
| `supervisor.py` completo: 8 detectores, análisis, dedup, expiración, revisión | 681 líneas |
| `"operaciones"` declarado en `API_RESOURCES` | `common/scopes.py` |
| RLS + FORCE + 2 políticas en las 6 tablas `operaciones_*` | medido en producción |
| Tests | `test_m02_actividades.py`, `test_m03_programacion.py`, `test_m09_supervisor.py` |

**El hueco real es de una línea, y es otro:** `Profile.ROLES`
(`common/utils.py:44`) sólo ofrece **`ADMIN`** y **`USER`**. El permiso acepta
`OPERACIONES` y `SUPERVISOR`, pero **no hay forma normal de asignarlos**, porque
no están en el catálogo de choices. En producción: **1 ADMIN, 4 USER** — hoy
sólo el ADMIN puede revisar propuestas.

No es «falta el rol». Es **«el guardia ya sabe reconocer tres credenciales y la
imprenta sólo emite dos»**.

---

## 1. Gobierno — Jefe de Operaciones

### Nombre canónico recomendado

**`OPERACIONES`** — ya es el que `ROLES_GESTION` espera. Inventar
`JEFE_DE_OPERACIONES` obligaría a tocar `campo/permissions.py`, que hoy cubre
otro dominio con el mismo conjunto, y a mantener dos listas que deberían ser
iguales. El propio módulo advierte contra eso: *«Se importa en vez de copiarse:
dos listas de roles que deberían ser iguales terminan divergiendo.»*

### Relación con `Profile.ROLES`

| | |
|---|---|
| Hoy | `(("ADMIN","ADMIN"), ("USER","USER"))` |
| Haría falta | agregar `SUPERVISOR` y `OPERACIONES` |
| Efecto colateral a vigilar | `Profile.save()` deriva `is_organization_admin = (role == "ADMIN")`. Un `OPERACIONES` quedaría **no-admin** y aun así pasaría `EsJefeDeOperaciones` — **que es exactamente lo que se busca**: revisar sin administrar. |

> **No es «sólo cambiar un choice».** Cambiarlo sin mirar el resto deja al nuevo
> rol sin poder entrar por ningún lado. Ver §8 para la lista completa.

### Matriz de roles

| Rol | Consultar propuestas | Revisar | Aceptar | Modificar | Rechazar | Ejecutar | Administrar |
|---|---|---|---|---|---|---|---|
| **ADMIN** | sí | sí | sí | sí | sí | **NO** | sí |
| **SUPERVISOR** | sí | sí | sí | sí | sí | **NO** | no |
| **OPERACIONES** (Jefe de Op.) | sí | sí | sí | sí | sí | **NO** | no |
| **USER** | **no** | no | no | no | no | **NO** | no |
| **Supervisor NOC IA** | — (escribe) | **no** | no | no | no | **NO** | no |

**«Ejecutar» es NO para todos**, y no por política: `supervisor.ejecutar_propuesta()`
**levanta siempre** `EjecucionNoPermitida`. Es el único camino declarado hacia la
ejecución, y no ejecuta.

### Qué NO puede hacer el Jefe de Operaciones

Crear propuestas a mano (las crea el ciclo con evidencia) · cambiar
`evidencia`, `tipo_senal` u `origen` · reabrir una propuesta ya revisada ·
ejecutar · mover el kill switch (eso es `autonomia_operador`, otro rol y otra
capa) · cambiar niveles de autonomía · ver propuestas de otra organización.

### Reservado a ADMIN

Asignar el rol `OPERACIONES` a un perfil · administrar la organización ·
`is_organization_admin`.

### Cómo queda registrado el revisor

`revisado_por` (FK a `Profile`) + `revisado_en` + `resultado`. Y
`supervisor.revisar()` **exige un `actor` que no puede ser `None`**: una
transición sin persona detrás **no es representable**.

### Tenant isolation

Tres capas, y hay que decir dónde falla una:

| Capa | Estado |
|---|---|
| Queryset (`org=request.org`) | sí |
| `misma_organizacion(obj, request)` → **404, no 403** | sí — un 403 confirmaría que el id existe |
| **RLS en base** | **sí** en las 6 tablas `operaciones_*` (RLS + FORCE + 2 políticas) |
| **RLS en `campo_*`** | **NO** — ver §3 |

### Cómo se impide que un USER revise

`permission_classes = [EsJefeDeOperaciones]` en las cuatro vistas, más la
comprobación de `profile` y `org` en la sesión. Un `USER` recibe 403 con
mensaje explícito.

---

## 2. Deduplicación

### Lo que hay hoy

```python
def _ya_propuesta(org, senal):
    return PropuestaSupervisor.objects.filter(
        org=org, tipo_senal=senal.tipo,
        origen_tipo=senal.origen_tipo, origen_id=senal.origen_id,
        estado=PropuestaSupervisor.PROPUESTA,
    ).exists()
```

Clave efectiva: **`(org, tipo_senal, origen_tipo, origen_id)` filtrando sólo
`estado='propuesta'`**.

### El hueco, medido contra el diseño

| Caso | Hoy | M09-C §5 pedía |
|---|---|---|
| Ya hay una en `propuesta` | no crea otra ✔ | reutilizar ✔ |
| **La anterior fue `rechazada`** | **crea otra en el siguiente ciclo** | no volver a preguntar dentro de la ventana |
| La anterior `expiró` | crea otra ✔ | crear nueva ✔ |
| La anterior fue `aceptada` y el hecho sigue | crea otra | reabrir citando la anterior |

**Consecuencia real:** el Jefe rechaza «revisar el caso #123», y al día
siguiente la propuesta vuelve idéntica. Rechazar es una decisión; repetir la
pregunta la ignora. Es el mismo mecanismo que llenó `acciones_propuestas` con
36 pendientes sin revisar — que el propio `_ya_propuesta` cita como motivo de
existir.

### Clave de deduplicación propuesta

```
(organization_id, tipo_senal, origen_tipo, origen_id, ventana)
```

**`ventana` no es tiempo de reloj: es el período en que la misma situación
cuenta como la misma.** Se deriva, no se almacena como fecha libre:

| Señal | Ventana | Por qué |
|---|---|---|
| `caso_abierto_antiguo` | día | la antigüedad avanza a diario |
| `caso_en_riesgo_sla` | hasta que cambie el deadline de M04 | el hecho es el deadline |
| `actividad_vencida`, `compromiso_por_vencer` | día | |
| `actividad_sin_responsable`, `actividad_bloqueada` | mientras dure la condición | no es periódica |
| `dependencia_pendiente` | mientras dure la arista | |
| `orden_sin_programar` | **semana** | la unidad de planificación es `ProgramacionSemanal` |
| `orden_con_riesgo_operacional` | día programado | |

**No se incluye `estado` en la clave** — incluirlo es justo lo que produce el
defecto de arriba. El estado entra en la **regla de decisión**, no en la
identidad.

**`conocimiento_version` tampoco entra en la clave.** Si cambia la regla, el
hecho sigue siendo el mismo hecho; lo que cambia es la recomendación, y eso se
resuelve actualizando la propuesta viva, no creando otra.

### Reglas (A–F)

- **A · mismo evento:** coinciden los cinco componentes.
- **B · nueva propuesta:** cambia la ventana, o la anterior expiró, o la
  anterior fue aceptada y la condición **persiste** (reapertura citando la
  previa).
- **C · reutilizar:** hay una en `propuesta` → se **actualiza la evidencia** y
  se recalcula prioridad; no se crea otra ni se pierde la antigüedad.
- **D · reabrir:** sólo desde `aceptada` con condición persistente, y como
  **propuesta nueva** que cita la anterior. Un estado revisado no vuelve a
  `propuesta`.
- **E · expira:** pasa `expira_en` (hoy `DIAS_VIGENCIA_PROPUESTA = 7`) o el
  origen se cierra/cancela. `expirar_vencidas()` ya existe.
- **F · cambio de evidencia:** si cambia el **hecho** (la OT pasó de `asignada`
  a `en_sitio`), la propuesta vigente **se cancela** — ya no describe la
  realidad. Si sólo cambia la **magnitud** (de 8 a 9 días), se **actualiza**.
  La distinción: ¿sigue siendo verdad la frase del `accion_propuesta`?

**No se crea índice ni constraint en este paso.** Ver §8-I.

---

## 3. `orden_sin_programar`

### La condición implementada hoy

```python
OrdenTrabajo.objects.filter(org=org,
                            programada_para__isnull=True,
                            estado_operativo=OrdenTrabajo.ASIGNADA)
```

### Verificación contra la máquina de estados real

`campo/services/transiciones.py:19-32`:

```
ASIGNADA             -> {EN_CAMINO, EN_SITIO, CANCELADA}
EN_CAMINO            -> {EN_SITIO, CANCELADA}
EN_SITIO             -> {COMPLETADA_CAMPO, CANCELADA}
COMPLETADA_CAMPO     -> {CERRADA, CORRECCION_REQUERIDA}
CORRECCION_REQUERIDA -> {EN_CAMINO, EN_SITIO, CANCELADA}
CERRADA              -> {}
```

> **Ninguna transición vuelve a `ASIGNADA`.** Y `iniciada_en` sólo se escribe al
> pasar a `EN_CAMINO`/`EN_SITIO` (`transiciones.py:293`).
>
> **Por lo tanto `estado_operativo = ASIGNADA` ya implica `iniciada_en IS
> NULL`.** La condición extra que propuse en M09-C **es redundante** y la
> retiro: agregarla no cierra nada y sugiere una protección que la máquina de
> estados ya da.

Esto también descarta, por construcción: `cancelada`, `completada`, `cerrada`,
`correccion_requerida` y cualquier `vuelta` > 1 — ninguna es `ASIGNADA`.

### El hueco que **sí** es real

`ProgramacionOrden` y `programada_para` son **dos cosas distintas y nada las
sincroniza** — lo dice el propio modelo (`operaciones/models.py:400-411`):

> *`ProgramacionOrden` = lo que se PLANIFICÓ el viernes anterior.
> `OT.programada_para` = lo que RIGE ahora mismo.*

Una OT puede estar **en el plan semanal** (`ProgramacionOrden` en `planificada`
o `confirmada`) con `programada_para` todavía en NULL. Hoy la señal
**dispararía**, y propondría programar algo que ya está programado.

**No es hipotético:** `programada_para` está en **0 de 3** órdenes; el campo
existe y nunca se usó. En cuanto M03 empiece a planificar, ese es el primer
falso positivo que aparece.

### Condición final

```
estado_operativo = 'asignada'
AND programada_para IS NULL
AND NOT EXISTS (ProgramacionOrden de esta OT
                con estado IN ('planificada','confirmada'))
```

`reprogramada` y `cancelada` **no** cuentan como programación vigente.

### Las tres capas, separadas

**HECHO**
> «Existe una OT en estado `asignada`, sin `programada_para` y sin línea vigente
> en el plan semanal.»

**NO PODEMOS CONCLUIR**
> Que esté **atrasada** — no hay fecha comprometida contra la cual medir atraso.
> Que alguien **omitió** programarla. Que sea **urgente**. Cuándo **debería**
> programarse. A quién **asignarla**.

**PROPUESTA**
> «Revisar y programar la OT-NNNN.» · Módulo **M03** · nivel **1** · revisa el
> Jefe de Operaciones.

**Resultado hoy: 0 señales** (las 3 OT están `en_sitio`/`completada_campo`).

---

## 4. `programacion_sin_publicar`

### ¿Existe forma de demostrar «publicada»?

**Sí.** `ProgramacionSemanal` tiene los tres elementos:

| Campo | |
|---|---|
| `estado` | `borrador` / `publicada` / `cerrada` |
| `publicada_en` | `DateTimeField(null=True)` |
| `publicada_por` | FK a `Profile` |

**No hay que inventar nada.** La transición `borrador → publicada` es
demostrable, con fecha y con persona.

### Veredicto: **IMPLEMENTABLE CON CONDICIÓN**

- **Condición objetiva:** `estado = 'borrador'` **y** `semana_inicio <=
  hoy` — la semana ya empezó y el plan sigue en borrador.
- **Evidencia:** `semana_inicio`, `estado`, `publicada_en` (NULL), `now()`.
- **NO puede concluir:** que alguien se olvidó; que el plan esté completo o
  vacío; que haya órdenes esperando.
- **Módulo dueño:** M03. **Nivel 1.**
- **Lo que falta:** el tipo no está en `TIPOS_SENAL` → **cambio de choice +
  migración** (§8-B/C).
- **Datos hoy:** `operaciones_programacion_semanal` = **0 filas** → no
  dispararía. No es impedimento para definirla.

---

## 5. `dato_incompleto`

### El riesgo: que sea un comodín

Una señal llamada «falta un dato» puede justificar cualquier cosa. Se cierra
partiéndola en tres situaciones que **no son la misma**:

| Situación | Qué es | Qué se hace |
|---|---|---|
| **`dato_no_disponible`** | el módulo de origen **nunca se pobló**: `operaciones_disponibilidad` con 0 filas | **no es una señal.** Es una condición de cobertura del Supervisor. Se informa en el resumen del ciclo, no como propuesta. Emitir una propuesta por cada tabla vacía sería ruido estructural. |
| **`dato_incompleto`** | el registro **existe** y le falta un campo que **su propio modelo declara esperable**: OT sin `tipo_trabajo_version`, actividad con `origen_id` que no resuelve | **señal informativa, nivel 0.** No recomienda: deja constancia de que un registro no permite evaluar su condición. |
| **`dato_contradictorio`** | dos fuentes afirman cosas incompatibles: OT `cerrada` con `cerrada_en` NULL; `ProgramacionOrden` `confirmada` para una OT `cancelada` | **ninguna propuesta, y ninguna interpretación.** Es un defecto de integridad: va a M10 (gobierno/calidad), no a la cola del Jefe de Operaciones. |

### Reglas que lo cierran

1. **Sólo se emite sobre un registro concreto** — nunca sobre «el sistema».
2. **Debe nombrar el campo exacto y su modelo.** «Falta información» no es
   evidencia; «`campo_orden_trabajo.tipo_trabajo_version` es NULL en OT-1842,
   leído a las 22:40» sí lo es.
3. **Sólo sobre campos que el modelo declara esperables** para evaluar una
   señal — no sobre cualquier campo opcional.
4. **Nivel 0 siempre.** No propone, no prioriza, no tiene revisor.
5. **Nunca sustituye a una propuesta.** Si falta el dato para evaluar, se emite
   ésta **en lugar de** la otra, no además.

### ¿Señal de M09 o calidad de datos transversal?

**Las dos, separadas:**
- **`dato_incompleto` como señal nivel 0 de M09** — acotada a «este registro no
  me deja evaluar esta señal». Es del Supervisor porque nace de su evaluación.
- **`dato_contradictorio` como calidad transversal de M10** — no depende de que
  M09 mire; es un defecto que existe igual.

---

## 6. Las 8 señales existentes

| Señal | Estado | Datos necesarios | ¿Produce hoy? | Condición objetiva | Evidencia mínima | Riesgo de falso positivo | Corrección | Dueño |
|---|---|---|---|---|---|---|---|---|
| `caso_abierto_antiguo` | **IMPLEMENTABLE** | `case` (197 filas) | **sí** — 128 abiertos | abierto y `created_at < now()−7d` | id, status, created_at, días | **bajo**: «antiguo» es medición | ninguna | M01 |
| `actividad_vencida` | **IMPLEMENTABLE** | `operaciones_actividad` (**0**) | no | `vence_en < now()` y no cerrada | id, vence_en, estado | bajo | ninguna | M02 |
| `actividad_sin_responsable` | **IMPLEMENTABLE** | ídem (**0**) | no | `responsable IS NULL` y abierta | id, responsable NULL | **medio**: puede ser deliberado en una cola sin asignar | citar si hay novedad asociada | M02 |
| `actividad_bloqueada` | **IMPLEMENTABLE** | ídem (**0**) | no | `estado='bloqueada'` | id, motivo_bloqueo | **bajo**: la causa está **declarada** | ninguna | M05 |
| `compromiso_por_vencer` | **IMPLEMENTABLE** | ídem (**0**) | no | `tipo='compromiso'` y vence en 24 h | id, vence_en, ventana | bajo | ninguna | M02 |
| `dependencia_pendiente` | **IMPLEMENTABLE** | ídem (**0**) | no | `depende_de` abierta | ambas actividades | bajo | ninguna | M02 |
| `orden_sin_programar` | **IMPLEMENTABLE CON CONDICIÓN** | `campo_orden_trabajo` (3) + `programacion_orden` (**0**) | no (0 en `asignada`) | §3 | estado, `programada_para` NULL, ausencia en plan | **ALTO hoy**: falta el `NOT EXISTS` del plan | **§3 — obligatoria** | M03 |
| `orden_con_riesgo_operacional` | **NO IMPLEMENTABLE ACTUALMENTE** | `operaciones_disponibilidad` (**0**) | **no** | OT programada + técnico declarado ausente | OT, asignación, disponibilidad | n/a | requiere que M03 declare disponibilidad | M03 |

**No se agregan señales para completar la lista.** Las dos nuevas
(`programacion_sin_publicar`, `dato_incompleto`) se definen en §4 y §5 y quedan
fuera hasta la migración de choices.

---

## 7. Autonomía — reconfirmado, sin cambios

M09-C.1 **no toca** los niveles. M09 sigue siendo:

```
detectar → evidenciar → recomendar → esperar revisión humana
```

**No ejecuta. No llama a WispHub. No llama a SmartOLT. No cierra casos. No
modifica tickets. No modifica programación real.**

Y no es una promesa: `supervisor.ejecutar_propuesta()` **levanta siempre**, el
estado `ejecutada` **no existe**, `accion_propuesta_ref` queda vacío, y M09 **no
abre permiso** en ninguna de las dos puertas de la frontera del paso 10.14A.

---

## 8. Cambios necesarios antes de M09-D

| # | Tipo | Qué | Por qué |
|---|---|---|---|
| 1 | **B · choice** | `Profile.ROLES` += `SUPERVISOR`, `OPERACIONES` | el permiso ya los acepta; el catálogo no los emite |
| 2 | **C · migración** | `AlterField` de `Profile.role` | choices cambia el estado de migraciones |
| 3 | **D · permisos** | ninguno nuevo | `EsJefeDeOperaciones` y `ROLES_GESTION` ya existen |
| 4 | **G · frontend** | selector de rol al editar un perfil | si sólo ofrece ADMIN/USER, el rol nuevo es inalcanzable desde la UI |
| 5 | **B · choice** | `TIPOS_SENAL` += `programacion_sin_publicar`, `dato_incompleto` | §4 y §5 |
| 6 | **C · migración** | `AlterField` de `tipo_senal` | ídem |
| 7 | **A · modelo** | campo `ventana` (o clave derivada) en `PropuestaSupervisor` | §2: hoy no se puede distinguir «misma semana» de «otra semana» |
| 8 | **I · índice** | único parcial sobre la clave de dedup para estados vivos | que la unicidad la garantice la base, no el `exists()` — que tiene carrera entre dos ciclos |
| 9 | **J · sin cambio** | condición de `orden_sin_programar` | es una consulta: `NOT EXISTS` sobre `ProgramacionOrden`. Sin modelo ni migración |
| 10 | **J · sin cambio** | regla de dedup por estado revisado | lógica en `_ya_propuesta` |
| 11 | **F · endpoint** | ninguno nuevo | las cuatro rutas ya existen |
| 12 | **H · auditoría** | ninguno nuevo | `operaciones/auditoria.py` ya existe |
| 13 | **E · RLS** | **`campo_*`: 7 tablas sin RLS ni políticas** | dos señales leen `campo_orden_trabajo`; hoy el aislamiento por organización depende **sólo** del queryset de Django. Las 6 tablas `operaciones_*` sí tienen RLS+FORCE+2 políticas. **Es una asimetría medida, no una sospecha** |
| 14 | **J · sin cambio** | frontera externa e idempotencia | M09 no produce efectos externos |

> **Ninguno implementado en este paso.**
>
> El nº 13 excede M09: son 69 de 135 tablas de `public` sin ninguna política.
> Se reporta porque **afecta a dos señales de M09**, no para resolverlo aquí.

---

## 9. Criterio de cierre

| Requisito | Estado |
|---|---|
| Diseño claro del revisor humano | **sí** — rol `OPERACIONES`, matriz, permiso ya existente, hueco acotado a un choice |
| Deduplicación definida | **sí** — clave de 5 componentes, ventana por señal, reglas A–F, defecto actual identificado |
| `orden_sin_programar` sin falsos positivos | **sí** — condición final en §3; se retira la parte redundante y se agrega la que sí hace falta |
| `programacion_sin_publicar` definida o descartada | **sí — definida.** `estado` + `publicada_en` + `publicada_por` existen |
| `dato_incompleto` con semántica cerrada | **sí** — partida en tres, con cinco reglas y nivel 0 |
| Cada señal con evidencia y dueño | **sí** — las 8, más las 2 nuevas |
| Sin ambigüedad sobre qué ejecuta M09 | **sí** — nada, y el único camino declarado levanta excepción |

# DECISIÓN: **GO PARA M09-D**

Con estas cuatro condiciones, que son de implementación y no de diseño:

1. **Agregar `SUPERVISOR` y `OPERACIONES` a `Profile.ROLES`** (+ migración +
   selector en el frontend). Sin esto, sólo el único ADMIN puede revisar.
2. **Corregir `orden_sin_programar`** con el `NOT EXISTS` sobre
   `ProgramacionOrden`. Es el falso positivo que aparecerá en cuanto M03
   empiece a planificar.
3. **Arreglar la deduplicación ante estados revisados.** Hoy una propuesta
   rechazada vuelve al día siguiente — el mismo defecto que llenó
   `acciones_propuestas` con 36 pendientes.
4. **Decidir sobre la RLS de `campo_*`** antes de que M09 lea esas tablas en
   producción: hoy el aislamiento por organización ahí no lo da la base.

Las dos señales nuevas (`programacion_sin_publicar`, `dato_incompleto`) quedan
**definidas y fuera del alcance** hasta su migración de choices: son deseables,
no bloqueantes.

**Producción intacta. Kill switch DETENIDO. Cero llamadas externas.**

**Me detengo. Espero revisión.**
