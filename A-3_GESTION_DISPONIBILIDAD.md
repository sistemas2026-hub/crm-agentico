# A-3 — Gestión operativa de disponibilidad

**Alcance:** el proceso por el que se registra y corrige la disponibilidad de un
técnico. **No se define capacidad** — sigue **[PENDIENTE — D-4 / K-02]**.
**Fecha:** 2026-09-17 · **No se implementó nada.**

**Etiquetas:** **[MEDIDO]** · **[DOCUMENTADO]** · **[DISEÑO]** ·
**[DEPENDENCIA]** · **[RIESGO]** · **[PENDIENTE]**

---

## 0. El hallazgo que condiciona todo el diseño

D-4.1 encontró que la única vía de registro es el admin de Django. A-3 fue a ver
**si ese admin puede quedar como vía de contingencia**, y encontró que no, por un
motivo que no se veía desde afuera.

**[MEDIDO]** `/admin/` está en `EXEMPT_PATHS` del middleware `RequireOrgContext`
(`common/middleware/rls_context.py:123`). **El admin NO fija `app.current_org`.**

**[MEDIDO]** Y la política de aislamiento es:

```sql
org_id::text = NULLIF(current_setting('app.current_org', true), '')
```

**[DOCUMENTADO]** El propio archivo explica qué pasa con contexto vacío, para el
caso hermano de los endpoints públicos — y dice que fue **verificado**:

> *"`_set_org_context` returns early when request.org is None, so these requests
> run with `app.current_org` empty, and the isolation policy … matches nothing
> when empty. **Verified as `crm_user` (non-superuser, no BYPASSRLS)**: invoice,
> estimate and csat_survey all return 0 rows with empty context."*

> **[RIESGO CRÍTICO]** El admin funciona hoy **solo porque el runtime se conecta
> como `postgres`, que tiene BYPASSRLS**. Después de B-7 —con `crm_user`— una
> pantalla de admin sobre `DisponibilidadTecnico` **mostraría 0 filas y no podría
> insertar**.
>
> **La única vía de registro que existe hoy es también la que B-7 rompe.**

**Consecuencia para A-3:** el admin **no puede ser la vía de contingencia** sin
resolver antes su contexto de organización. Queda como **[GAP]**, no como plan.

---

## 1. Estado actual

### 1.1 — `DisponibilidadTecnico`

**[MEDIDO]** Producción, 2026-09-17:

| | |
|---|---|
| **Filas** | **0** |
| **Tabla** | `public.operaciones_disponibilidad` |
| **Campos** | `id`, `org_id`, `profile_id`, `fecha`, `hora_inicio`, `hora_fin`, `disponible`, `motivo`, `zona`, `created_by_id`, `updated_by_id`, `created_at`, `updated_at` |
| **Constraints** | `disponibilidad_franja_valida` (`hora_fin > hora_inicio`) · **`ausencia_exige_motivo`** (`disponible = True OR motivo <> ''`) |
| **Índices** | 6 — incluido el compuesto **`(org_id, fecha, profile_id)`**, que es exactamente el que usa la consulta de H-05 |
| **RLS** | **habilitada ✔ y FORZADA ✔** |
| **Políticas** | **2**: `org_isolation` (ALL) y `org_insert_check` (INSERT), ambas contra `app.current_org` |

### 1.2 — La superficie operativa

**[MEDIDO]**

| Pieza | Estado |
|---|---|
| **Rutas** | **ninguna** |
| **Serializers** | **ninguno** |
| **Vistas** | **ninguna** |
| **Permisos** | **ninguno propio** |
| **Admin** | `admin.site.register(DisponibilidadTecnico)` — **registro pelado** |

**[MEDIDO]** El contraste con la tabla vecina es deliberado y está escrito:
`PropuestaSupervisor` **sí** tiene un `ModelAdmin` que prohíbe crear y editar —
*"un admin que permita editar el estado a mano abre un camino sin rastro"*.
`DisponibilidadTecnico` **no tiene** esa protección: es plenamente editable.

**[MEDIDO]** Quién llega al admin: **1 de 5 usuarios** (`is_staff`).

---

## 2. Ocho conceptos que no son sinónimos

**[DISEÑO]** La distinción importa porque A-3 diseña **el primero**, y el resto
son efectos de otros módulos.

| Concepto | Qué responde | Dónde vive | ¿A-3 lo diseña? |
|---|---|---|:--:|
| **Disponibilidad** | ¿esta persona puede trabajar el jueves de 8 a 12? | `DisponibilidadTecnico` (`disponible=True`) | **SÍ** |
| **Ausencia** | ¿esta persona NO puede, y por qué? | ídem (`disponible=False` + `motivo`) | **SÍ** |
| **Asignación** | ¿quién es responsable de esta orden? | `AsignacionTrabajo` | no |
| **Programación** | ¿qué se planificó para esta semana? | `ProgramacionSemanal` / `ProgramacionOrden` | no — M03 |
| **Reprogramación** | mover trabajo a otra fecha | M03 | no |
| **Redistribución** | mover trabajo a otra persona | M03 | no |
| **Bloqueo** | el trabajo se detuvo por algo | `ActividadOperativa.estado_operativo` | no |
| **Novedad** | ¿por qué se detuvo? | `NovedadOperativa.TIPOS` (8 causas) | no |

> **[DOCUMENTADO]** `ausencia` **es una de las ocho causas** de `NovedadOperativa`,
> pero registrar una novedad de tipo `ausencia` sobre un trabajo **no es lo mismo**
> que declarar que una persona no está disponible. La novedad explica un trabajo
> detenido; la disponibilidad describe a la persona.

---

## 3. Actores

**[MEDIDO]** Roles que **existen**:

| Origen | Valores |
|---|---|
| `Profile.ROLES` | `ADMIN`, `SUPERVISOR`, `OPERACIONES`, `USER` |
| `ROLES_GESTION` | `{ADMIN, SUPERVISOR, OPERACIONES}` |
| `AsignacionTrabajo.ROLES_CUADRILLA` | `tecnico`, `tecnico_lider`, `ayudante`, `chofer`, `supervisor` |
| Acceso al admin | `is_staff` — **1 de 5 usuarios** |

**[MEDIDO]** Perfiles reales en producción: `{ADMIN: 1, USER: 4}`. **No existe
ningún perfil `SUPERVISOR` ni `OPERACIONES` cargado.**

### Matriz de actores

`[E]` existente · `[D]` diseño · `[P]` pendiente de decisión

| Actor | Consultar | Registrar | Modificar | Anular/corregir | Validar |
|---|---|---|---|---|---|
| **Técnico** (`USER`) | **[P]** | **[P]** | **[P]** | **[P]** | no aplica |
| **Auxiliar** (`ayudante`) | **[P]** | **[P]** | **[P]** | **[P]** | no aplica |
| **Supervisor** (`SUPERVISOR`) | **[P]** | **[P]** | **[P]** | **[P]** | **[P]** |
| **Jefe de Operaciones** (`OPERACIONES`) | **[P]** | **[P]** | **[P]** | **[P]** | **[P]** |
| **Administración** (`ADMIN`) | **[E]** vía admin | **[E]** vía admin | **[E]** vía admin | **[E]** vía admin | **[P]** |
| **Supervisor NOC IA** | **[E]** lee en `_ordenes_en_riesgo` | **NO — nunca** | **NO** | **NO** | **NO** |

> **[MEDIDO]** Solo una fila tiene `[E]` en registrar, y es por el admin —
> el mismo que el §0 muestra que B-7 rompe.
>
> **[DOCUMENTADO]** La última fila no es una decisión pendiente: el Supervisor
> NOC IA **no escribe disponibilidad por diseño**. Es nivel 1 —recomienda, no
> ejecuta— y `supervisor.py` no tiene ninguna función que escriba esa tabla.

---

## 4. Responsable de registro

**[PENDIENTE — DECISIÓN DE NEGOCIO]** No existe ninguna definición vigente.

**[MEDIDO]** Lo único que hay es un **acceso técnico**, no una designación.

**[DISEÑO]** Candidatos, **para análisis. No se elige ninguno.**

| Cargo | A favor | En contra |
|---|---|---|
| Jefe de Operaciones | define el procedimiento; ya revisa las propuestas M09 | puede no enterarse el mismo día de un imprevisto |
| Supervisor de Operaciones / despacho | es quien primero se entera y quien reprograma | **[MEDIDO]** no hay ningún perfil `SUPERVISOR` cargado hoy |
| Administración / RR. HH. | ya gestiona vacaciones e incapacidades | puede no ver el impacto operativo del día |
| El propio técnico | se entera primero | **[RIESGO]** autodeclararse ausente sin validación |

> **No se escoge al Jefe de Operaciones solo porque sea el revisor del
> Supervisor** (§6 del encargo). Son responsabilidades distintas: una es revisar
> recomendaciones, la otra es cargar un hecho operativo.

---

## 5. Momento del registro

**[PENDIENTE — DECISIÓN DE NEGOCIO]** No existe definición. **No se fija ninguna
hora límite.**

**[DISEÑO]** Tres momentos, que no compiten — **conviven**:

| Tipo | Cuándo | Para qué sirve |
|---|---|---|
| **Registro preventivo** | se conoce con antelación: vacaciones, permiso, capacitación | permite **no programar** sobre esa persona. Evita el conflicto en origen |
| **Registro de novedad ocurrida** | el mismo día: incapacidad, imprevisto | permite **detectar** el conflicto con la programación que ya existe |
| **Corrección posterior** | se registró mal, o el hecho cambió | mantiene la historia fiel — ver §7 |

**[DISEÑO]** Lo único que se puede afirmar sin decidir, porque se deriva del
código y no de una política:

> **H-05 solo es útil si la ausencia se registra ANTES de la fecha programada de
> la orden.** Registrada después, la señal llega cuando la orden ya pasó.

Eso acota la decisión; **no la toma**.

---

## 6. Datos

**[MEDIDO]** **No se agrega ningún campo. No se modifica ningún modelo.**

| Campo | Existe | Obligatorio técnico | Regla actual | Decisión pendiente |
|---|:--:|:--:|---|---|
| `profile` | **sí** | **sí** (FK NOT NULL) | FK a `Profile` | — |
| `fecha` | **sí** | **sí** (NOT NULL) | una fecha, **un solo día** | **rangos multi-día** |
| `hora_inicio` | **sí** | **sí** (NOT NULL) | `disponibilidad_franja_valida` | — |
| `hora_fin` | **sí** | **sí** (NOT NULL) | `hora_fin > hora_inicio` | — |
| `disponible` | **sí** | **sí** (NOT NULL) | booleano; distingue turno de ausencia | — |
| `motivo` | **sí** | **sí cuando `disponible=False`** | **`ausencia_exige_motivo`** | **¿catálogo cerrado?** |
| `zona` | **sí** | no | texto libre | ¿debe ser catálogo? |
| `org` | **sí** | **sí** | RLS + política de INSERT | — |
| `created_by` / `updated_by` | **sí** | no (nullable) | `BaseModel` | ver §8 |
| `created_at` / `updated_at` | **sí** | **sí** | `BaseModel` | — |

### Gaps de campo — **[GAP]**, no se implementan

| # | Campo ausente | Para qué haría falta | ¿Lo necesita H-05? |
|:--:|---|---|:--:|
| G-1 | **rango de fechas** | una ausencia de 15 días exige hoy **15 filas** | no |
| G-2 | **tipo** (catálogo) | agrupar y medir: *¿cuántos días de incapacidad este trimestre?* | no |
| G-3 | **estado** (solicitada/aprobada) | si una ausencia se autoriza antes de valer | no |
| G-4 | **evidencia** (adjunto) | incapacidad con soporte médico | no |
| G-5 | **motivo de corrección** | por qué se editó una ausencia — ver §7 | no |

> **[MEDIDO]** Ninguno de los cinco es necesario para H-05: los cuatro campos que
> el detector usa —`profile`, `fecha`, `disponible`, `motivo`— **existen, son
> NOT NULL y están respaldados por constraint.**

---

## 7. Correcciones e historial

**[MEDIDO]** Hoy, una fila de `DisponibilidadTecnico` se puede **editar o borrar
sin dejar rastro del valor anterior**: `updated_by`/`updated_at` dicen *quién y
cuándo*, **nunca qué cambió**.

**[DISEÑO]** Cuatro operaciones que no son la misma:

| Operación | Qué significa | Riesgo si se confunde |
|---|---|---|
| **Editar** | corregir un tipeo (una hora mal puesta) | ninguno, si queda registro |
| **Corregir** | el hecho era otro: no era incapacidad, era permiso | **se pierde por qué se creyó lo primero** |
| **Anular** | la ausencia no ocurrió: el técnico sí vino | **borrar la fila borra que alguien la declaró** |
| **Reemplazar** | cambió el alcance: era un día, son tres | puede dejar huérfano el registro original |

> **[DISEÑO] Regla propuesta:** **anular no debe ser borrar.** Una ausencia que
> se declaró y no ocurrió es un hecho: alguien la declaró, y una programación
> pudo haberse movido por eso. Borrarla hace desaparecer la causa de una decisión
> que sí se tomó.
>
> **[PENDIENTE — DECISIÓN DE NEGOCIO]** Si anular debe conservar la fila con una
> marca, o si basta con el historial de auditoría.

**[MEDIDO]** Mecanismos de historial que **ya existen** y podrían reutilizarse —
**no se crea ninguno nuevo**:

| Mecanismo | Qué registra | ¿Sirve? |
|---|---|---|
| **`common.Activity`** vía `operaciones/auditoria.py` | actor, org, entidad, acción, **estado anterior/nuevo**, motivo, metadata | **sí, y es el más completo**: ya registra antes/después por campo (M09-F) |
| **`django_admin_log`** | **[MEDIDO]** existe, 0 filas. `user_id`, `action_time`, `action_flag`, `object_repr`, `change_message` | **parcial**: dice quién y cuándo, **no el valor anterior ni el motivo de negocio** |
| `BaseModel` (`updated_by`/`updated_at`) | último que tocó | **insuficiente solo** |

**[DISEÑO]** El mecanismo adecuado es `common.Activity`: es el mismo que audita
las decisiones sobre propuestas, ya guarda antes/después, y **no hay que crear
nada**. `auditoria.ENTIDAD_*` tendría que admitir un valor para disponibilidad —
**[GAP]**, no implementado.

---

## 8. Auditoría

**[DISEÑO]** Lo que debería quedar registrado, y con qué se cubre hoy:

| Dato | ¿Cubierto? | Con qué |
|---|---|---|
| **quién** | **sí** | `created_by` / `updated_by`; `Activity.user` |
| **cuándo** | **sí** | `created_at` / `updated_at`; `Activity.created_at` |
| **qué técnico** | **sí** | `profile` |
| **qué fecha** | **sí** | `fecha` |
| **qué cambió** | **NO** | **[GAP]** — `Activity.metadata` podría, pero nadie lo escribe |
| **por qué** | **parcial** | `motivo` es el de la ausencia, **no el de la corrección** |
| **quién corrigió** | **parcial** | `updated_by` da el último, **no la secuencia** |

> **[GAP]** Tres de siete no están cubiertos. Los tres se resuelven llamando a
> `auditoria.registrar(...)` desde donde se escriba la disponibilidad — **que es
> justamente el lugar que no existe** (§1.2).

---

## 9. Seguridad

**[MEDIDO]** Lo que ya está:

| Control | Estado |
|---|---|
| RLS habilitada y **forzada** | ✔ |
| Política de aislamiento por org | ✔ `org_isolation` |
| Política de INSERT | ✔ `org_insert_check` |
| Aislamiento de aplicación | **n/a** — no hay vista que filtre |
| `EsJefeDeOperaciones` | **existe**, pero **no se aplica** a esta tabla |
| `ROLES_GESTION` | existe: `{ADMIN, SUPERVISOR, OPERACIONES}` |

### Gaps de seguridad — **[GAP]**, no se corrigen

| # | Gap | Evidencia |
|:--:|---|---|
| **S-1** | **El admin no fija `app.current_org`** → la RLS **no lo protege**; funciona solo por BYPASSRLS de `postgres` | **[MEDIDO]** `/admin/` en `EXEMPT_PATHS` |
| **S-2** | **B-7 rompe la única vía de registro** | consecuencia de S-1 |
| **S-3** | `DisponibilidadTecnico` es **plenamente editable** en el admin, sin las restricciones que sí tiene `PropuestaSupervisor` | **[MEDIDO]** `admin.site.register` pelado |
| **S-4** | No hay permiso propio: cualquier `is_staff` con el permiso del modelo puede escribir | **[MEDIDO]** |
| **S-5** | Una ausencia se puede **borrar** sin dejar rastro del valor anterior | **[MEDIDO]** §7 |

> **S-1 y S-2 son el mismo hecho visto de dos lados**, y es el hallazgo del §0.

---

## 10. Relación con la programación

**[DISEÑO]** El escenario, y qué debe producir:

```
   técnico ausente  +  OT programada ese día  +  él es el principal
                              ↓
                    ALERTA  →  ESCALAMIENTO
```

| Efecto | ¿Corresponde? | Por qué |
|---|:--:|---|
| **Alerta** | **SÍ** | es lo que H-05 hace: emite una señal |
| **Escalamiento** | **SÍ** | toda propuesta va a revisión humana (M09-F) |
| **Recomendación** | **SÍ, acotada** | puede recomendar *revisar*; **no puede recomendar a quién reasignar** — M09-C prohíbe que el Supervisor nombre personas |
| Conflicto (estado) | **no** | exigiría un campo de estado que no existe |
| **Cancelar la OT** | **NO** | — |
| **Reasignar automáticamente** | **NO** | M03 es el dueño del efecto |
| **Reprogramar automáticamente** | **NO** | ídem |

> **[DISEÑO] Una ausencia NO cancela una asignación.** La ausencia es un hecho
> sobre una persona; cancelar es una decisión sobre el trabajo. El sistema no
> puede saber si se cubre con otro técnico, se mueve, o se hace igual porque la
> ausencia era de media jornada.
>
> **[DOCUMENTADO]** Y coherente con K-04: la ausencia es **una de las ocho causas
> legítimas**, no una falta. Que un técnico esté ausente no es incumplimiento de
> nadie.

---

## 11. Relación con H-05

**[MEDIDO]** **No se modificó nada**: ni `habilidades.py`, ni la ficha H-05, ni
`supervisor.py`, ni el detector, ni `PropuestaSupervisor`, ni H-C4.

**H-05 detecta hoy:**

> Órdenes programadas cuyo **técnico principal** está declarado **ausente ese
> día**.

**H-05 NO calcula:**

```
capacidad general · productividad · carga · complejidad
desplazamiento · capacidad disponible
```

> **[GAP DE HABILIDAD]** La ficha se llama *"Estimar riesgo operacional de una
> orden por capacidad"*. El código detecta un conflicto de ausencia. El nombre
> promete más de lo que la función hace. **Registrado, no corregido.**

### Matriz: qué necesita H-05

| Necesidad H-05 | Existe | Fuente | Estado |
|---|:--:|---|---|
| Estructura de disponibilidad | **sí** | `DisponibilidadTecnico` | **lista** |
| Los 4 campos que usa | **sí** | NOT NULL + constraints | **listos** |
| Índice para la consulta | **sí** | `(org_id, fecha, profile_id)` | **listo** |
| **Datos de disponibilidad** | **no** | **0 filas** | **falta — A-3** |
| **Vía de registro operativa** | **no** | solo admin, y B-7 lo rompe | **falta — §0** |
| **OT con `programada_para`** | **no** | **0 de 3** | **falta — M03** |
| **OT en estado `asignada`** | **no** | **0 de 3** (`en_sitio`/`completada_campo`) | **falta — M03** |
| Técnico principal asignado | **sí** | 3 de 3, `es_principal=True` | **listo** |

> **[MEDIDO]** De ocho requisitos, **cuatro faltan**. Registrar ausencias **no
> basta**: también hace falta que M03 programe órdenes en estado `asignada`.

---

## 12. Flujo conceptual

**[DISEÑO]** Nada se ejecuta automáticamente.

```
   Novedad / información de disponibilidad
                  ↓
        ¿quién está autorizado?          ← [PENDIENTE] §4
                  ↓
        REGISTRO por una vía operativa   ← [GAP] no existe · §0
                  ↓
        Validación de datos              ← [MEDIDO] ya existe:
                                            hora_fin > hora_inicio
                                            ausencia exige motivo
                                            org por RLS
                  ↓
        Disponibilidad registrada
                  ↓
        AUDITORÍA                        ← [GAP] §8: falta el qué cambió
                  ↓
        ¿hay programación para esa persona ese día?
             ↙                    ↘
           NO                     SÍ
            ↓                      ↓
       continuar            H-05 emite SEÑAL
                                   ↓
                            PROPUESTA nivel 1
                                   ↓
                            REVISIÓN HUMANA        ← la cadena termina aquí
                                   ↓
                     el humano decide: cubrir / mover / dejar
```

**[MEDIDO]** De los siete pasos, **tres ya están construidos** (validación,
detección, revisión humana), **dos faltan** (vía de registro, auditoría del
cambio) y **dos son decisiones pendientes** (quién autoriza, qué hace el humano).

---

## 13. El admin: ¿contingencia o no?

**[DISEÑO]** El encargo pregunta si el admin debe quedar como vía
administrativa/contingencia mientras se construye una operativa.

**La respuesta honesta es: hoy no puede, y hay que decirlo.**

| Condición para ser contingencia | ¿Se cumple? |
|---|:--:|
| Existe y es alcanzable | **sí** — 1 de 5 usuarios |
| Valida los datos | **sí** — los constraints operan igual |
| Respeta el aislamiento por organización | **NO** — `/admin/` está exento; hoy depende de BYPASSRLS |
| **Sobrevive a B-7** | **NO** — con `crm_user` mostraría 0 filas |
| Deja auditoría suficiente | **parcial** — `django_admin_log` no guarda el valor anterior |
| Es usable por quien debe registrar | **no evaluable** — no hay responsable definido |

> **[DISEÑO]** Para que el admin sirva de contingencia haría falta que fijara
> `app.current_org`. **Eso es una modificación de código y del middleware: §26
> obliga a detenerse.** Queda como **[GAP]**.
>
> **No se modificó el Admin** (§13 del encargo).

---

## 14. Gaps

| # | Gap | Tipo | Bloquea |
|:--:|---|---|---|
| **A3-1** | **El admin no fija `app.current_org`; B-7 rompe la única vía de registro** | seguridad + operativo | **todo el proceso** |
| **A3-2** | No hay ruta, vista, serializer ni permiso | operativo | el registro por cualquiera que no sea `is_staff` |
| **A3-3** | La auditoría no registra **qué cambió** | auditoría | corregir con trazabilidad |
| **A3-4** | `auditoria.ENTIDAD_*` no contempla disponibilidad | auditoría | reutilizar `common.Activity` |
| **A3-5** | No hay rango multi-día: una fila por día | datos | comodidad y fiabilidad de carga |
| **A3-6** | Anular = borrar: se pierde que alguien lo declaró | historial | §7 |
| **A3-7** | `DisponibilidadTecnico` plenamente editable en el admin | seguridad | — |
| **A3-8** | **M03 sin órdenes programadas** (`0/3`) ni en `asignada` (`0/3`) | dependencia | que H-05 emita, aun con ausencias |
| **A3-9** | `business_calendar`: `timezone=UTC`, **0 festivos** | dependencia | decisiones futuras de jornada — **no corregido** (§19) |

---

## 15. Decisiones pendientes

| Decisión | Estado | Evidencia | Responsable de decidir |
|---|---|---|---|
| **Quién registra** | **PENDIENTE** | no existe procedimiento; solo acceso técnico | Jefe de Operaciones |
| **Quién consulta** | **PENDIENTE** | no hay vista | Jefe de Operaciones |
| **Quién corrige** | **PENDIENTE** | hoy cualquiera con acceso al admin | Jefe de Operaciones |
| **Quién valida** | **PENDIENTE** | no existe concepto de validación | Jefe de Operaciones / RR. HH. |
| **Por dónde se registra** | **PENDIENTE** | **[MEDIDO]** solo admin, y B-7 lo rompe | Jefe de Operaciones + producto |
| Cuándo se registra | **PENDIENTE** | no existe definición | Jefe de Operaciones |
| Si anular conserva la fila | **PENDIENTE** | hoy se borra | Jefe de Operaciones |
| Si hace falta catálogo de tipos | **PENDIENTE** | texto libre | Jefe de Operaciones / RR. HH. |
| Si una ausencia se aprueba | **PENDIENTE** | no existe el campo | Jefe de Operaciones / RR. HH. |
| Si se admiten rangos multi-día | **PENDIENTE** | una fila por día | Jefe de Operaciones |
| Si la ausencia de ayudante/chofer alerta igual | **PENDIENTE** | H-05 mira solo al principal | Jefe de Operaciones |
| **Motivo obligatorio en ausencia** | **YA DEFINIDO** | `ausencia_exige_motivo` | — implementado |
| **Franja válida** | **YA DEFINIDO** | `disponibilidad_franja_valida` | — implementado |
| **Aislamiento por organización** | **YA DEFINIDO** | RLS forzada, 2 políticas | — implementado |
| **La ausencia no cancela la asignación** | **[DISEÑO]** | K-04 + nivel 1 | Jefe de Operaciones (validar) |
| **El Supervisor NOC IA no escribe disponibilidad** | **YA DEFINIDO** | ninguna función lo hace | — por diseño |

---

## 16. Conclusión

**[MEDIDO]** La estructura de datos está **completa y bien protegida**: seis
índices, dos constraints de negocio, RLS forzada con dos políticas, y los cuatro
campos que H-05 usa son obligatorios.

**Lo que falta no es la tabla: es todo lo que la rodea.**

Y el orden importa, porque A-3 encontró que la dependencia no es la que parecía:

> **No se puede decidir *quién* registra antes de resolver *por dónde*** — y
> *por dónde* no es solo que falte una pantalla: **es que la única vía que existe
> hoy deja de funcionar con B-7**, porque `/admin/` no fija el contexto de
> organización y hoy se sostiene únicamente sobre el BYPASSRLS de `postgres`.
