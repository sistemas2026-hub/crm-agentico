# M03-B — VALIDADO

**Programación básica de una Orden de Trabajo · Informe de implementación**
Fecha: 2026-09-18

---

## Resumen

```
Archivos creados:      2      Archivos modificados:   3  (+106 líneas, -0)
Migraciones:           0      ← "No changes detected"
Modelos nuevos:        0      Tablas nuevas:          0
Endpoint:              1      POST /api/campo/trabajos/<pk>/programar/

Tests M03-B:          29 passed / 0 failed / 0 skipped
Regresión completa:  506 passed / 0 failed / 0 skipped   (477 base + 29)

Transacción:          UNA sola, con select_for_update  -- verificado desarmándolo
Persistencia:         verificada por conexión independiente del ORM
Rollback:             verificado rompiendo la operación en su último paso
Cross-tenant:         A→A 201 · A→B 404 · B→A 404 · 0 escrituras cruzadas
Efectos externos:     0        -- con el instrumento probado antes de leer su cero
Producción:           SIN CAMBIOS  (solo lectura, read_only = True)
Commit:               no
```

---

## 1. Objetivo

Habilitar la **primera operación real de programación**: poner fecha a una orden
escribiendo su línea de plan **y** `OrdenTrabajo.programada_para` de forma
coherente.

M03-A midió que las tres tablas del plan existían con RLS, constraints y registro
en el admin, y **sin un solo escritor**: 0 filas, 0 servicios, 0 endpoints. M03-B
es ese escritor, y nada más.

---

## 2. Estructuras reutilizadas — cero estructuras nuevas

| Estructura | Qué aporta | Cambios |
|---|---|---|
| `ProgramacionSemanal` | el plan de la semana | **ninguno** |
| `ProgramacionOrden` | la línea: orden, día, hora, zona, prioridad, secuencia, estado | **ninguno** |
| `OrdenTrabajo.programada_para` | el "cuándo" vigente | **ninguno** |
| `EventoTrabajo` | la bitácora append-only donde ya vive la reasignación | **ninguno** |
| `IsCampoAuthenticated` + `ROLES_GESTION` | el permiso de despacho | **ninguno** |
| `_orden_o_404`, `_exigir_gestion`, `manejar_idempotencia` | 404 estricto, 403 por rol, idempotencia | **ninguno** |

**[MEDIDO]** §25 satisfecho antes de escribir la primera línea de prueba:

```
python manage.py makemigrations --check --dry-run
→ No changes detected
```

---

## 3. Servicio

**`operaciones/programacion.py`** → `programar_orden(...)`.

### Por qué vive en `operaciones/` y no en `campo/`

**[MEDIDO]** La operación toca modelos de los dos módulos, así que la dirección
de la dependencia decide dónde va:

```
operaciones  ──importa──>  campo        ya existía (FK a OrdenTrabajo, supervisor.py)
campo        ──importa──>  operaciones  NO existía  (medido: 0 coincidencias)
```

Poner el servicio en `campo/` habría cerrado el ciclo. Puesto en `operaciones/`,
la flecha nueva (`campo/despacho_views.py` → `operaciones/programacion.py`) va en
la misma dirección que la que ya había.

### Los siete pasos, todos dentro de la misma transacción

```
1. actor y fecha presentes; la fecha trae zona horaria
2. la orden pertenece a request.org   Y   el plan pertenece a request.org
3. el plan no está cerrado
4. la fecha cae dentro de la semana del plan
5. SELECT ... FOR UPDATE sobre la orden  →  se relee estado y programada_para
6. estado programable  y  no programada ya
7. crear ProgramacionOrden + escribir programada_para + EventoTrabajo
```

### §3 — el GAP de estados, y qué se hizo con él

**[GAP, ya reportado en M03-A]** **Ningún estado de `OrdenTrabajo` restringe hoy la
escritura de `programada_para`.** El campo se fija al crear la orden y nada lo
valida.

El §3 del encargo dice: *documentar el GAP y utilizar solamente un estado
inequívocamente válido si existe*. **Existe uno**, y su semántica no la inventé:
la establece el detector de M09 (`supervisor.py:340`), escrito antes que esto:

> *"`estado_operativo = asignada` YA implica que no arrancó: ninguna transición
> vuelve a ese estado y `iniciada_en` sólo se escribe al salir de él."*

```python
ESTADOS_PROGRAMABLES = frozenset({OrdenTrabajo.ASIGNADA})
```

Los otros seis quedan fuera **explícitamente**, y hay una prueba parametrizada que
lo verifica en los seis. `correccion_requerida` merece mención aparte: un trabajo
devuelto probablemente deba poder reprogramarse, pero **eso es reprogramar**, que
es la fase siguiente. Queda como **decisión de negocio pendiente**.

### La única regla que derivé, dicha como tal

**[REGLA DERIVADA — confirmar con negocio]** La fecha debe caer dentro de la
semana del plan (`semana_inicio` … `+6 días`).

No hay constraint en la base que lo imponga ni política de empresa que lo declare.
Sale del propio campo, cuyo `help_text` dice *"Lunes de la semana que planifica"*:
una línea fechada fuera de esa semana deja al plan diciendo algo que no es.

> **Se marca como derivada y no como medida.** Si el negocio quiere líneas que
> crucen semanas, esta comprobación es lo que hay que quitar — y está en una sola
> condición.

---

## 4. Endpoint

```
POST /api/campo/trabajos/<uid:pk>/programar/
```

**Junto a `crear`, `asignar` y `validar`, no en una API paralela** (§11): es el
mismo recurso y el mismo verbo operativo que `asignar`.

| Entrada | |
|---|---|
| `programacion_semanal_id` | UUID, obligatorio |
| `programada_para` | fecha-hora con zona, obligatorio |
| `zona`, `prioridad`, `secuencia` | opcionales; sin ellos, los `default` del modelo |

**[DISEÑO]** `ProgramarSerializer` **no declara `org` ni `organization_id`**. Misma
decisión que A-3.3: lo que el cliente no debe elegir, no se declara — así un
`organization_id` en el cuerpo no se ignora *después*, **no llega a existir**.
Verificado: un POST con `org`, `org_id` y `organization_id` apuntando a otra
empresa crea la fila en la propia.

| Respuesta | Cuándo |
|---|---|
| **201** | programada |
| **400** | estado no programable · plan cerrado · fecha fuera de la semana |
| **403** | rol sin gestión |
| **404** | la orden o el plan no existen **en esta organización** |
| **409** | **ya programada** — con `"pendiente": "REPROGRAMACION"` |

**409 y no 400** en el conflicto: la petición es válida, lo que choca es el estado
del recurso.

---

## 5. Permisos

**[MEDIDO]** `IsCampoAuthenticated` + `_exigir_gestion` → `ROLES_GESTION`
(`{ADMIN, SUPERVISOR, OPERACIONES}`). **Reutilizados sin modificar. 0 roles
nuevos.**

Programar es de quien coordina, igual que crear, asignar y validar. Un `USER`
recibe 403; sin sesión, 403.

---

## 6. Transacción, concurrencia y el lock que sí se probó

`@transaction.atomic` + `select_for_update()` sobre la orden **antes** de leer su
estado.

### La prueba de concurrencia se verificó desarmando el mecanismo

Dos peticiones simultáneas programando la misma orden con fechas distintas dan
`[201, 409]`. **Pero esa aserción pasaría igual si los dos hilos corrieran en
serie y el lock no hiciera nada.**

Así que quité el `select_for_update()` y volví a correr **solo esa prueba**:

```
sin lock  →  FAILED test_b8_dos_peticiones_simultaneas_programan_una_sola_vez
con lock  →  1 passed
```

**La prueba mide el lock.** Restaurado y confirmado.

---

## 7. Duplicados (§8)

**[MEDIDO]** Constraints existentes, sin agregar ninguna:
`unique(programacion, orden)` y `unique(org, semana_inicio)`.

Comportamiento: si la orden ya tiene `programada_para` **o** ya tiene una línea de
plan → **409, sin escribir nada**.

> Se mira **por las dos vías** a propósito. Una orden con `programada_para` puesto
> y sin línea de plan es exactamente lo que el campo permite hoy (se fija al
> crear). Programar encima dejaría una línea nueva junto a una fecha que nadie
> puede explicar — que es la incoherencia que M03-B existe para no producir.
> Verificado en `test_b6b`.

**No se implementó reprogramación.**

---

## 8. Persistencia y coherencia (§16, §27)

Leído con una **conexión psycopg independiente del ORM**:

| OT | ProgramacionOrden | programada_para | Coherente |
|---|---|---|:--:|
| #8001 (M03-B Org A) | 2026-10-07 09:00 `[planificada]` | 2026-10-07T09:00+00:00 | **SÍ** |
| #8002 (M03-B Org B) | 2026-10-08 14:30 `[planificada]` | 2026-10-08T14:30+00:00 | **SÍ** |

```sql
filas incoherentes (una parte sin la otra) ........... 0
líneas con organización distinta a la de su orden .... 0
```

### Un detalle que no es de formato

`ProgramacionOrden.dia` se calcula con **`timezone.localtime(...)`, la misma
conversión que usa H-05** (`_ordenes_en_riesgo` compara contra
`timezone.localtime(o.programada_para).date()`).

> Con otra conversión —UTC crudo, o la fecha del servidor— la línea y la fecha que
> H-05 mira podrían caer en días distintos, y el detector buscaría la ausencia en
> el día equivocado **sin que nada fallara**. Hoy `TIME_ZONE = "UTC"`, así que
> coinciden; el punto es que sigan coincidiendo si eso cambia.

---

## 9. Rollback (§17)

Se rompe la operación **después** de sus dos escrituras: el evento de auditoría es
el último paso, así que cuando revienta ahí, la línea y `programada_para` ya están
escritos dentro de la transacción.

```
ProgramacionOrden ....... 0 filas
programada_para ......... NULL
EventoTrabajo ........... 0 de tipo 'programacion'
```

Verificado **dos veces**: por ORM (`test_b7`) y **desde fuera, con conexión
independiente** (`test_b7b`). La atomicidad es real, no un decorador decorativo.

---

## 10. Cross-tenant (§13, §18)

| Dirección | Esperado | Obtenido |
|---|---|---|
| A → OT de A + plan de A | permitido | **201** |
| A → OT de A + **plan de B** | rechazado | **404**, 0 escrituras |
| A → **OT de B** | rechazado | **404**, 0 escrituras |
| B → OT de A | rechazado | **404**, 0 escrituras |
| B → OT de B + plan de B | permitido | **201** |

**404 y no 403**: un 403 confirmaría que el recurso existe. Mismo criterio que el
resto del módulo.

**[DISEÑO]** Las **dos** pertenencias se comprueban, y también **en el servicio**,
no solo en la vista: una orden legítima de A metida en un plan de B cruzaría las
empresas por la vía del plan. Hay prueba que llama al servicio directamente, sin
pasar por la vista (`test_b3b`).

---

## 11. Auditoría (§14)

**Mecanismo existente, tabla nueva ninguna.** `EventoTrabajo`, el mismo sitio donde
`despacho.asignar` deja la reasignación:

```
tipo    "programacion"
profile el actor de la petición          ← quién
org     la organización                  ← dónde
orden   la orden                         ← qué
created_at                               ← cuándo
datos   {numero, programada_para, dia, programacion_semanal,
         semana_inicio, estado_del_plan, linea}
```

**[DISEÑO]** `actor` no tiene valor por defecto en el servicio: una programación
sin persona detrás **no es representable**. Hay prueba.

---

## 12. Tabla de pruebas (§26)

| Prueba | Esperado | Obtenido | Resultado |
|---|---|---|:--:|
| **B1** programación válida | 201 y las dos escrituras coherentes | 201, `dia == localtime(programada_para).date()` | **PASS** |
| **B1b** auditoría con actor | evento con actor, org, día | `EventoTrabajo` tipo `programacion` completo | **PASS** |
| **B2** persistencia independiente | la base lo confirma desde fuera | 1 fila, coherente, por conexión propia | **PASS** |
| **B3** organización incorrecta | rechazo, 0 escrituras | 404, 0 filas | **PASS** |
| **B3b** el servicio también rechaza | error sin pasar por la vista | `ErrorProgramacion`, 0 filas | **PASS** |
| **B3c** `organization_id` del cuerpo | no decide nada | 201, fila en la org de la sesión; 0 en B | **PASS** |
| **B4** OT inexistente | 404 | 404, 0 filas | **PASS** |
| **B5** programación inexistente | 404 | 404, `programada_para` sigue NULL | **PASS** |
| **B6** OT ya programada | rechazo sin sobrescribir | 409 `YA_PROGRAMADA`, fecha original intacta, 1 línea | **PASS** |
| **B6b** solo `programada_para` poblado | también rechaza | `YaProgramada`, 0 líneas | **PASS** |
| **B7** rollback | nada persiste | 0 líneas, `programada_para` NULL, 0 eventos | **PASS** |
| **B7b** rollback desde fuera | la base tampoco lo tiene | 0 filas, NULL | **PASS** |
| **B8** concurrencia | una sola programación | `[201, 409]`, 1 línea, coherente | **PASS** |
| **B9** sin asignación | programada y sin técnico | `programada_para` puesto, 0 asignaciones | **PASS** |
| **B10** no cambia estado | estado, validación, vuelta, `iniciada_en` intactos | los cuatro sin cambio | **PASS** |
| **B10b** solo lo que no arrancó | 400 en los 6 estados restantes | 400 ×6, 0 filas | **PASS** |
| **B11** cross-tenant | A→A 201, A→B 404, B→A 404 | exactamente eso | **PASS** |
| **B12** segunda organización | cada una programa lo suyo | 1 línea por org, sin mezcla | **PASS** |
| plan cerrado | rechazo | 400, 0 filas | **PASS** |
| fecha fuera de la semana | rechazo | 400 `"fuera del plan"` | **PASS** |
| un técnico no programa | 403 | 403, 0 filas | **PASS** |
| sin sesión | rechazo | 403, 0 filas | **PASS** |
| sin actor | no representable | `ErrorProgramacion`, 0 filas | **PASS** |
| **alcance**: ni novedades ni asignaciones | 0 y 0 | 0 novedades, 0 asignaciones, 0 planes publicados | **PASS** |
| **lock desarmado** (control) | B8 **debe fallar** | **FAILED** | **PASS** |

```
29 passed · 0 failed · 0 skipped
```

**No se usó ningún `skipif` para ocultar nada.** Las tres pruebas marcadas
`postgres_only` (B2, B7b, B8) **corrieron de verdad**: el entorno apunta a
PostgreSQL 16, y el conteo lo confirma (29 recolectadas, 29 pasadas, 0 saltadas).

---

## 13. Regresión (§22)

```
pytest operaciones/tests/ campo/tests/ --no-cov

  506 passed, 0 failed, 0 skipped      en 266s
```

| | |
|---|---|
| Base (A-3.4) | **477 passed** |
| M03-B | **+29** |
| **Total** | **506** |

**Ninguna falla nueva.** No hubo nada que clasificar como PREEXISTENTE,
INTRODUCIDA ni AMBIENTAL.

Dos guardas existentes merecían atención y **no se rompieron**:

- **La guarda de rutas de M09-F** fija el inventario de nombres de rutas de
  `operaciones`. `trabajo_programar` vive en `campo`, así que no la toca — y sus
  substrings prohibidos (`ejecutar`, `aplicar`, `despachar`) siguen ausentes.
- **`campo/tests/test_aislamiento_tenant_404.py`** sigue en verde con una ruta más.

---

## 14. Efectos externos (§23)

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP saliente 0 · scheduler autónomo 0
```

Instrumentado en `socket.socket.connect` **antes de importar Django**.

**El cero se leyó después de probar el instrumento:** una sonda deliberada a
`127.0.0.1:9` quedó registrada como `('127.0.0.1', 9)`. Sin esa comprobación, un
contador roto también habría marcado 0.

Alcance real, dicho en vez de disimulado: cubre toda la pila HTTP de Python
(`requests`, `httpx`, `urllib`, `http.client`), que es por donde saldrían los tres
sistemas externos. `psycopg3` va por `libpq` y no aparece.

**No hay programación automática**: ni IA, ni scheduler, ni autonomía. La
operación exige una persona autenticada con rol de gestión, y el servicio rechaza
un `actor` nulo.

---

## 15. Producción (§24)

# SIN CAMBIOS

Medida con `read_only = True`, idéntica a M03-A:

```
ledger 50 · django_migrations 192 · tenant_config v146 · kill switch detenido
OrdenTrabajo 3 · programada_para 0/3 · AsignacionTrabajo 3 · EventoTrabajo 12
evento tipo 'programacion' 0 · ProgramacionSemanal 0 · ProgramacionOrden 0
NovedadOperativa 0 · DisponibilidadTecnico 0 · PropuestaSupervisor 0
operaciones_externas 0
```

Todo se implementó y probó en un contenedor PostgreSQL 16 aislado (`pg-m03b`), con
un runner **sin una sola credencial de producción** — medido, no prometido.

**Entorno temporal eliminado al terminar.**

---

## 16. H-05 (§19)

**H-05 NO quedó validado.** No se tocó: ni la ficha, ni el detector, ni
`supervisor.py`.

Lo único que se verificó es lo que el §19 pide — si **ahora puede construirse el
primer escenario de datos**:

| # | Requisito de H-05 | Antes de M03-B | Después | Quién lo produce |
|:--:|---|:--:|:--:|---|
| 1 | `programada_para` no nulo | imposible salvo al crear | **SÍ** | **M03-B** |
| 2 | `estado_operativo = asignada` | — | **SÍ, garantizado** | M03-B no lo cambia, y solo programa órdenes que ya están así |
| 3 | técnico principal | sí | sí | `despacho.asignar` |
| 4 | ausencia declarada ese día | sí | sí | A-3.3 + un perfil `SUPERVISOR` |

Los requisitos **1 y 2 quedan cubiertos por las pruebas B1 y B10**: tras programar,
la orden tiene fecha **y sigue en `asignada`**.

> **M03-B aporta solo programación.** Faltan asignación y ausencia, y sigue sin
> existir un perfil `SUPERVISOR` en producción (`{ADMIN: 1, USER: 4}`) que pueda
> cargar la ausencia.

---

## 17. Entrega (§30)

### Archivos creados (2)

| Archivo | |
|---|---|
| `django-crm/backend/operaciones/programacion.py` | el servicio |
| `django-crm/backend/operaciones/tests/test_m03b_programacion.py` | 29 pruebas |

### Archivos modificados (3) — **+106 líneas, −0**

| Archivo | Cambio |
|---|---|
| `django-crm/backend/campo/despacho_views.py` | **+1 vista** `ProgramarTrabajoView` (+81) |
| `django-crm/backend/campo/serializers.py` | **+1 serializador** `ProgramarSerializer` (+24) |
| `django-crm/backend/campo/urls.py` | **+1 ruta** (+1) |

**Puramente aditivo: no se borró ni se reescribió una sola línea existente.**

### Migraciones

# 0

**No se creó ningún archivo de migración** porque ninguna hace falta:
`makemigrations --check --dry-run` → *No changes detected*.

### NO modificados — verificado

`operaciones/models.py` · `campo/models.py` · `supervisor.py` · los 10 detectores ·
H-05 · `habilidades.py` · `DisponibilidadTecnico` · `ProgramacionSemanal` ·
`ProgramacionOrden` · `AsignacionTrabajo` · `WorkTypeVersion` · `NovedadOperativa` ·
`common/rls/__init__.py` · políticas RLS · roles · grants · `DBUSER` · B-7 ·
producción.

### Resultado final

# M03-B = VALIDADO

29/29 pruebas propias, 506/506 en regresión, coherencia verificada desde fuera del
ORM, rollback verificado rompiendo la operación, lock verificado desarmándolo,
0 efectos externos, producción sin cambios.

**No se hizo commit.**

---

## 18. Lo que sigue abierto

| # | Pendiente | Tipo |
|:--:|---|---|
| **P-1** | **Reprogramar** — mover una fecha ya puesta, con `NovedadOperativa` (antes/después/motivo) | M03-D |
| P-2 | **Publicar / cerrar** el plan semanal | M03-C |
| P-3 | ¿`correccion_requerida` debe poder programarse? | **decisión de negocio** |
| P-4 | ¿Las líneas pueden cruzar semanas? (la regla derivada de §3) | **decisión de negocio** |
| P-5 | El plan **no dice quién**: `ProgramacionOrden` no tiene FK a técnico | modelo |
| P-6 | Secuencia de jornada (los campos ya existen, la operación no) | M03-E |
| **P-7** | **`campo_*` sin RLS** (7 tablas) — **B-7 no lo resuelve** | **seguridad**, ya reportado en M03-A |
| P-8 | No existe perfil `SUPERVISOR` en producción | operativo |
| P-9 | Capacidad: sigue sin existir un solo dato | bloqueado por D-2/D-3/D-4 |
