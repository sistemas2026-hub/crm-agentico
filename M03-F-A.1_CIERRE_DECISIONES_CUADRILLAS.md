# M03-F-A.1 — Cierre de decisiones de cuadrillas

**Fecha:** 2026-09-18
**Alcance:** auditoría + diseño. **Sin implementar.**
**Veredicto F-B:** **NO-GO** (2 de 10 criterios fallan; 4 decisiones empresariales siguen abiertas)

---

## Resumen

```
Código modificado:     0      Modelos: 0   Migraciones: 0   Endpoints: 0
makemigrations --check:        "No changes detected"
Producción:            SIN CAMBIOS -- 15 claves, DIFERENCIAS: NINGUNA (solo SELECT, read_only)
Commit:                no

Mediciones nuevas:     6 (M1..M6) en contenedor aislado, sin credenciales de produccion
Hallazgo de seguridad: 1 bypass real -- reportado, NO parcheado (seccion K.4)
```

### Lo que cambia respecto de la recomendación preliminar de F-A

F-A recomendó `F-3 = es_principal ⇔ rol=tecnico_lider`. **La medición lo
contradice por dos caminos distintos**, y por eso F-3 no se puede cerrar como
venía propuesto:

| | [MEDIDO] |
|---|---|
| **Crear una OT con técnico** deja `rol='tecnico'` **+** `es_principal=True` | viola la equivalencia en la **primera** llamada (`despacho_views.py:158` llama `asignar()` **sin** `rol`) |
| **Asignar una segunda persona** deja al `tecnico_lider` **sin** principal y al `ayudante` **como** principal | la única vía de escritura soportada **produce activamente** la combinación que F-3 quiere prohibir |

**[RIESGO]** Declarar la equivalencia hoy convertiría en inválidos los 2 caminos
de escritura que existen. No es un ajuste: es un cambio de contrato de ambos.

---

## Método

**[MEDIDO]** Seis mediciones (M1–M6) sobre PostgreSQL 16 en contenedor aislado
(`pg-fa1`) con un runner desde `crm-agentico-backend:latest`. Credenciales de
producción visibles en el runner: **0** (medido con `env | grep -ci`, no
prometido). Entorno **eliminado** al terminar; el archivo de medición
**borrado** (verificado con `git status`: no quedó rastro).

Producción: **solo `SELECT`**, con `read_only = True` en la conexión.

---

## A. F-1 — Cuadrilla ad-hoc

### A.1 ¿Puede un conjunto de `AsignacionTrabajo` representar una cuadrilla sin entidad adicional?

**[MEDIDO] Sí, y la estructura ya lo hace.** `orden.asignaciones.all()` devuelve
N personas con rol. El propio repo ya lo declara, en
`operaciones/models.py:19`:

```
LO QUE SE REUTILIZA, Y NO SE VUELVE A CREAR
    campo.AsignacionTrabajo   la cuadrilla. Ya soporta N personas con rol.
```

**[MEDIDO]** Verificado contra la base: `M4-D` creó dos personas en la misma OT
sin error. `M5` creó una cuadrilla de 2 (principal + ayudante) y ambas
existen simultáneamente.

### A.2 ¿Cómo se identifica que varias asignaciones son del mismo grupo?

**[MEDIDO] Por `orden_id`. La clave de agrupación ya existe y es obligatoria**
(`orden_id` es `NOT NULL`, con FK e índice propio). No hay ninguna otra
agrupación en la tabla.

### A.3 ¿Existe hoy un campo que permita esa agrupación?

**[MEDIDO] Sí: `orden_id`.** Columnas reales de `campo_asignacion_trabajo`:

```
created_at · updated_at · id · rol · es_principal · asignado_en
created_by_id · profile_id · updated_by_id · orden_id
```

No hay `cuadrilla_id`, `grupo`, `lote`, `jornada_id` ni `vigente`.

### A.4–A.6 ¿Qué campo mínimo haría falta? ¿Migración? ¿Alternativa?

**[DISEÑO] Para una cuadrilla POR OT: ningún campo nuevo, ninguna migración.**
`orden_id` ya agrupa.

**[PENDIENTE] Para una cuadrilla que persiste ENTRE OTs** (las mismas 3
personas hacen 5 OTs el martes) **haría falta un agrupador nuevo**, y hoy no
existe. Dos alternativas sin modelo nuevo:

| Alternativa | Migración | Evaluación |
|---|:--:|---|
| **`lote` UUID dentro de `EventoTrabajo.datos`** (precedente real: M03-E5-B lo usa para el lote de secuenciación, porque `campo_evento_trabajo.orden_id` es `NOT NULL` y no admite un evento "de conjunto") | **no** | Agrupa **el acto**, no **el estado**. Sirve para el historial (sección J); **no** sirve para consultar "qué cuadrilla trabaja hoy" |
| **Columna `cuadrilla_ref` (UUID) en `campo_asignacion_trabajo`** | **sí** | Es el campo mínimo real si se decide que la cuadrilla persiste entre OTs |

**[PENDIENTE] Esto es una decisión empresarial abierta y es la que bloquea F-1**
(ver N y Q). No la decido: la evidencia no la resuelve. Producción tiene 1
persona por orden en las 3 órdenes, así que **no hay un solo caso real que
muestre cuál de los dos significados usa la empresa**.

### A.7 ¿A qué debería vincularse la agrupación?

**[MEDIDO] Hoy está vinculada a la OT, y es la única opción que no requiere
nada nuevo.** Evaluación de las cuatro candidatas:

| Vínculo | Hoy | Nota |
|---|:--:|---|
| **OT** | **existe** (`orden_id`) | La cuadrilla es de *este desplazamiento físico* |
| **Jornada** | no existe | La "jornada" no es una entidad: es `(dia, plan)` derivado en `operaciones/programacion.py`. No hay a qué apuntar |
| **ProgramacionOrden** | no existe | Ver sección F: una OT puede tener **varias** líneas a lo largo del tiempo (reprogramaciones). Colgar la cuadrilla de la línea la haría desaparecer al reprogramar |
| **Otra entidad** | — | `teams` existe con **0 filas** y consumidores ajenos a M03 (F-A). No se usa |

### A.8 El hueco real de F-1 — la cuadrilla no es alcanzable por la API

**[MEDIDO]** La estructura soporta N personas. **La API no tiene ninguna
operación que agregue un miembro sin convertirlo en principal.**

`campo/services/despacho.py:170-179` — la **única** vía de escritura expuesta:

```python
orden.asignaciones.filter(es_principal=True).update(es_principal=False)
asignacion, creada = AsignacionTrabajo.objects.get_or_create(
    orden=orden, profile=profile_tecnico,
    defaults={"rol": rol, "es_principal": True},
)
if not creada:
    asignacion.es_principal = True
    asignacion.rol = rol
```

No hay rama: **toda** llamada baja al principal anterior y sube al nuevo.

**Medición M1** — `asignar(p1, rol="tecnico_lider")` y después
`asignar(p2, rol="ayudante")`:

```
p1  rol='tecnico_lider'   es_principal=False
p2  rol='ayudante'        es_principal=True
miembros=2   principales=1   tecnico_principal -> p2
```

**[MEDIDO]** La cuadrilla de 2 **sí** se forma — pero al precio de que el líder
deja de ser el principal y el ayudante pasa a serlo. **No existe forma, por la
API, de agregar un auxiliar conservando al líder como principal.**

**[DISEÑO]** F-B necesita **tres operaciones que hoy no existen**:
`agregar_integrante`, `retirar_integrante`, `cambiar_rol`. Ninguna es una
variante de `asignar()`: `asignar()` significa *"cambia el responsable"*, no
*"suma a alguien"*.

---

## B. F-2 — Líder obligatorio

### B.1 ¿Cómo se representa hoy el líder?

**[MEDIDO] Con `es_principal`, no con `rol`.** Ver sección C: `es_principal`
tiene 6 consumidores; `rol` tiene **cero**.

### B.2 ¿`rol=tecnico_lider` puede identificarlo?

**[MEDIDO] Hoy no, por tres razones medidas:**

1. **Nadie lo lee.** `rol` no aparece en ninguna condición, filtro, orden,
   permiso ni respuesta de API (sección C.2).
2. **No es un valor confiable.** La API acepta **cualquier** cadena (M2, y
   sección K.4).
3. **Puede repetirse.** M4-D creó **dos** `tecnico_lider` en la misma OT sin
   error. No hay constraint que lo impida.

### B.3 ¿`es_principal=True` puede identificarlo?

**[MEDIDO] Parcialmente. Garantiza "como máximo uno", nunca "exactamente uno".**

Índice real en producción:

```sql
CREATE UNIQUE INDEX unique_tecnico_principal_por_orden
    ON public.campo_asignacion_trabajo USING btree (orden_id)
    WHERE es_principal
```

**[MEDIDO]** Un índice único **parcial** no exige existencia: si ninguna fila
cumple el `WHERE`, no hay nada que duplicar. M4-B lo confirma — una OT con un
`tecnico_lider` y `es_principal=False` fue **aceptada**, y su
`tecnico_principal` quedó en `None`.

### B.4 Las cuatro combinaciones — medidas, no razonadas

**[MEDIDO]** Probadas contra PostgreSQL real:

| | Combinación | ¿Posible hoy? | Cómo se alcanza |
|:--:|---|:--:|---|
| **A** | `tecnico_lider` + `es_principal=True` | **SÍ** | Es lo que hay en las 3 filas de producción |
| **B** | `tecnico_lider` + `es_principal=False` | **SÍ** | **La produce `asignar()` en su segunda llamada** (M1). También por escritura directa |
| **C** | `auxiliar`/`ayudante` + `es_principal=True` | **SÍ** | **La produce `asignar()` en su segunda llamada** (M1). Y `CrearOrdenView` deja `rol='tecnico'` + principal |
| **D** | dos personas con `rol=tecnico_lider` | **SÍ** | Sin constraint alguna. Medido: `lideres=2` |
| **E** | dos personas con `es_principal=True` | **NO** | **Único caso que la base rechaza**: `duplicate key value violates unique constraint "unique_tecnico_principal_por_orden"` |

**[MEDIDO]** Las cuatro combinaciones que F-2 llama contradictorias **son todas
posibles hoy**, y dos de ellas (**B** y **C**) no requieren ni siquiera una
escritura irregular: **las produce la API normal**.

### B.5 ¿Existe una constraint que garantice exactamente un líder?

**[MEDIDO] No.** Sobre `campo_asignacion_trabajo`:

```
CHECK constraints ......... 0
triggers .................. 0
UNIQUE .................... 2   (orden_id+profile_id) y (orden_id) WHERE es_principal
```

### B.6 ¿Existe una constraint que garantice la equivalencia rol ⇔ es_principal?

**[MEDIDO] No.** Ninguna constraint menciona `rol`. `rol` no participa de
ningún índice.

### B.7 ¿Puede garantizarse por servicio?

**[DISEÑO] Sí para "como máximo uno" y "al menos uno" — pero con un límite
medido.**

**[MEDIDO] Un servicio no cierra la puerta.** Tres vías lo rodean hoy:

| Vía | Medido |
|---|---|
| **Django Admin** | `campo/admin.py:17-21` expone `es_principal` y `rol` como campos **editables** en un inline. El usuario ya instruyó *"NO utilizar Django Admin como vía operacional"* — pero la puerta está abierta |
| **Escritura directa por ORM** | M6: crear la fila directamente dejó **0 eventos** (`delta=0`). El servicio audita; la escritura directa no |
| **`seed_campo_demo.py:122`** | `AsignacionTrabajo.objects.get_or_create(...)` sin pasar por `asignar()` |

### B.8 ¿Puede garantizarse por DB?

**[DISEÑO] Parcialmente, y la parte que falta es la difícil.**

| Invariante | Mecanismo | Viable |
|---|---|:--:|
| **como máximo un principal** | índice único parcial | **ya existe** |
| **como máximo un `tecnico_lider`** | índice único parcial sobre `(orden_id) WHERE rol='tecnico_lider'` | **sí**, migración de 1 índice |
| **`rol` dentro del catálogo** | `CHECK (rol IN (...))` | **sí**, migración de 1 constraint |
| **AL MENOS un líder** | — | **NO es expresable como constraint de Django** |

**[DISEÑO]** "Al menos uno" es un invariante **de ausencia**: se viola por lo
que *no* está. `UniqueConstraint` y `CheckConstraint` evalúan **una fila**; no
pueden afirmar que exista otra. En PostgreSQL se implementa con un **trigger
`CONSTRAINT ... DEFERRABLE INITIALLY DEFERRED`** que cuente al final de la
transacción — porque durante `asignar()` hay un instante real con **cero**
principales (`update(es_principal=False)` corre **antes** del `get_or_create`),
y un trigger inmediato abortaría la operación legítima.

**[RIESGO]** Django no gestiona triggers: quedaría como SQL crudo en una
`RunSQL`, fuera de `makemigrations --check`. Es deuda, y hay que decidirla a
ojos abiertos.

### B.9 Diferencia de seguridad entre servicio y DB

**[DISEÑO]**

| | Servicio | Base de datos |
|---|---|---|
| **Cubre** | lo que pasa por `despacho.asignar()` | **toda** escritura, venga de donde venga |
| **No cubre** | admin, ORM directo, seeds, `psql`, migraciones de datos | — |
| **Mensaje de error** | en español, accionable | violación de constraint, cruda |
| **Costo** | 0 migraciones | 1 migración (+ SQL crudo para "al menos uno") |
| **Se puede desarmar para probarlo** | sí (disciplina del proyecto) | sí |

**[DISEÑO] Recomendación técnica: las dos capas, con reparto explícito.** La DB
sostiene lo que es invariante (catálogo, unicidad); el servicio sostiene lo que
es política (cuándo se exige líder, qué motivo se pide) y da el mensaje. Es el
mismo patrón de *"seguridad en dos capas"* que ya rige en `PRD §7.4`.

### B.10 Conflicto que F-2 no puede ignorar

**[MEDIDO] "Toda cuadrilla tiene exactamente un líder" contradice un estado
deliberado y documentado del sistema: la OT sin asignar.**

`campo/serializers.py:202-204`:

```python
# A quien se le asigna de entrada. Opcional: una orden puede quedar sin
# asignar esperando que alguien la tome, y esa es una columna util en la
# bandeja del supervisor.
tecnico_profile_id = serializers.UUIDField(required=False, allow_null=True)
```

Y `operaciones/supervisor.py:478` lo consume así, a propósito:

```python
principal = o.tecnico_principal
if principal is None:
    continue
```

**[PENDIENTE]** F-2 debe decir **desde cuándo** aplica la regla: ¿desde que la
OT existe (y entonces la OT sin asignar deja de ser legal), o desde que tiene
≥1 integrante (y entonces "cero integrantes" sigue siendo válido)? **Decisión
empresarial abierta.** La segunda lectura es la única compatible con el código
actual, pero *compatible* no es *aprobada*, y no la elijo por mi cuenta.

---

## C. F-3 — Principal ≡ Líder

> *"No asumir que 'principal' y 'líder' son conceptos distintos ni asumir que
> son idénticos. Si tienen semánticas diferentes, explicarlo. Si actualmente se
> utilizan como sinónimos, demostrarlo."*

**[MEDIDO] Ninguna de las dos. Hoy no son sinónimos ni conceptos distintos:
uno decide todo y el otro no decide nada.**

### C.1 Quién consume `es_principal` — 6 consumidores reales

| Consumidor | Archivo | Qué decide |
|---|---|---|
| `OrdenTrabajo.tecnico_principal` | `campo/models.py:307-315` | La **@property** de la que cuelga todo lo demás |
| **H-05 `_ordenes_en_riesgo`** | `operaciones/supervisor.py:477` | **Si se emite una señal de riesgo** por ausencia. Es el único cruce M03↔M09 |
| `OrdenTrabajoSerializer` | `campo/serializers.py:85-92` | El técnico que ve la bandeja |
| `OrdenTrabajoDetailSerializer` | `campo/serializers.py:146-153` | Ídem, en el detalle |
| `admin.tecnico_responsable` | `campo/admin.py:162` | La columna "Técnico Principal" |
| `despacho.asignar` | `campo/services/despacho.py:167` | El `anterior` del evento de reasignación |

Más, estructuralmente: el **índice único parcial** (`models.py:369`), el
**`Meta.ordering`** (`models.py:361`, `["-es_principal", "asignado_en"]`) y el
**`__str__`** (`models.py:376`, el sufijo `" (Principal)"`).

### C.2 Quién consume `rol=tecnico_lider` — cero

**[MEDIDO]** `rol` aparece **solo en escritura**, en dos lugares:

```
campo/despacho_views.py:193   rol=s.validated_data["rol"] or "tecnico"
campo/services/despacho.py:178   asignacion.rol = rol
```

y en el `datos` del evento (`despacho.py:191`), que es historial, no decisión.

**[MEDIDO] `rol` NO aparece en:** ninguna respuesta de API (ni
`OrdenTrabajoSerializer` ni `OrdenTrabajoDetailSerializer` lo exponen), ningún
`filter()`, ningún `order_by()`, ningún permiso, ninguna constraint, ningún
índice, ninguna regla de `operaciones/programacion.py`.

**Único lector en todo el backend:** `campo/admin.py:20`, que lo muestra en el
inline del panel de Django. Nada que decida conducta.

### C.3 ¿Los datos de producción demuestran que son sinónimos?

**[MEDIDO] Coinciden 3 de 3 — y esa coincidencia no demuestra una regla.**

```
rol='tecnico_lider'  es_principal=True  -> 3 filas   (100%)

OT 1842  en_sitio            asign=1  principal=1  lider=1
OT 1843  en_sitio            asign=1  principal=1  lider=1
OT 1844  completada_campo    asign=1  principal=1  lider=1
```

**[MEDIDO] Por qué la correlación no prueba nada:** hay **1 sola persona** en
las 3 asignaciones y **1 sola asignación por orden**. Con un solo patrón de
escritura, cualquier par de campos correlaciona.

**[MEDIDO] Y hay evidencia de que esas 3 filas no vinieron del servicio:** de
los 12 `EventoTrabajo` de producción, **cero** son de tipo `asignacion` o
`reasignacion`:

```
datos_actualizados 3 · accion_marcar_en_camino 3 · accion_marcar_llegada 3
evidencia_confirmada 2 · trabajo_completado_campo 1
```

`despacho.asignar()` **siempre** escribe un evento. Sin ninguno, esas 3 filas
no pasaron por ahí. Sus valores coinciden **exactamente** con el default de
`campo/management/commands/seed_campo_demo.py:125`
(`defaults={"rol": "tecnico_lider", "es_principal": True}`).

**[RIESGO]** No afirmo que el seed las creó — no tengo evidencia directa del
origen. Afirmo lo medido: **coinciden con el seed y ningún evento respalda otra
vía**. La consecuencia es la misma en cualquier caso: **la correlación 3/3 es
un artefacto de un valor por defecto, no la huella de una política.**

### C.4 Las dos vías de escritura rompen la equivalencia

**[MEDIDO]** Esto es lo que tumba la recomendación preliminar de F-A:

**Vía 1 — crear una OT con técnico.** `campo/despacho_views.py:158`:

```python
asignar(orden, tecnico, request.profile)      # sin 'rol'
```

`asignar` tiene `rol: str = "tecnico"` por defecto → la fila nace
**`rol='tecnico'` + `es_principal=True`**. Es la combinación **C**. **La
equivalencia se viola en la primera llamada del sistema.**

**Vía 2 — asignar una segunda persona.** M1, ya citado: deja `tecnico_lider`
sin principal (**B**) y `ayudante` como principal (**C**) **a la vez**.

### C.5 ¿Es necesaria la equivalencia?

**[DISEÑO] No es necesaria para nada de lo que existe hoy.** Nada la consulta.
Declararla sería **agregar** una regla, no documentar una vigente.

**[PENDIENTE] Y hay una razón empresarial real para que NO sean lo mismo**, que
sale de lo que `es_principal` ya significa **medido**:

| | Significado que **ya tiene**, por sus consumidores |
|---|---|
| **`es_principal`** | *quién responde por la OT*: a quién muestra la bandeja, y **de quién depende H-05** — si **esa** persona está ausente, la OT entra en riesgo (`supervisor.py:477-484`) |
| **`rol=tecnico_lider`** | *(sin significado operacional; nadie lo lee)* |

En una cuadrilla de 3, *"quién dirige el trabajo en sitio"* y *"por quién
pregunta el supervisor / cuya ausencia pone la OT en riesgo"* **pueden ser
personas distintas**, y eso es una decisión de cómo opera Rapilink, no una
propiedad del código.

**[RIESGO] Consecuencia concreta de declarar la equivalencia:**
`rol=tecnico_lider` heredaría de golpe la semántica de H-05. Un cambio de rol
pasaría a mover **qué ausencia dispara una señal de riesgo** — un efecto que
hoy ningún cambio de `rol` tiene, porque `rol` no lo lee nadie.

**[PENDIENTE] F-3 queda ABIERTA.** No la cierro: elegir entre "son lo mismo" y
"son distintos" es exactamente la decisión empresarial que el encargo prohíbe
tomar por cuenta propia.

---

## D. Análisis de `AsignacionTrabajo`

### D.1 Lo que hay

| | [MEDIDO] |
|---|---|
| **Modelo** | `campo/models.py:317-378` |
| **Manager** | **ninguno propio** — hereda el de `BaseModel` |
| **Constraints** | 2 UNIQUE. **0 CHECK. 0 triggers** |
| **Serializers** | `AsignarSerializer` (`serializers.py:207-210`) — es **entrada**; **no hay serializer de salida** para la asignación |
| **Views** | `AsignarTrabajoView` (`despacho_views.py:171-201`) |
| **Servicios** | `despacho.asignar()` (`services/despacho.py:145-195`) |
| **Permisos** | `PuedeAccederOrden` (`campo/permissions.py:32-57`) |
| **Otras vías de escritura** | `admin.py:17` (inline editable) · `seed_campo_demo.py:122` |
| **RLS** | **deshabilitada** · 0 políticas · **sin `org_id` propio** |

### D.2 Qué haría falta para los 8 escenarios

**[DISEÑO]** Ninguno se implementa aquí. `[EXISTENTE]` = funciona hoy.

| | Escenario | Estado hoy | Qué faltaría |
|:--:|---|:--:|---|
| **A** | Técnico individual | **[EXISTENTE]** | Nada. Es el único caso ejercido en producción |
| **B** | Cuadrilla ad-hoc de 2 | **parcial** | La estructura sí; **la operación no** (A.8). Falta `agregar_integrante` |
| **C** | Cuadrilla ad-hoc de 3+ | **parcial** | Igual que B. El `unique(orden, profile)` ya impide duplicar persona |
| **D** | Cambio de líder | **parcial** | `asignar()` cambia el **principal**; no toca el `rol` del anterior (M1: p1 quedó `tecnico_lider` sin principal). Falta decidir si "líder" es `rol` o `es_principal` → **depende de F-3** |
| **E** | Retiro de integrante | **[NUEVO]** | **No existe ninguna operación de borrado.** Y `on_delete=CASCADE` en ambos FK: borrar la fila **borra la historia de membresía**. Necesita `retirado_en`/`vigente`, no `DELETE` |
| **F** | Incorporación de integrante | **[NUEVO]** | La operación no existe (A.8) |
| **G** | Reasignación de OT | **[EXISTENTE]** | `asignar()` ya lo hace y deja evento `reasignacion` |
| **H** | Cambio de cuadrilla en ejecución | **[NUEVO]** | Depende de E y F. Además: **nada bloquea hoy reasignar una OT `en_sitio`** — `asignar()` solo rechaza `CERRADA` y `CANCELADA` (`despacho.py:161-164`). **[PENDIENTE]** decisión empresarial: ¿se puede cambiar la cuadrilla con el trabajo empezado? |

### D.3 Lo que falta en el modelo, independientemente de F-1/F-2/F-3

**[RIESGO]** Tres huecos que F-B arrastraría:

1. **No hay vigencia.** Sin `retirado_en`, un integrante retirado solo puede
   borrarse, y el `CASCADE` se lleva el rastro.
2. **No hay `org_id` propio.** El aislamiento depende **enteramente** de
   `orden.org` (sección K).
3. **El catálogo no se valida** (sección K.4).

---

## E. Relación con la OT

### E.1 ¿A qué pertenece conceptualmente la cuadrilla?

**[DISEÑO] A la OT (opción A)** — con una salvedad que hay que decidir.

Sustento **[MEDIDO]**:

- `orden_id` es `NOT NULL`: una asignación **no puede existir** sin OT.
- `PuedeAccederOrden` concede acceso **por pertenecer a la OT** (M5).
- `tecnico_principal` es una propiedad **de la OT**.
- La OT es *"el desplazamiento físico"* (`operaciones/models.py:19`). La
  cuadrilla es *quién va en ese desplazamiento*.

**[PENDIENTE]** Si la empresa decide que la cuadrilla persiste **entre** OTs
(A.4), la respuesta pasa a ser **E (combinación)**: la membresía sigue siendo
de la OT, y el agrupador es una entidad aparte. **Sin esa decisión, F-1 no
está definido sin ambigüedad.**

### E.2 Lo que no debe moverse

**[DISEÑO]** El encargo lo exige y conviene dejarlo escrito como invariante de
F-B: crear o modificar una cuadrilla **no** debe tocar `programada_para`,
`secuencia`, `prioridad` ni el SLA.

**[MEDIDO] Hoy se cumple, con una excepción medida:** `asignar()` **sí**
incrementa `orden.revision` (`despacho.py:181-182`). Es el contador de
sincronización de la cola offline del técnico, no un dato de programación —
pero es una escritura sobre la OT y F-B debe conservarla deliberadamente, no
por descuido.

---

## F. Relación con programación

### F.1 Qué significa `ProgramacionOrden` + `AsignacionTrabajo`

**[MEDIDO] Hoy: nada. No se cruzan en ningún punto del código.**

`operaciones/programacion.py` (1.500+ líneas, todo el módulo M03) **no lee
`asignaciones` ni una sola vez**. Sus únicas referencias a `profile` son
`profile=actor` — quien escribe el evento, no quien ejecuta el trabajo.

Las dos entidades responden preguntas distintas:

| | Responde |
|---|---|
| `ProgramacionOrden` | **cuándo** y **en qué orden** |
| `AsignacionTrabajo` | **quién** |

### F.2 ¿La asignación debe ocurrir antes, después, o independientemente?

**[MEDIDO] Hoy: independientemente (opción C), y de forma no verificada.**

`ESTADOS_PROGRAMABLES = frozenset({OrdenTrabajo.ASIGNADA})` filtra por el
**campo de estado** `estado_operativo`, que es una columna de
`campo_orden_trabajo` — **no** comprueba que exista ninguna fila en
`campo_asignacion_trabajo`.

**[RIESGO]** Consecuencia medida: **una OT en estado `ASIGNADA` con cero
asignaciones se puede programar.** El estado dice "asignada"; la tabla puede
decir que no hay nadie. Nada los concilia.

**[DISEÑO] Qué patrón da más coherencia:** el que ya rige en el módulo —
**validar en el servicio, en el momento de la operación, contra la fila fresca
bajo lock**. `programar_orden` ya toma `select_for_update` sobre la OT; ahí
cabría la comprobación de que la cuadrilla existe, sin inventar un flujo nuevo
ni un estado nuevo.

**[PENDIENTE]** Si programar debe exigir cuadrilla es **decisión empresarial**:
podría ser legítimo planificar la semana y asignar personas después. No la
tomo.

---

## G. Relación con disponibilidad

### G.1 Qué información existe hoy

**[MEDIDO]** `DisponibilidadTecnico` (A-3.x) tiene `(org, profile, fecha,
disponible, motivo)`. Es **por persona**, no por cuadrilla — o sea, **el dato
crudo para detectar el conflicto ya existe completo**.

### G.2 El hueco

**[MEDIDO]** `_ordenes_en_riesgo` (`supervisor.py:471-490`) consulta
**únicamente al principal**:

```python
principal = o.tecnico_principal
if principal is None:
    continue
ausencia = DisponibilidadTecnico.objects.filter(
    org=org, profile=principal, fecha=dia, disponible=False).first()
```

**[RIESGO]** Con una cuadrilla de 3 donde el principal está presente y los
otros dos ausentes, **H-05 no emite nada**. No es un fallo de H-05 — se
escribió cuando una OT era una persona — pero **F-1 lo convierte en un punto
ciego** el día que exista la primera cuadrilla real.

### G.3 Diseño de la detección — solo detección

**[DISEÑO]** El cambio mínimo, sin inventar reemplazo, cancelación ni
reprogramación (el encargo lo prohíbe explícitamente):

```
para cada OT programada:
    integrantes = [a.profile for a in orden.asignaciones.all()]     # ya existe
    ausentes    = DisponibilidadTecnico.filter(profile__in=integrantes,
                                               fecha=dia, disponible=False)
    si ausentes:  emitir ORDEN_EN_RIESGO con una observacion POR ausente
```

**[DISEÑO]** Reutiliza `Senal`, `PropuestaSupervisor.ORDEN_EN_RIESGO` y
`_observacion`, que ya existen. **No requiere modelo nuevo ni migración.**

**[PENDIENTE]** Qué **gravedad** tiene cada caso — ausente el principal vs.
ausente un ayudante vs. ausente toda la cuadrilla — es una decisión
empresarial. Hoy solo existe un tipo de señal, sin niveles.

---

## H. Vehículo

**[MEDIDO] No existe ningún modelo de vehículo en el backend.** Barrido
completo de `vehiculo|vehículo|flota|placa`: **1 sola coincidencia**, y es
ajena — `seed_campo_demo.py:81`, el texto de una instrucción de evidencia
(*"Foto exterior con placa visible de la nomenclatura"*, que se refiere a la
placa de la dirección del cliente, no a un vehículo).

**[DISEÑO] Su ausencia NO impide definir una cuadrilla ad-hoc.** Una cuadrilla
es un conjunto de personas asignadas a una OT; el vehículo es un recurso
*adicional* que esas personas usan. Ninguno de los invariantes de F-1, F-2 o
F-3 lo menciona.

**[DEPENDENCIA] Futura, documentada y no bloqueante.** Si algún día se modela,
la pregunta abierta será si el vehículo se asocia a la OT, a la cuadrilla o a
la jornada — y esa pregunta **es la misma que A.7**, así que decidir bien el
agrupador de F-1 ahora abarata el vehículo después.

---

## I. Zona

**[MEDIDO] `zona` hoy es texto libre sin catálogo** (gap **E-7**, abierto desde
M03-E4). Vive en `ProgramacionOrden`, **no** en `AsignacionTrabajo` ni en la OT.

**[DISEÑO] Una cuadrilla NO necesita zona propia hoy.** Sustento: la zona
describe **dónde se trabaja** y ya cuelga de la línea de programación; la
cuadrilla describe **quién trabaja**. Duplicarla en la asignación crearía dos
fuentes para el mismo dato, que es exactamente lo que `operaciones/models.py:19`
y la regla del `tecnico_principal` (*"fuente única de verdad"*) evitan.

**[PENDIENTE]** Si en el futuro se quiere *"esta cuadrilla solo atiende la zona
norte"*, eso es una **restricción de asignación**, no un atributo de la
cuadrilla, y exige primero cerrar E-7 (catálogo de zonas). No lo decido aquí.

---

## J. Historial

### J.1 Lo que ya existe

**[MEDIDO]** `EventoTrabajo` es la superficie de auditoría del módulo, y
`asignar()` ya escribe en ella:

```python
tipo = "asignacion" if anterior is None else "reasignacion"
datos = {"anterior": ..., "nuevo": ..., "rol": rol, "motivo": motivo}
```

**[MEDIDO] Restricción estructural:** `campo_evento_trabajo.orden_id` es
`NOT NULL` — **no existe el evento "de conjunto"**. M03-E5-B ya resolvió esto
para lotes con un **UUID `lote` dentro de `datos`**, y ese precedente aplica
igual aquí.

### J.2 Diseño de los 7 eventos — sin sistema de auditoría nuevo

**[DISEÑO]** Todo cabe en `EventoTrabajo` reutilizando `tipo` + `datos`:

| # | Hecho | `tipo` | `datos` mínimos |
|:--:|---|---|---|
| 1 | Creación de cuadrilla ad-hoc | `cuadrilla_formada` | `{lote, integrantes: [...], lider}` |
| 2 | Incorporación de integrante | `integrante_agregado` | `{profile, rol, motivo}` |
| 3 | Retiro de integrante | `integrante_retirado` | `{profile, rol_que_tenia, motivo}` |
| 4 | Cambio de líder | `cambio_lider` | `{anterior, nuevo, motivo}` |
| 5 | Cambio de asignación | `reasignacion` | **[EXISTENTE]**, sin cambios |
| 6 | Cambio de cuadrilla | `cuadrilla_reemplazada` | `{lote, salen: [...], entran: [...], motivo}` |
| 7 | Disolución | `cuadrilla_disuelta` | `{lote, integrantes}` |

**[DISEÑO]** `1`, `6` y `7` son actos sobre **varias** filas: comparten un
`lote` UUID, igual que M03-E5-B. `2`, `3` y `4` son de una fila y no lo
necesitan.

**[RIESGO]** `EventoTrabajo.tipo` es **texto sin catálogo cerrado**, y
`operaciones/auditoria.py:44` ya advierte que un tipo sin declarar *"se guarda
igual y queda divergiendo sin que nadie lo vea"*. Agregar 6 tipos nuevos sin
declararlos repetiría el mismo error que esa nota describe.

**[RIESGO] El historial NO cubre la escritura directa.** Medido en M6: crear la
fila por ORM dejó **0** eventos (`delta=0`). Mientras el admin siga exponiendo
el inline editable, el historial de cuadrillas tendrá huecos silenciosos —
exactamente el problema que el docstring de `asignar()` dice haber resuelto
(*"Una hecha desde el panel de Django no lo dejaba, y entonces la bitácora
tenía un hueco justo donde el trabajo cambiaba de manos"*). **La corrección de
entonces cubrió el servicio, no el panel.**

---

## K. Seguridad / multi-tenant

### K.1 Nivel de aislamiento real

**[MEDIDO]** Medido sobre producción, tabla por tabla:

```
TODAS las tablas campo_*    RLS = False    forzada = False    politicas = 0
campo_asignacion_trabajo    sin columna org_id / organization_id
rol de la conexion runtime  postgres   bypassrls = True   superuser = False
```

**[MEDIDO] `ORG_SCOPED_TABLES` (`common/rls/__init__.py`) no contiene ninguna
entrada `campo_`** — esa es la causa, ya identificada en pasos previos (gap
**R-2**). Confirmado de nuevo aquí: el barrido de `campo_` sobre ese archivo no
devuelve nada.

### K.2 De qué depende hoy el aislamiento

**[MEDIDO] Enteramente de la capa de aplicación**, en dos puntos:

| Capa | Medido |
|---|---|
| `PuedeAccederOrden` | 404 estricto si `obj.org != request.org` (`permissions.py:47-49`) |
| `despacho.asignar` | `if profile_tecnico.org_id != orden.org_id: raise ErrorDespacho` (`despacho.py:159-160`) |

**[RIESGO]** Como `campo_asignacion_trabajo` **no tiene `org_id`**, incluso si
se activara RLS sobre las tablas `campo_*` esta tabla **no tendría columna
sobre la cual filtrar**: la política tendría que navegar el FK a
`campo_orden_trabajo`. Es viable (`USING (EXISTS (SELECT 1 FROM
campo_orden_trabajo o WHERE o.id = orden_id AND o.org_id = ...))`) pero es una
política **más cara y más frágil** que una columna directa. **Es un dato que
F-B debe conocer antes de diseñar, no después.**

### K.3 Permisos de la cuadrilla — lo que sí funciona

**[MEDIDO]** M5, contra el permiso real:

```
principal   ve la orden?  True
ayudante    ve la orden?  True          <- miembro NO principal: SÍ accede
ajeno       ve la orden?  NO -- levanta Http404
```

**[MEDIDO] `PuedeAccederOrden` concede por PERTENENCIA, no por principalía**
(`permissions.py:53`: `orden.asignaciones.filter(profile=profile).exists()`).
**Esta es la pieza que F-1 necesita y que ya está bien construida**: el día que
exista una cuadrilla real, todos sus integrantes ven la OT sin tocar el permiso.

### K.4 [RIESGO] Bypass real — el catálogo cerrado no se valida en tiempo de ejecución

> El encargo exige: *"Si encuentras un bypass real: NO lo ocultes ni lo
> parchees sin reportarlo primero."* Se reporta. **No se parcheó.**

**[MEDIDO]** El modelo declara (`campo/models.py:322-328`):

```
# CATALOGO CERRADO (15/09/2026). Antes era texto libre con la lista solo
# en el help_text, y ya habia divergido [...]
# Lo que se cierra es lo que se puede escribir de ahora en adelante.
```

**La medición dice que no se cerró.** M2, contra la API real:

```
POST /api/campo/trabajos/<id>/asignar/   {"rol": "capitan_pirata_que_no_existe"}

HTTP = 200
rol PERSISTIDO en la base = 'capitan_pirata_que_no_existe'
esta en ROLES_CUADRILLA?  False
```

**Las tres causas, cada una medida:**

| # | Causa | Evidencia |
|:--:|---|---|
| 1 | `AsignarSerializer.rol` es **`CharField`**, no `ChoiceField` | `campo/serializers.py:209`. Hay `ChoiceField` en el mismo archivo (`:281`), así que no es que se desconociera |
| 2 | **Nadie llama `full_clean()`** sobre `AsignacionTrabajo` | Único `full_clean` en `campo/` + `operaciones/`: `supervisor.py:732`, sobre `propuesta` |
| 3 | **No hay `CHECK` en la base** | 0 CHECK constraints sobre la tabla |

**[MEDIDO] El mecanismo existe y funciona — simplemente no se invoca.** M3:

```
.save() con rol inventado      -> guardo 'inventado_xyz'  (sin error)
full_clean() SI lo rechaza     -> ["Value 'inventado_xyz' is not a valid choice."]
```

Django valida `choices` en formularios y admin, **nunca en `.save()`**.

**[RIESGO] El propio repo ya diagnosticó este mecanismo, citando este mismísimo
campo.** `operaciones/auditoria.py:44`:

> *"un entity_type sin declarar se guarda igual —Django valida 'choices' en
> formularios, no al guardar— y queda divergiendo sin que nadie lo vea— que es
> como 'AsignacionTrabajo.rol' termino con un 'tecnico_lider' que su propio
> modelo no documenta"*

**[MEDIDO] La corrección del 15/09/2026 cerró el modelo y dejó abierta la
puerta de entrada.** La divergencia que esa nota describe **puede repetirse hoy
por la API**, con HTTP 200.

**[DISEÑO] Reparación (NO aplicada, requiere autorización):** `ChoiceField` en
el serializer + `CheckConstraint` en el modelo. La segunda **exige migración**.
Ver sección M.

---

## L. Modelo conceptual propuesto

**[DISEÑO]** No implementado. Cada campo etiquetado como pide el encargo.

```
OrdenTrabajo                                        [EXISTENTE]
 |
 +-- AsignacionTrabajo  (N filas, agrupadas por orden_id)
      |
      +-- orden          FK, NOT NULL                [EXISTENTE]  <- es el agrupador
      +-- profile        FK, NOT NULL                [EXISTENTE]
      +-- rol            catalogo cerrado            [EXISTENTE]  (sin validar: K.4)
      +-- es_principal   bool                        [EXISTENTE]
      +-- asignado_en    auto_now_add                [EXISTENTE]
      +-- retirado_en    null => vigente             [NUEVO]      <- requiere migracion
      +-- cuadrilla_ref  UUID                        [PENDIENTE]  <- solo si F-1 = persistente
```

### L.1 Las seis preguntas del encargo

| Pregunta | Respuesta | Etiqueta |
|---|---|---|
| **¿Basta con esto?** | **Para la cuadrilla POR OT: sí.** La estructura basta; lo que falta son **operaciones**, no campos (A.8) | **[DISEÑO]** |
| **¿Hace falta agrupador?** | **No para cuadrilla por OT** (`orden_id` ya agrupa). **Sí si persiste entre OTs** — decisión abierta (A.4) | **[PENDIENTE]** |
| **¿Hace falta estado?** | **No.** Un estado de cuadrilla duplicaría `OrdenTrabajo.estado_operativo`. La cuadrilla no tiene ciclo de vida propio si pertenece a la OT | **[NO NECESARIO]** |
| **¿Hace falta vigencia?** | **Sí, `retirado_en`.** Sin ella, retirar a alguien es `DELETE`, y el `CASCADE` borra la historia (D.2-E) | **[NUEVO]** |
| **¿Hace falta referencia a jornada?** | **No.** La jornada no es una entidad: es `(dia, plan)` derivado. No hay a qué apuntar (A.7) | **[NO NECESARIO]** |
| **¿Hace falta otra información?** | **`org_id` propio** sería lo correcto para RLS (K.2) — pero **[PENDIENTE]**: es una decisión de arquitectura de aislamiento que excede F-B y afecta a las 7 tablas `campo_*`, no solo a esta | **[PENDIENTE]** |

---

## M. Migraciones

### M.1 ¿F-1/F-2/F-3 pueden implementarse sin migración?

**[DISEÑO]**

| | Sin migración | Con migración |
|---|---|---|
| **F-1** (cuadrilla por OT) | **SÍ** — solo endpoints y servicios | — |
| **F-1** (cuadrilla persistente entre OTs) | no | `cuadrilla_ref` UUID + índice |
| **F-2** garantizado **por servicio** | **SÍ** | — |
| **F-2** garantizado **por DB** | no | índice único parcial (`WHERE rol='tecnico_lider'`) **+** trigger `DEFERRABLE` para "al menos uno" |
| **F-3** declarada y aplicada **por servicio** | **SÍ** | — |
| **F-3** garantizada **por DB** | no | `CheckConstraint` que ligue `rol` y `es_principal` |
| **Retiro de integrante** (D.2-E) | no | `retirado_en` (nullable) |
| **Cierre real del catálogo** (K.4) | **el serializer sí** | el `CheckConstraint` **no** |

### M.2 Qué exigiría cada migración, y por qué

**[DISEÑO]** Ninguna se crea aquí.

| # | Migración | Por qué |
|:--:|---|---|
| 1 | `AddField retirado_en (DateTimeField, null=True)` | Es el único modo de retirar a alguien sin que el `CASCADE` borre la historia. Nullable → **no requiere backfill**: las 3 filas de producción quedan vigentes |
| 2 | `AddConstraint CheckConstraint(rol IN ROLES_CUADRILLA)` | Cierra el catálogo en la capa que ninguna vía rodea (K.4). **[MEDIDO]** Las 3 filas de producción son `tecnico_lider`, que **está** en el catálogo → **la constraint valida sin rechazar nada existente** |
| 3 | `AddConstraint UniqueConstraint(orden, condition=Q(rol='tecnico_lider'))` | "Como máximo un líder", si F-3 decide que el líder es `rol`. **[MEDIDO]** Producción tiene 1 por orden → **valida sin conflicto** |
| 4 | `RunSQL` con trigger `DEFERRABLE` | "Al menos un líder". **[RIESGO]** SQL crudo, invisible a `makemigrations --check` |
| 5 | `AddField cuadrilla_ref` | **Solo** si F-1 se cierra como persistente |

**[MEDIDO]** Las migraciones 2 y 3 **no romperían producción**: se verificó que
las 3 filas existentes las cumplen. Las 1 y 5 son aditivas nullable.

**[DISEÑO]** Migraciones 1–3 son de bajo riesgo. La 4 es la única que
introduce un mecanismo que Django no gestiona.

---

## N. Matriz de decisiones

### F-1 — Cuadrilla ad-hoc

| | |
|---|---|
| **Decisión propuesta** | La cuadrilla **es** el conjunto de `AsignacionTrabajo` de una OT, agrupado por `orden_id`. **Sin entidad `Cuadrilla`, sin campo nuevo.** |
| **Evidencia** | **[MEDIDO]** `orden_id` NOT NULL agrupa; `operaciones/models.py:19` ya lo declara; M4-D y M5 formaron cuadrillas de 2 sin error; `teams` tiene 0 filas y consumidores ajenos |
| **Regla técnica** | `cuadrilla(OT) := OT.asignaciones.all()` · integrante := fila · tamaño := `count()` |
| **Impacto** | 0 migraciones, 0 modelos. **3 operaciones nuevas**: `agregar_integrante`, `retirar_integrante`, `cambiar_rol` |
| **PENDIENTE** | **¿La cuadrilla persiste entre OTs o es por OT?** Producción no tiene un solo caso que lo muestre (1 persona/OT en las 3). Si persiste → campo nuevo + migración, y la respuesta de E.1 cambia a "combinación" |

### F-2 — Líder obligatorio

| | |
|---|---|
| **Decisión propuesta** | Una cuadrilla de ≥2 tiene **exactamente un** líder |
| **Evidencia** | **[MEDIDO]** Hoy **no se cumple ni se puede verificar**: las 4 combinaciones contradictorias (A/B/C/D) son posibles; solo "dos principales" está bloqueado; 0 CHECK, 0 triggers |
| **Regla técnica** | `count(es_principal=True) == 1` sobre las filas **vigentes**, evaluado **al cierre** de la transacción (durante `asignar()` hay un instante legítimo con cero) |
| **Impacto** | Por servicio: 0 migraciones, pero **3 vías lo rodean** (admin, ORM, seeds). Por DB: 1 índice + 1 trigger SQL crudo |
| **PENDIENTE** | **¿Desde cuándo aplica?** La OT sin asignar es un estado **deliberado y documentado** (`serializers.py:202-204`, `supervisor.py:478`). "Exactamente un líder siempre" lo ilegaliza. **Decisión empresarial abierta** |

### F-3 — Principal ≡ Líder

| | |
|---|---|
| **Decisión propuesta** (de F-A) | `es_principal=True` ⇔ `rol=tecnico_lider` |
| **Evidencia** | **[MEDIDO]** **No son sinónimos ni conceptos distintos hoy**: `es_principal` tiene **6 consumidores** y decide H-05; `rol` tiene **0 lectores** y no decide nada. La correlación 3/3 de producción coincide con el default del seed y **ningún evento respalda otra vía**. **Las 2 vías de escritura rompen la equivalencia**: crear OT deja `tecnico`+principal; asignar a un segundo deja `lider` sin principal y `ayudante` como principal |
| **Regla técnica** | *(no se puede redactar sin la decisión: ver abajo)* |
| **Impacto** | **[RIESGO]** Declararla invalida los **2** caminos de escritura existentes y hace que `rol` herede la semántica de H-05 — hoy cambiar `rol` no afecta a nada |
| **PENDIENTE** | **¿"Principal" y "líder" son la misma persona por definición?** `es_principal` significa, medido, *"de quién depende que la OT entre en riesgo"*; `rol=tecnico_lider` no significa nada operacionalmente. En una cuadrilla de 3 pueden ser personas distintas. **Decisión empresarial abierta — no la tomo** |

### Decisión transversal (no estaba en F-1/F-2/F-3)

| | |
|---|---|
| **Hallazgo** | **[RIESGO]** El catálogo `ROLES_CUADRILLA`, declarado "cerrado" el 15/09/2026, **no se valida en ejecución**: la API acepta y persiste cualquier cadena con HTTP 200 (K.4) |
| **Impacto sobre F-2/F-3** | **Ambas reglas se apoyan en `rol`.** Construirlas sobre un campo que acepta cualquier valor las deja sin piso |
| **PENDIENTE** | Autorización para corregirlo (`ChoiceField` + `CheckConstraint`). **No parcheado** |

---

## O. Pruebas futuras para F-B

**[DISEÑO]** Las 18 que pide el encargo. No se implementan. Se anota, para cada
una, **qué la haría falsa** — la disciplina del proyecto: una prueba que afirma
que un mecanismo *existe* no prueba que funcione.

| # | Prueba | Afirma sobre el **efecto** | Cómo se verifica que no es falsa |
|:--:|---|---|---|
| 1 | Técnico individual | 1 fila, es principal, `tecnico_principal` lo devuelve | Ya cubierto por la suite de campo |
| 2 | Cuadrilla de 2 | 2 filas vigentes **y el líder sigue siendo principal** | **Desarmar** `agregar_integrante` → debe caer en la conducta M1 (líder pierde principalía) |
| 3 | Cuadrilla de 3+ | 3 filas, 1 principal | El `unique(orden,profile)` ya impide duplicar persona |
| 4 | Exactamente un líder | `count(principal)==1` tras cada operación | **Desarmar la regla** → la prueba debe fallar |
| 5 | Cero líderes | **rechazado al cierre** de la transacción | Debe pasar **con** el instante intermedio de cero dentro de `asignar()` |
| 6 | Dos líderes | rechazado | **Hoy pasaría sin código nuevo**: M4-D demuestra que se aceptan 2 |
| 7 | Principal sin rol líder | según F-3 | **No redactable hasta cerrar F-3** |
| 8 | Líder sin principal | según F-3 | **No redactable hasta cerrar F-3** |
| 9 | Incorporación | +1 fila, **1 evento**, principal **intacto** | Leer con **conexión independiente del ORM** |
| 10 | Retiro | `retirado_en` poblado, fila **no borrada**, 1 evento | Afirmar que la fila **sigue existiendo** |
| 11 | Cambio de líder | principal se mueve, **2** filas tocadas, 1 evento | Encadenar: `anterior` del evento == principal previo |
| 12 | Cambio de cuadrilla | N salidas + M entradas, **un solo `lote`** | Todos los eventos comparten el UUID |
| 13 | Técnico no disponible | H-05 emite señal por **un ayudante** ausente | **Hoy no emite** (G.2). La prueba debe fallar antes del cambio |
| 14 | Líder no disponible | H-05 emite | Ya funciona; sirve de no-regresión |
| 15 | Aislamiento tenant | una OT de otra org → **404**, no 403 | **Conexión independiente del ORM** (K.1: no hay RLS que lo respalde) |
| 16 | Concurrencia | dos incorporaciones simultáneas → estado coherente | **Desarmar el lock** → debe fallar. Respetar el orden de locks del módulo |
| 17 | Historial | cada operación deja **exactamente** 1 evento; un no-op deja **0** | Probar que el instrumento dispara antes de confiar en el cero |
| 18 | Permisos | integrante **no principal** accede; ajeno 404 | **Ya medido y funciona** (M5) — no-regresión |

**[RIESGO]** Las pruebas **7** y **8** no se pueden redactar hoy: su resultado
esperado **es** la decisión F-3. Escribirlas ahora sería inventar la política.

---

## P. Archivos que F-B modificaría

**[DISEÑO]** Ninguno tocado en este paso.

| Archivo | Cambio previsto | Migración |
|---|---|:--:|
| `campo/models.py` | `retirado_en` · `CheckConstraint` del catálogo · índice de líder | **sí** |
| `campo/serializers.py` | `rol` → **`ChoiceField`** (K.4) · serializers de entrada para las 3 operaciones nuevas · **exponer la cuadrilla** en la respuesta (hoy no se expone) | no |
| `campo/services/despacho.py` | `agregar_integrante`, `retirar_integrante`, `cambiar_rol` · reglas de líder · eventos nuevos | no |
| `campo/despacho_views.py` | 3 endpoints nuevos · **`asignar()` en `CrearOrdenView:158` debe pasar `rol` explícito** (hoy deja `tecnico`+principal, C.4) | no |
| `campo/urls.py` | 3 rutas | no |
| `campo/admin.py` | **[RIESGO]** `es_principal`/`rol` a `readonly` — hoy el inline los deja editables y rodea toda regla de servicio | no |
| `campo/permissions.py` | **sin cambios** — ya concede por pertenencia (M5) | no |
| `operaciones/supervisor.py` | `_ordenes_en_riesgo`: mirar **todos** los integrantes, no solo el principal (G.2) | no |
| `operaciones/programacion.py` | **sin cambios**, salvo que se decida exigir cuadrilla al programar (F.2) | no |
| `campo/migrations/00XX_*.py` | 1 migración con los cambios del modelo | **sí** |
| `campo/tests/` + `operaciones/tests/` | las 18 pruebas de la sección O | no |

**[MEDIDO]** `operaciones/programacion.py` **no lee asignaciones en ninguna
línea**, así que F-B no lo toca por defecto — el módulo M03 entero queda al
margen salvo decisión explícita.

---

## Q. GO / NO-GO para F-B

### Los 10 criterios, uno por uno

| # | Criterio | | Sustento |
|:--:|---|:--:|---|
| 1 | **F-1 definido sin ambigüedad** | **NO** | La estructura está clara, pero **falta decidir si la cuadrilla es por OT o persiste entre OTs** (A.4). De esa respuesta dependen: un campo nuevo, una migración y la respuesta de E.1 |
| 2 | **F-2 definido sin ambigüedad** | **NO** | **Falta decidir desde cuándo aplica.** "Exactamente un líder" contradice la OT sin asignar, que es un estado deliberado y documentado (B.10) |
| 3 | **F-3 definido sin ambigüedad** | **NO** | **Es la más abierta de las tres.** No son sinónimos ni conceptos distintos hoy; las 2 vías de escritura rompen la equivalencia propuesta; declararla cambiaría qué ausencia dispara H-05 (C.5) |
| 4 | **`AsignacionTrabajo` evoluciona sin duplicar el concepto** | **SÍ** | **[MEDIDO]** `orden_id` ya agrupa; `teams` no se usa; no hace falta entidad `Cuadrilla` |
| 5 | **Se sabe exactamente qué modificar** | **SÍ** | Sección P: 11 archivos, con el cambio de cada uno |
| 6 | **Se sabe si requiere migración** | **SÍ** | Sección M: **la cuadrilla por OT no la requiere**; el retiro y el cierre del catálogo sí. Verificado que las constraints propuestas no rechazan las filas existentes |
| 7 | **La regla de líder es técnicamente verificable** | **SÍ, con salvedad** | "Como máximo uno" → índice parcial (ya existe uno igual). "Al menos uno" → **solo con trigger `DEFERRABLE`**, porque no es expresable como constraint de Django (B.8) |
| 8 | **Relación con OT/programación clara** | **SÍ** | **[MEDIDO]** La cuadrilla es de la OT; `programacion.py` **no lee asignaciones en ninguna línea**. Se documenta el hueco: una OT `ASIGNADA` con 0 asignaciones es programable (F.2) |
| 9 | **No se inventaron políticas empresariales** | **SÍ** | Las 4 decisiones abiertas se dejan **abiertas y nombradas**, no resueltas |
| 10 | **Seguridad y RLS documentados como están realmente** | **SÍ** | **[MEDIDO]** 0 RLS, 0 políticas, sin `org_id`, `bypassrls=True`. Y se reporta el **bypass del catálogo** (K.4) sin parchearlo |

```
CUMPLEN: 7 de 10        FALLAN: 3 (los tres primeros, y son los decisivos)
```

### Veredicto

# NO-GO

**[PENDIENTE]** Cuatro decisiones empresariales siguen abiertas. El criterio del
encargo es explícito — *"Si alguna decisión empresarial continúa abierta:
NO-GO"* — y **ninguna de las cuatro se puede derivar de la evidencia**:

| # | Decisión abierta | Por qué no la puedo cerrar |
|:--:|---|---|
| **1** | **¿La cuadrilla es por OT o persiste entre OTs?** | Producción tiene **1 persona en cada una de las 3 órdenes**. No existe un solo caso real de cuadrilla. Los datos no distinguen las dos hipótesis |
| **2** | **¿Desde cuándo se exige líder?** | La OT sin asignar es un estado **deliberado**; la regla lo ilegalizaría. Elegir cuál gana es política, no técnica |
| **3** | **¿Principal y líder son la misma persona por definición?** | `es_principal` tiene significado medido (H-05); `rol` no tiene ninguno. Que hoy coincidan en 3 filas es un artefacto de un valor por defecto |
| **4** | **¿Se autoriza cerrar el catálogo de `rol` en ejecución?** | Es una corrección de un bypass real, y toca el contrato de la API (un `rol` fuera de catálogo pasaría de 200 a 400). **No se parchea sin autorización** |

**[RIESGO] La #4 es previa a las otras.** F-2 y F-3 se apoyan **ambas** en
`rol`. Mientras la API acepte cualquier cadena para ese campo, cualquier regla
construida encima es una regla escrita sobre un valor que nadie garantiza.

---

## Anexo — Mediciones

**[MEDIDO]** Contenedor aislado, sin credenciales de producción (verificado con
`env | grep -ci` → **0**).

```
M1  asignar(p1,'tecnico_lider') + asignar(p2,'ayudante')
      p1  rol='tecnico_lider'  es_principal=False
      p2  rol='ayudante'       es_principal=True
      miembros=2  principales=1  tecnico_principal -> p2

M2  POST /asignar/ {"rol": "capitan_pirata_que_no_existe"}
      HTTP=200 · persistido literal · en ROLES_CUADRILLA? False

M3  .save() con rol invalido       -> guarda, sin error
    .full_clean() con el mismo     -> "Value 'inventado_xyz' is not a valid choice."

M4  A lider+principal .......... ACEPTADO
    B lider sin principal ...... ACEPTADO   (tecnico_principal=None)
    C ayudante+principal ....... ACEPTADO
    D dos tecnico_lider ........ ACEPTADO   (lideres=2)
    E dos principales .......... RECHAZADO  (unique_tecnico_principal_por_orden)

M5  principal True · ayudante True · ajeno -> Http404

M6  evento tras asignar() por el servicio ....... 1
    evento tras crear la fila directamente ..... 0  (delta=0)
```

### Producción — foto de cierre

**[MEDIDO]** Solo `SELECT`, `read_only = True`. 15 claves contra la foto de
M03-B1 → **DIFERENCIAS: NINGUNA**.

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
OrdenTrabajo 3 · AsignacionTrabajo 3 (1 persona) · EventoTrabajo 12
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · teams 0 · Profile 5 · operaciones_externas 0
kill switch detenido · tenant_config rapilink v146

campo_asignacion_trabajo:  0 CHECK · 0 triggers · RLS False · sin org_id
eventos de tipo asignacion/reasignacion: 0
```

---

```
codigo ......... 0 archivos modificados     pruebas ... 0 archivos (el temporal se borro)
migraciones .... 0     modelos .... 0     endpoints .... 0     constraints .... 0
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no

VEREDICTO F-B .. NO-GO   (4 decisiones empresariales abiertas)
```
