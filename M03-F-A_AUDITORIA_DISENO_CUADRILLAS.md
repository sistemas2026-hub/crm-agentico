# M03-F-A — Auditoría y diseño de cuadrillas

**Fecha:** 2026-09-18
**Alcance:** auditoría y diseño. **0 código, 0 modelos, 0 migraciones, 0 endpoints, producción solo `SELECT`.**

---

## RESUMEN EJECUTIVO

# S · NO-GO para M03-F-B

**[MEDIDO]** No porque falte estructura —la hay, y está declarada— sino porque
**el concepto de cuadrilla no existe todavía en la operación real**:

```
órdenes en producción ........ 3
asignaciones ................. 3
personas distintas asignadas . 1     ← carlos.tecnico@rapilink.com
personas por orden ........... 1, en las tres
teams ........................ 0 filas
```

> **Nunca ha existido una cuadrilla de dos o más personas en producción.** Toda
> regla que M03-F-B implementara —líder obligatorio, mínimo de integrantes,
> reemplazo, disponibilidad del grupo— se escribiría **sin un solo caso que la
> ejercite**.

### Dos premisas del encargo que la medición desmiente

**[MEDIDO] 1. `OrdenTrabajo.tecnico_lider` NO EXISTE.** El encargo pide auditarlo
(§3). Lo que hay es otra cosa:

| Lo que el encargo supone | Lo que hay |
|---|---|
| `OrdenTrabajo.tecnico_lider` como campo | **no existe** |
| — | `OrdenTrabajo.tecnico_principal`: una **`@property`** (`campo/models.py:307`) que lee `AsignacionTrabajo` |
| — | `tecnico_lider`: un **valor** de `AsignacionTrabajo.rol` |

> **Por eso no puede haber divergencia entre los dos: uno se deriva del otro.**
> La propiedad lo dice en su propio docstring: *"Fuente única de verdad: obtiene
> el responsable principal desde AsignacionTrabajo."*

**[MEDIDO] 2. `AsignacionTrabajo.rol` NO es texto libre.** Es un **catálogo
cerrado** (`ROLES_CUADRILLA`, 5 valores) desde el 15/09/2026, y el comentario del
modelo documenta **exactamente la divergencia que el encargo describe** — ya
corregida:

> *"CATALOGO CERRADO (15/09/2026). Antes era texto libre con la lista solo en el
> help_text, y ya habia divergido: las 3 asignaciones de produccion dicen
> 'tecnico_lider', que no estaba entre los cuatro documentados."*

### Y una respuesta que el propio repositorio ya daba

**[MEDIDO]** `operaciones/models.py:19`, escrito en M09-D:

```
LO QUE SE REUTILIZA, Y NO SE VUELVE A CREAR
    campo.OrdenTrabajo        el desplazamiento fisico. No se crea otra OT.
    campo.AsignacionTrabajo   la cuadrilla. Ya soporta N personas con rol.
```

> **El código ya declara que `AsignacionTrabajo` ES la cuadrilla.** No es una
> inferencia mía: está escrito, y el módulo `operaciones` entero se construyó
> sobre esa premisa.

---

## A · Inventario de estructuras existentes

**[MEDIDO]** Barrido por los nueve términos del §1, sobre modelos, tablas,
serializers, views, urls, servicios, permisos, admin, tests y frontend:

| Término | Qué existe | Estado |
|---|---|---|
| **cuadrilla** | **19 apariciones, todas en texto**: docstrings, `verbose_name` de la app, `ROLES_CUADRILLA`. **Ninguna entidad** | **solo palabra** |
| **crew** | **0** | no existe |
| **team** | `common.Teams` + M2M en `accounts`, `cases`, `RoutingRule`, `approvals` | **vivo, pero ajeno a campo** |
| **lider** | valor `tecnico_lider` de `AsignacionTrabajo.rol` | **valor, no entidad** |
| **tecnico_lider** | idem | valor |
| **asignacion** | **`campo.AsignacionTrabajo`** | **la estructura real** |
| **miembro** | **0** | no existe |
| **vehiculo / placa / moto** | **0 modelos, 0 tablas.** Los 103 aciertos de "moto" son **`motor`** (el motor de IA): `MOTOR_URL`, `motor_user`, `motor_alcanzado`… | **no modelado** |
| **zona** | `ProgramacionOrden.zona` y `DisponibilidadTecnico.zona`, **texto libre sin catálogo** | informativo |
| **disponibilidad** | `operaciones.DisponibilidadTecnico` | vivo, **0 filas** |
| **jornada** | `(org, dia)` sobre `ProgramacionOrden` — M03-E2 | vivo, **0 filas** |
| **orden** | `campo.OrdenTrabajo` | vivo, 3 filas |

**[MEDIDO]** Tablas que coincidan con `vehic*`, `cuadrilla*`, `crew*`, `moto*` en
producción: **ninguna**.

---

## B · `AsignacionTrabajo` — análisis completo

**[MEDIDO]** `campo/models.py:317`:

| Aspecto | |
|---|---|
| **campos** | `orden` (FK), `profile` (FK), `rol`, `es_principal`, `asignado_en` + los de `BaseModel` |
| **`rol`** | **catálogo cerrado**: `tecnico`, `tecnico_lider`, `ayudante`, `chofer`, `supervisor` |
| **cardinalidad** | **N personas por orden** — `related_name="asignaciones"` |
| **constraints** | `unique(orden, profile)` · `unique(orden) WHERE es_principal` → **un solo principal por orden** |
| **quién crea/modifica** | `despacho.asignar(...)`, vía `POST /api/campo/trabajos/<pk>/asignar/` con `ROLES_GESTION`; y el admin de Django |
| **quién consume** | `OrdenTrabajo.tecnico_principal` · `supervisor._ordenes_en_riesgo` (H-05) · `campo.PuedeAccederOrden` · serializers |
| **¿técnico individual o cuadrilla?** | **ambos**: una fila = una persona; el conjunto de filas de una orden = la cuadrilla |
| **¿varios técnicos?** | **sí**, con rol cada uno |
| **¿fecha/jornada propia?** | **NO** — la fecha vive en la orden (`programada_para`) y en la línea de plan |
| **¿líder?** | **sí**, por dos vías a la vez: `es_principal` (constraint) y `rol=tecnico_lider` (catálogo) |
| **¿vigencia?** | **NO** — no hay `desde`/`hasta` ni `activa` |
| **¿histórico?** | **NO en la tabla**; sí en `EventoTrabajo` (`asignacion` / `reasignacion`) |
| **tenant isolation** | **solo por la orden**: `AsignacionTrabajo` **no tiene `org`** propio |
| **RLS** | **NO** — `relrowsecurity = false`, **0 políticas** |
| **API real** | **sí**: `AsignarTrabajoView` |

### Lo que ya hace de cuadrilla, sin llamarse así

**[MEDIDO]** `campo/permissions.py::PuedeAccederOrden`:

```python
# Técnicos de campo: solo órdenes donde estén asignados
esta_asignado = orden.asignaciones.filter(profile=profile).exists()
```

> **La asignación ya es la frontera de autorización del trabajo de campo.** Un
> técnico ve una orden **si y solo si** está en `AsignacionTrabajo`. Cualquier
> entidad nueva de cuadrilla tendría que replicar eso o convivir con ello.

### Los dos huecos reales

**[MEDIDO]**

| # | Hueco | Consecuencia |
|:--:|---|---|
| **H-1** | **`es_principal` y `rol=tecnico_lider` son dos formas de decir lo mismo**, y **nada las obliga a coincidir** | se puede crear un `ayudante` con `es_principal=True`, o dos `tecnico_lider` de los cuales solo uno es principal |
| **H-2** | **la cuadrilla no tiene identidad**: existe solo como "el conjunto de filas de esta orden" | no se puede decir *"la cuadrilla de Carlos y Luis"*, ni reutilizarla mañana, ni darle un vehículo o una zona |

**[MEDIDO]** H-1 no es hipotético: **las 3 asignaciones de producción son
`rol=tecnico_lider` + `es_principal=true`** — coinciden, pero porque las escribió
un mismo importador, no porque algo lo garantice.

---

## C · `tecnico_lider` / `tecnico_principal`

**[MEDIDO]**

```python
# campo/models.py:307
@property
def tecnico_principal(self) -> Profile | None:
    """Fuente única de verdad: obtiene el responsable principal desde AsignacionTrabajo."""
    asig = self.asignaciones.filter(es_principal=True).select_related("profile__user").first()
    return asig.profile if asig else None
```

| Pregunta del §3 | Respuesta medida |
|---|---|
| ¿quién lo escribe? | **nadie**: es derivado. Lo que se escribe es `AsignacionTrabajo.es_principal`, desde `despacho.asignar` |
| ¿quién lo lee? | `campo/serializers.py` (2 veces), `campo/admin.py`, `despacho.asignar`, **y H-05** (`supervisor._ordenes_en_riesgo`) |
| ¿representa responsable individual? | **sí** — una persona, garantizada única por constraint |
| ¿coexiste con `AsignacionTrabajo`? | **no coexiste: SE DERIVA de él** |
| ¿hay divergencia? | **imposible por construcción.** La divergencia real es **H-1**: `es_principal` vs. `rol=tecnico_lider` |
| ¿debe seguir existiendo como dato de la OT? | **la pregunta no aplica: no es un dato de la OT.** Es una propiedad calculada, y quitarla rompería H-05 y dos serializers sin ganar nada |

**[DISEÑO]** **No se modificó.** Y la recomendación es no tocarla: es el único
sitio donde "el responsable" está definido sin ambigüedad.

---

## D · `Teams`

**[MEDIDO]** `common/models.py:774`:

```python
class Teams(BaseModel):
    name = CharField(100)
    description = TextField()
    users = ManyToManyField(Profile, related_name="user_teams")
    org = ForeignKey(Org)
```

| Aspecto | |
|---|---|
| campos | nombre, descripción, miembros (M2M a `Profile`), organización |
| **líder** | **NO** |
| **vehículo / zona / disponibilidad** | **NO** |
| **RLS** | **SÍ** — `enabled`, `forced`, **2 políticas** |
| **filas en producción** | **0** |
| **escritores en código de producción** | **ninguno** — solo tests |
| **lectores** | `accounts` (`Account.teams`), `cases` (`Case.teams`), `RoutingRule.target_team`, `cases.approvals` |
| **¿lo usa `campo` u `operaciones`?** | **NO — 0 referencias** |

### ¿Abandonada, piloto o activa?

**[DISEÑO]** **Ninguna de las tres, exactamente.** Es una estructura **viva en el
dominio comercial** —cuatro consumidores reales la referencian— y **sin una sola
fila**. Está cableada y sin estrenar.

**[RIESGO] Y eso es justo lo que la descarta como cuadrilla:** reutilizarla
significaría que `Account.teams`, `Case.teams`, `RoutingRule.target_team` y el
flujo de aprobaciones empezaran a ver cuadrillas de campo entre sus equipos
comerciales. **Un `Teams` que a veces es un equipo de ventas y a veces una
cuadrilla de fibra no se puede filtrar sin un discriminador** — que sería un
campo nuevo, o sea una migración.

**[MEDIDO]** Lo único que `Teams` tiene y `AsignacionTrabajo` no: **RLS** (§L).

---

## E · Definición operacional sustentada

**[DISEÑO]** A partir del código y la documentación, **sin inventar política**:

| Concepto | ¿Está sustentado hoy? | Por qué |
|---|:--:|---|
| **cuadrilla ad-hoc** | **SÍ** | es exactamente lo que `AsignacionTrabajo` representa: las personas de **esta** orden, con su rol. El código lo declara: *"la cuadrilla. Ya soporta N personas con rol"* |
| **técnico individual** | **SÍ** | una fila; y el caso real: las 3 órdenes tienen una persona |
| **líder** | **SÍ**, con ambigüedad | `es_principal` (constraint) **y** `rol=tecnico_lider` (catálogo) — ver **H-1** |
| **auxiliar** | **SÍ como rol** | `ayudante`, `chofer` están en el catálogo, **sin usar** |
| **cuadrilla estable** | **NO** | **no hay nada** que sobreviva a una orden: sin identidad, sin nombre, sin reutilización |
| **vehículo** | **NO** | 0 modelos, 0 tablas, 0 campos |
| **zona** | **parcial** | existe como texto libre en dos tablas, **sin catálogo** y **sin participar en ninguna decisión** |

> **[DISEÑO] Definición que el repositorio sí sostiene:**
>
> *Una cuadrilla, hoy, es **el conjunto de personas asignadas a una orden**, cada
> una con un rol del catálogo cerrado, con **una sola** marcada como principal.
> Nace con la orden y muere con ella: no tiene identidad propia.*

**[PENDIENTE]** Si el negocio quiere **cuadrillas estables** —que se nombren, se
reutilicen, tengan vehículo o zona— **eso es una entidad nueva**, y esa decisión
no está tomada.

---

## F · Relación con programación

**[DISEÑO]** El vínculo conceptual, y **solo eso**:

```
ProgramacionOrden  ──(orden)──>  OrdenTrabajo  ──(asignaciones)──>  Profile × N
        │                              │
     dia, secuencia              programada_para
```

**[MEDIDO]** Hoy **no hay ningún vínculo** entre la asignación y la programación:
`ProgramacionOrden` **no tiene FK a técnico ni a cuadrilla** —lo midió M03-A— y
`AsignacionTrabajo` **no tiene fecha**.

> **Se cruzan únicamente a través de la orden**, y eso ya es suficiente para
> H-05: `_ordenes_en_riesgo` une `programada_para` + `tecnico_principal` +
> `DisponibilidadTecnico`.

**[DISEÑO] Lo que una cuadrilla NO debe hacer, y el diseño lo respeta:**

| | |
|---|---|
| modificar `secuencia` automáticamente | **no** — E-1/E-2 ya decidieron que no hay reordenamiento automático |
| modificar `prioridad` automáticamente | **no** — E-6: `prioridad` no participa en nada |
| modificar SLA | **no** — el SLA ancla en `Case.created_at` y no lee nada de campo |

---

## G · Relación con disponibilidad

**[MEDIDO]** `DisponibilidadTecnico` es **individual**: FK a `Profile`, con
`fecha`, franja, `disponible` y `motivo`. **0 filas en producción.**

**[DISEÑO]** Una disponibilidad de cuadrilla **sería derivada**, no almacenada —
el mismo criterio que el modelo ya declara para la capacidad:

> *"Un numero de 'capacidad' depende de la disponibilidad, de la carga ya
> asignada… Guardarlo es garantizar que quede viejo la proxima vez que cualquiera
> de esos cinco cambie."*

**[PENDIENTE] Las tres preguntas del §8 no tienen respuesta en el repositorio:**

| Situación | ¿Qué debe pasar? |
|---|---|
| falta **un integrante** | **PENDIENTE** — ¿la cuadrilla sigue? ¿con qué mínimo? |
| falta **el líder** | **PENDIENTE** — ¿se promueve a otro? ¿se bloquea la orden? |
| falta **toda la cuadrilla** | **PENDIENTE** |

**[MEDIDO]** Lo único que el sistema hace hoy: **H-05 emite una señal** cuando el
**técnico principal** está ausente el día programado. **No propone reemplazo, y no
mira a los demás integrantes.** Eso es deliberado — M09 detecta y propone, no
ejecuta.

**No se inventó ninguna regla de reemplazo.**

---

## H · Vehículo

# [MEDIDO] NO MODELADO

```
modelos con Vehiculo / Moto / placa ....... 0
tablas vehic* / moto* en producción ....... 0
campos 'vehiculo' o 'placa' ............... 0
```

**[MEDIDO]** Los 103 aciertos de `moto` en el backend son **`motor`** — el motor
de IA (`MOTOR_URL`, `MOTOR_TENANT`, `motor_user`, `motor_alcanzado`,
`base_motor`). El único acierto de `placa` es igualmente ruido.

**[DISEÑO]** De las cuatro opciones del §9 —propiedad de la cuadrilla, del
técnico, recurso independiente, o no modelado— **solo D tiene evidencia: no
modelado.** Las otras tres requerirían inventar una estructura, y el encargo lo
prohíbe.

**[PENDIENTE]** Si el vehículo importa operativamente (una cuadrilla de fibra
normalmente tiene una moto o una camioneta asignada), **es una decisión y una
entidad nuevas**. No se diseñan aquí.

---

## I · Zona

**[MEDIDO]** Dos campos `zona`, y **no significan lo mismo**:

| | `ProgramacionOrden.zona` | `DisponibilidadTecnico.zona` |
|---|---|---|
| tipo | `CharField(128)`, texto libre | idem |
| `help_text` | **ninguno** | **`"Zona que cubre en esa franja. Vacío = cualquiera."`** |
| ¿catálogo? | **no** | **no** |
| ¿participa en asignación? | **NO** | **NO** |
| ¿participa en secuencia? | **NO** — E-7 lo dejó decidido | no aplica |
| ¿quién la lee para decidir? | **NADIE** | **NADIE** |

**[DISEÑO]** `DisponibilidadTecnico.zona` **es la única con semántica declarada**
—cobertura— y es la que una asignación por zona necesitaría. Pero con **texto
libre y sin catálogo**, *"Norte"* y *"norte"* son zonas distintas para la base.

**[MEDIDO]** Y M03-A ya había medido el contexto: **no existe catálogo de zonas**
en ningún sitio, y la agrupación geográfica de facto del negocio es el `router`
de WispHub — **otro identificador, en otro sistema**.

**No se inventó política de zonificación.**

---

## J · Permisos

**[DISEÑO]** **Se reutiliza `ROLES_GESTION` y nada más.**

```
ROLES_GESTION = {"ADMIN", "SUPERVISOR", "OPERACIONES"}
common.utils.ROLES = {"ADMIN", "SUPERVISOR", "OPERACIONES", "USER"}
```

**0 roles nuevos.** Ni `cuadrilla`, ni `lider`, ni `auxiliar`: **el rol dentro de
la cuadrilla ya es `AsignacionTrabajo.rol`**, que es un dato de la asignación, no
un permiso del sistema. Esa separación ya está hecha y es correcta.

**[MEDIDO] Y sigue sin haber a quién asignar los roles de gestión:** perfiles en
producción `{USER: 4, ADMIN: 1}` — **0 `SUPERVISOR`, 0 `OPERACIONES`**.

---

## K · Auditoría e historial

**[DISEÑO]** `EventoTrabajo` cubre **todo** lo que el §12 pide, **sin sistema
nuevo** — `tipo` es texto libre y `datos` es JSONB:

| Hecho | Superficie | ¿Existe hoy? |
|---|---|---|
| asignar / reasignar | `EventoTrabajo` `asignacion` / `reasignacion` | **SÍ**, con `{anterior, nuevo, rol, motivo}` |
| alta/baja de miembro | `EventoTrabajo` | cabe, **no implementado** |
| cambio de líder | `EventoTrabajo` | cabe; hoy se registra como `reasignacion` |
| asignar cuadrilla a OT | `EventoTrabajo` | cabe |
| retiro / reemplazo | `EventoTrabajo` | cabe |
| cambio de vehículo | — | **no aplica**: no hay vehículo |
| **creación de cuadrilla** | — | **no cabe**: `orden_id` es `NOT NULL`, y una cuadrilla estable no tiene orden |

**[RIESGO]** Ese último es el mismo obstáculo que M03-E5 encontró: **un evento sin
orden no se puede escribir.** Si el negocio quiere cuadrillas **estables**, su
ciclo de vida **no cabe en `EventoTrabajo`** y necesitaría `Activity` —que exige
declarar el `entity_type`, o sea migración— u otra superficie.

**[DISEÑO]** Para cuadrillas **ad-hoc** (las que existen hoy) no hay problema:
todo evento cuelga de su orden.

---

## L · Multi-tenant

**[MEDIDO]** El estado real, y **es el hallazgo de seguridad de este paso**:

| Tabla | `org_id` | RLS | FORCE | Políticas |
|---|:--:|:--:|:--:|:--:|
| `campo_orden_trabajo` | **sí** | **NO** | no | **0** |
| **`campo_asignacion_trabajo`** | **NO** | **NO** | no | **0** |
| `campo_evento_trabajo` | sí | **NO** | no | **0** |
| `profile` | sí | **NO** | no | **0** |
| `teams` | sí | **SÍ** | **sí** | **2** |
| `operaciones_disponibilidad` | sí | **SÍ** | **sí** | **2** |

**[MEDIDO]** **`AsignacionTrabajo` no tiene `org` propio**: su aislamiento es
**doblemente indirecto** — depende de la orden, y la orden **tampoco tiene RLS**.

**[RIESGO]** Una cuadrilla construida sobre `AsignacionTrabajo` **hereda cero
RLS**. Una construida sobre `Teams` la tendría. **Es el único argumento técnico a
favor de `Teams`**, y no alcanza para compensar el problema del §D.

**[MEDIDO]** **B-7 no lo resuelve**: la causa es `ORG_SCOPED_TABLES`
(`common/rls/__init__.py:34`), que **no lista ninguna tabla `campo_*`**.

**No se corrigió RLS en este paso** (§13 lo prohíbe). Solo se midió.

---

## M · Datos reales

**[MEDIDO]** Producción, solo `SELECT`, `read_only = True`:

```
asignaciones ................. 3
órdenes ...................... 3
personas distintas asignadas . 1        carlos.tecnico@rapilink.com (role USER)
personas por orden ........... 1  ×3    ← nunca 2 o más
roles usados ................. tecnico_lider ×3, todos es_principal=true
roles SIN usar ............... tecnico, ayudante, chofer, supervisor
órdenes sin asignación ....... 0
teams ........................ 0 filas
perfiles ..................... {USER: 4, ADMIN: 1}
disponibilidad ............... 0 filas
planes / líneas de plan ...... 0 / 0
```

### [MEDIDO] No existen datos suficientes, y lo digo explícitamente

| Pregunta | ¿Hay dato? |
|---|:--:|
| ¿cómo se compone una cuadrilla real? | **NO** — nunca hubo más de una persona |
| ¿qué roles se usan de verdad? | **parcialmente** — uno de cinco |
| ¿hay líder distinto del ejecutor? | **NO** — la misma persona es las dos cosas |
| ¿hay cuadrillas que se repitan? | **NO** — no hay con qué compararlas |
| ¿alguien usa `Teams`? | **NO** |
| ¿hay ausencias que fuercen un reemplazo? | **NO** — 0 disponibilidades |

**No se fabricó ningún dato.**

---

## N · Decisiones empresariales pendientes

| # | Decisión | ¿Crítica para F-B? |
|:--:|---|:--:|
| **F-1** | **¿La cuadrilla es ad-hoc (por orden) o estable (con identidad propia)?** De aquí cuelga todo lo demás | **SÍ** |
| **F-2** | **¿El líder es obligatorio?** Hoy `es_principal` lo permite ausente | **SÍ** |
| **F-3** | **¿`es_principal` y `rol=tecnico_lider` deben coincidir?** (H-1) | **SÍ** |
| F-4 | ¿Mínimo de integrantes? ¿Máximo? | sí, si F-1 = estable |
| F-5 | ¿Qué pasa si falta un integrante? ¿Y el líder? ¿Y toda la cuadrilla? | sí |
| F-6 | ¿Se puede cambiar de cuadrilla **durante la ejecución**? ¿Y después de `iniciada_en`? | sí |
| F-7 | ¿El **vehículo** se modela? ¿De quién es? | no bloquea |
| F-8 | ¿Hace falta un **catálogo de zonas**? | no bloquea |
| F-9 | ¿Los roles sin usar (`ayudante`, `chofer`, `supervisor`) son reales o aspiracionales? | no bloquea |
| F-10 | ¿El historial de una cuadrilla **estable** dónde vive, si `EventoTrabajo` exige una orden? | sí, si F-1 = estable |

**[PENDIENTE] Ninguna se decide aquí.**

---

## O · Recomendación de reutilización

# B · EVOLUCIONAR `AsignacionTrabajo` — condicionado a F-1

**[DISEÑO]** Por qué las otras tres no sirven:

| | Opción | Por qué se descarta / elige |
|---|---|---|
| **A** | reutilizar `AsignacionTrabajo` **tal cual** | **insuficiente solo si F-1 = estable.** Para ad-hoc **ya alcanza** — de hecho ya es eso |
| **B** | **evolucionar `AsignacionTrabajo`** | **elegida**: cubre H-1 sin entidad nueva, y es lo que el código ya declara que es la cuadrilla |
| **C** | reutilizar `Teams` | **descartada**: `Account`, `Case`, `RoutingRule` y aprobaciones ya dependen de ella; mezclarlas exigiría un discriminador → migración → y aun así confundiría dos dominios |
| **D** | **crear entidad nueva** | **solo si F-1 = estable.** Y entonces **no reemplaza** a `AsignacionTrabajo`: convive con ella, porque la asignación seguiría siendo la frontera de autorización (`PuedeAccederOrden`) |

**[DISEÑO] Lo decisivo:** `AsignacionTrabajo` **ya es la cuadrilla ad-hoc**, ya
soporta N personas con rol, ya tiene el líder por constraint y **ya es la frontera
de permisos del técnico**. Crear otra estructura al lado duplicaría las tres
cosas.

---

## P · Arquitectura propuesta

**[DISEÑO]** Dos caminos, **según F-1**, sin implementar ninguno:

### Si F-1 = **ad-hoc** (lo que el sistema ya hace)

```
OrdenTrabajo ──asignaciones──> AsignacionTrabajo (N)
                                  profile · rol · es_principal
```

Trabajo de F-B, **sin migración**:

1. **Cerrar H-1** en el servicio: que `es_principal=True` exija
   `rol=tecnico_lider`, o que el rol se derive de la marca. *(Regla de servicio,
   no constraint — cambiar el modelo sería migración.)*
2. **Operación de conjunto**: asignar/quitar varios a la vez, atómica, con lote
   en `EventoTrabajo` — **exactamente el patrón de M03-E5-B**.
3. **Lectura de cuadrilla** de una orden, y de una jornada.

### Si F-1 = **estable**

```
Cuadrilla (nueva)  ──miembros──> Profile (N), con rol y líder
     │                              vehículo? zona?
     └──se materializa en──> AsignacionTrabajo al asignarla a una OT
```

**[DISEÑO]** Incluso así, **`AsignacionTrabajo` no desaparece**: la cuadrilla
estable sería una **plantilla** que al asignarse escribe las filas de asignación,
que siguen siendo lo que el permiso y H-05 leen.

**[RIESGO]** Este camino **sí exige migración** —modelo nuevo, y probablemente
`Activity.ENTITY_TYPE_CHOICES` para su historial (§K)— y **F-A no lo autoriza**.

---

## Q · Pruebas para la futura implementación

**[DISEÑO]** Matriz propuesta, siguiendo el método ya establecido en M03:

| # | Prueba | Qué debe afirmar |
|:--:|---|---|
| 1 | técnico individual | una fila, `es_principal=True`, la orden lo reporta como principal |
| 2 | dos técnicos | dos filas, **un solo** principal (constraint) |
| 3 | líder + auxiliar | roles distintos, principal único |
| 4 | **H-1**: `ayudante` con `es_principal=True` | **rechazo** — o la regla que F-3 decida |
| 5 | cuadrilla estable | solo si F-1 lo aprueba |
| 6 | cuadrilla ad-hoc | la actual |
| 7 | cambio de líder | el anterior pierde `es_principal` **en la misma transacción**; `EventoTrabajo reasignacion` con `{anterior, nuevo}` |
| 8 | miembro no disponible | **H-05 no emite** (solo mira al principal) — fijar el hecho |
| 9 | **líder no disponible** | **H-05 emite** `orden_con_riesgo_operacional` |
| 10 | cambio de cuadrilla | todas las filas cambian **atómicamente**, con lote |
| 11 | aislamiento tenant | una persona de otra organización **no se puede asignar** |
| 12 | **concurrencia** | dos asignaciones simultáneas → un solo principal. **Verificar desarmando el lock** |
| 13 | historial | un evento por cambio, agrupables por lote |
| 14 | orden ya iniciada | ¿se puede cambiar la cuadrilla? → **F-6** |
| 15 | efectos externos | **0**, con el instrumento probado antes de leer su cero |
| 16 | `makemigrations --check` | **limpio** si F-1 = ad-hoc |

---

## R · Archivos que se modificarían en F-B

**[DISEÑO]** Si **F-1 = ad-hoc** (sin migración):

| Archivo | Cambio previsto |
|---|---|
| `campo/services/despacho.py` | **+1 servicio** `asignar_cuadrilla` (conjunto, atómico); regla de H-1 en `asignar` |
| `campo/serializers.py` | **+1** `CuadrillaSerializer` (lista de miembros) |
| `campo/despacho_views.py` | **+1 vista** de cuadrilla |
| `campo/urls.py` | **+1 ruta** |
| `campo/tests/test_m03f_cuadrilla.py` | **nuevo** — la matriz del §Q |

```
migraciones .... 0     modelos .... 0     roles .... 0
M09 ............ sin tocar     revisar_coherencia ... sin tocar
```

**[RIESGO]** Si **F-1 = estable**: **+1 modelo, +1 migración**, y probablemente
`common/models.py` para el `entity_type` del historial. **Eso excede lo que F-A
puede recomendar.**

**[MEDIDO]** En los dos casos, la guarda de rutas de M09-F **no se toca**: fija el
inventario de `operaciones`, y esto vive en `campo`.

---

## S · GO / NO-GO

# NO-GO para M03-F-B

**[MEDIDO]** Contra los siete criterios del encargo:

| # | Criterio | |
|:--:|---|:--:|
| 1 | **sabemos qué representa una cuadrilla** | **NO** |
| 2 | sabemos qué estructura evolucionar | **SÍ** — `AsignacionTrabajo` |
| 3 | no hay ambigüedad crítica sobre asignación | **NO** — H-1 sigue abierta |
| 4 | no se duplica `AsignacionTrabajo` | **SÍ** |
| 5 | decisiones empresariales identificadas | **SÍ** — F-1 … F-10 |
| 6 | el diseño respeta programación y secuencia | **SÍ** |
| 7 | **no requiere inventar datos** | **NO** |

**Fallan tres, y el encargo es explícito: *"Si falta una decisión empresarial
crítica: NO-GO"*.**

### Lo que convertiría esto en GO

**Tres firmas, y ninguna exige código:**

| | | Sin ella… |
|---|---|---|
| **F-1** | ¿ad-hoc o estable? | no se sabe si F-B es un servicio sin migración o un modelo nuevo |
| **F-2** | ¿el líder es obligatorio? | no se puede escribir la validación |
| **F-3** | ¿`es_principal` ≡ `rol=tecnico_lider`? | **H-1 queda viva**, y es la única ambigüedad real de la asignación |

**[DISEÑO]** Con F-1 = **ad-hoc** más F-2 y F-3, **F-B sería un paso corto y sin
migración**: cerrar H-1 y añadir la operación de conjunto, reusando el patrón de
M03-E5-B entero.

### Y lo que ninguna firma arregla

**[RIESGO]** **No hay datos.** Una persona, tres órdenes, una por orden, cero
teams, cero disponibilidades. **La primera cuadrilla real será la primera vez que
este código vea dos personas en una orden.**

> No es una objeción al paso —la estructura hace falta antes de que alguien pueda
> armar una cuadrilla— pero conviene saber que **F-B se validará contra datos
> sintéticos de principio a fin**, igual que M03-C, D y E.

**[RIESGO] Y sigue pendiente lo mismo que desde A-3.2:** no existe ningún perfil
`SUPERVISOR` ni `OPERACIONES` en producción. **Quien tendría que armar la
cuadrilla no tiene todavía con qué entrar.**

---

```
código ......... 0     modelos ....... 0     migraciones ... 0
endpoints ...... 0     roles ......... 0     decisiones tomadas ... 0
M09 ............ sin tocar     revisar_coherencia ... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
