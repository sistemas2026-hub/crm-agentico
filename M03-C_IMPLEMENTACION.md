# M03-C = VALIDADO

**Publicación controlada de programación semanal · Informe de implementación**
Fecha: 2026-09-18

---

## Resumen

```
Archivos creados:      1      Archivos modificados:   4
Migraciones:           0      ← "No changes detected"
Modelos nuevos:        0      Tablas nuevas:          0      Roles nuevos: 0
Endpoint:              1      POST /api/operaciones/programacion/<id>/publicar/

Tests M03-C:          30 passed / 0 failed / 0 skipped
Regresión completa:  536 passed / 0 failed / 0 skipped   (506 base + 30)

Transición:      borrador → publicada, y ninguna más
Concurrencia:    select_for_update  -- verificado desarmándolo
Persistencia:    verificada por conexión independiente del ORM
Rollback:        verificado rompiendo la operación en el save
Cross-tenant:    404, sin escritura
Efectos externos: 0    -- con el instrumento probado antes de leer su cero
Producción:      SIN CAMBIOS  (solo lectura, read_only = True)
Commit:          no
```

---

## 1. Objetivo

Permitir que un plan semanal pase de **borrador** a **publicada** de forma
explícita, humana y auditable. Nada más: publicar **no ejecuta** la programación.

---

## 2. Auditoría del modelo (§3) — dos hallazgos que cambiaron el diseño

**No me apoyé en M03-A: releí el modelo.** Confirma lo que M03-A decía, y añade
dos cosas que M03-A no había dicho.

### Hallazgo 1 — `ProgramacionSemanal` **no tiene máquina de transiciones**

```
OrdenTrabajo      → TRANSICIONES_PERMITIDAS + TRANSICIONES_VALIDACION
WorkTypeVersion   → clean() y save() defienden la inmutabilidad
ProgramacionSemanal → tres constantes, y NADA que se mueva entre ellas
```

El ciclo `borrador → publicada → cerrada` existe en el **orden de la tupla
`ESTADOS`** y en los docstrings. En ningún otro sitio: hoy cualquier escritura
puede poner cualquier estado.

> **Consecuencia de diseño:** M03-C **no "respeta" una máquina existente — es el
> primer sitio donde una transición de plan queda restringida.** Y restringe solo
> la que necesita: no se declara una máquina completa porque eso decidiría de paso
> cerrar y reabrir, que son operaciones de otras fases.

### Hallazgo 2 — no hay campo de concurrencia optimista

Ni `revision` (que sí tiene `OrdenTrabajo`) ni versión. `BaseModel` aporta solo
timestamps. **La carrera se resuelve con el lock de la fila, no con un contador.**

**Ninguna contradicción con M03-A.** Campos, constraints y estados coinciden.

---

## 3. Transición

```
borrador  ──publicar──>  publicada          la única implementada
publicada ──publicar──>  409                idempotencia semántica (§12)
cerrada   ──publicar──>  409                §13
cerrada   ──────────>  borrador             NO EXISTE — no se creó reapertura
```

**[MEDIDO]** Hay una prueba que comprueba que el módulo **no expone** `reabrir`,
`cerrar_programacion` ni `despublicar`.

### §12 — las dos idempotencias, que no son la misma

| | Qué protege | Mecanismo |
|---|---|---|
| `manejar_idempotencia` (existente) | un reintento que repetiría una mutación **externa** | `Idempotency-Key` + `MutacionIdempotente` |
| **M03-C** | una segunda llamada que repetiría **una transición de estado** | **el propio estado** |

**No se creó mecanismo nuevo**: si el plan ya está `publicada`, el estado *es* el
registro de que la operación ocurrió. Aquí no hay tercero, hay una máquina de
estados.

Y lo que importa no es el 409: es que **el sello de la primera publicación quede
intacto**. Hay prueba con dos personas distintas (`C4b`): la segunda no pisa a
`publicada_por`.

---

## 4. Validaciones (§5, §6)

### Lo que se comprueba, y de dónde sale cada regla

| Comprobación | Origen |
|---|---|
| el plan pertenece a `request.org` | **[MEDIDO]** patrón del módulo |
| estado = `borrador` | **[MEDIDO]** los tres estados del modelo |
| cada línea vigente es de la misma organización | **[MEDIDO]** `org` es FK en las dos tablas |
| la orden de cada línea es de la misma organización | **[MEDIDO]** idem |
| `linea.dia` dentro de la semana del plan | **[DERIVADA]** — misma regla que M03-B ya declaró como derivada |
| `linea.dia == localtime(orden.programada_para).date()` | **[MEDIDO]** es la coherencia que M03-B garantiza al escribir |

### §14 — el plan vacío: **se publica**, y la evidencia no es mía

No inventé el requisito de "mínimo N órdenes". La evidencia está en el propio
código, en `_programaciones_sin_publicar`:

> *"NO se infiere la publicación de que existan líneas de plan — **un borrador
> también las tiene**, y confundir las dos cosas es exactamente lo que esta señal
> no debe hacer."*

**La semántica existente desacopla publicación de contenido.** Rechazar un plan
vacío habría sido una regla nueva. Hay prueba de que se publica (`C1b`).

### Qué cuenta como "línea vigente"

`planificada` y `confirmada`. `reprogramada` y `cancelada` **no** — misma
definición que `supervisor._programacion_vigente`, y por la misma razón: exigirle
coherencia con la fecha vigente a una línea cancelada sería exigírsela justo a la
que por definición ya no rige. Hay prueba (`C6c`).

### Por qué la comprobación de coherencia hace falta

M03-B escribe la línea y `programada_para` juntos, así que **no puede** producir
una incoherencia. Pero **no es el único escritor posible**: el panel de Django
también crea líneas y no pasa por el servicio. La comprobación existe para eso, y
la prueba fabrica la incoherencia justamente por esa vía.

**Y no corrige nada.** Una línea que no cuadra con su orden es un desacuerdo entre
dos decisiones humanas; elegir cuál gana no es algo que el servidor pueda saber.
Se devuelven **todos** los problemas, no el primero (`C6d`).

---

## 5. Permisos (§8)

**[MEDIDO]** `EsJefeDeOperaciones` → `ROLES_GESTION` = **`{ADMIN, SUPERVISOR,
OPERACIONES}`**. Reutilizado sin modificar. **0 roles nuevos.**

**Son tres roles, y se documenta en vez de reducirse.** Hay una prueba
parametrizada que verifica que los tres pueden publicar.

> **D-6 (¿quién programa?) sigue abierta.** Reducir el permiso a un solo rol la
> habría resuelto por mi cuenta. M03-B usó el mismo conjunto; M03-C no cambia el
> criterio.

---

## 6. Transacción, concurrencia y el lock probado

`@transaction.atomic` + `select_for_update()` sobre el plan **antes** de leer su
estado.

Sin el lock, dos peticiones leen `borrador` a la vez, las dos publican, y **el
plan termina diciendo que lo publicó quien llegó después** — pisando la respuesta
a la única pregunta que `publicada_por` existe para contestar.

### Verificado desarmándolo (§11)

`C8` afirma `[200, 409]` con dos publicaciones simultáneas. Esa aserción pasaría
igual si los hilos corrieran en serie, así que quité el `select_for_update()` y
volví a correr solo esa prueba:

```
sin lock  →  FAILED test_c8_dos_publicaciones_simultaneas_dejan_una_sola
con lock  →  1 passed
```

**Restaurado y confirmado** (2 ocurrencias en el módulo: M03-B y M03-C).

---

## 7. Rollback (§16)

Se rompe la operación **en el `save`**, con estado, actor y fecha ya fijados en
memoria. Si la transacción no fuera real, el plan quedaría publicado a medias.

| Leído desde **conexión independiente** | |
|---|---|
| `estado` | **borrador** |
| `publicada_en` | **NULL** |
| `publicada_por_id` | **NULL** |

Verificado dos veces: por ORM (`C7`) y desde fuera (`C7b`), este último con un
mock que **escribe de verdad y luego falla**, para que el rollback tenga algo que
deshacer.

---

## 8. Cross-tenant (§9)

| Caso | Esperado | Obtenido |
|---|---|---|
| A publica plan de A | permitido | **200** |
| A publica **plan de B** | rechazado | **404**, plan de B intacto |
| B publica plan de B | permitido | **200** |
| servicio llamado con org=A y plan de B | rechazado | `ErrorProgramacion` |

**404 y no 403**: un 403 confirmaría que el plan existe. Y la comprobación está
**también en el servicio**, que no confía en que la vista haya filtrado (`C3b`).

---

## 9. Auditoría (§10)

**Infraestructura existente, tabla nueva ninguna.** El propio modelo es el
registro:

| Dato | Dónde |
|---|---|
| **actor** | `publicada_por` |
| **cuándo** | `publicada_en` |
| **organización** | `org` |
| **programación** | la fila misma |
| **estado nuevo** | `estado` |
| **actor (2ª vía)** | `updated_by`, escrito por `BaseModel.save()` desde `crum` |

**[DISEÑO]** `updated_by` va explícitamente en `update_fields`. `BaseModel.save()`
lo asigna desde el usuario de la petición, pero sin nombrarlo el `UPDATE` lo
dejaría fuera. Es un **segundo registro del actor, independiente de
`publicada_por` y no falsificable por payload**.

### [GAP] Estado anterior

**No queda registrado.** El mecanismo adecuado (`operaciones/auditoria.py`, el
mismo que usa M09-F para guardar antes/después) exige un `entity_type` declarado
en `common.Activity.ENTITY_TYPE_CHOICES`, que **no incluye `ProgramacionSemanal`**.

**Declararlo = modificar `common/models.py` = migración → §27 obliga a detenerse.**
No se hizo. Es el mismo GAP que A-3.3 ya había declarado para disponibilidad.

**Hoy no bloquea:** la transición es de una sola dirección y desde un único estado
de origen, así que *"estado anterior"* solo puede valer `borrador`.

> **[GAP menor]** `publicada_por` es `on_delete=SET_NULL`. Si el perfil se borra,
> el actor se pierde — pero `updated_by` lo conserva.

**No se escribe `EventoTrabajo`**, y es deliberado: esa bitácora es de una *orden*,
y publicar no es un evento de ninguna orden. Hay prueba de que el conteo no se
mueve.

---

## 10. Publicar NO ejecuta (§7)

**[MEDIDO]** Después de publicar, leído desde conexión independiente:

```
OT #9501: asignada, programada_para=2026-10-07 09:00+00, revision=2
OT #9503: asignada, programada_para=2026-10-22 09:00+00, revision=2
asignaciones=0   novedades=0   lineas de plan=2
```

`revision=2` es de **M03-B** (al programar), no de M03-C: publicar no la tocó.

Las pruebas `C10` y `C11` afirman sobre el efecto: estado operativo, estado de
validación, `programada_para`, `revision`, `vuelta`, `iniciada_en`, el día y el
estado de la línea — **los ocho sin cambio**; y 0 asignaciones, 0 novedades,
0 eventos, 0 propuestas, 0 disponibilidades nuevas.

---

## 11. Matriz de resultados (§25)

| Prueba | Esperado | Obtenido | Resultado |
|---|---|---|:--:|
| **C1** publicación válida | 200, estado + actor + fecha | 200, `publicada`, actor y sello correctos | **PASS** |
| **C1b** plan vacío | se publica (§14) | 200, `publicada` | **PASS** |
| **C2** persistencia independiente | la base lo confirma desde fuera | `publicada`, `publicada_en`, `publicada_por`, `updated_by` | **PASS** |
| **C3** cross-tenant | 404, plan ajeno intacto | 404, `borrador`, sin sello | **PASS** |
| **C3b** el servicio también rechaza | error sin pasar por la vista | `ErrorProgramacion` | **PASS** |
| **C3c** cada organización publica lo suyo | actores distintos, cada uno de su org | así fue | **PASS** |
| **C4** ya publicado | 409, sin repetir la transición | 409 `NO_PUBLICABLE` | **PASS** |
| **C4b** no pisa al primer actor | el sello de la 1ª sobrevive | `publicada_por` intacto | **PASS** |
| **C5** plan cerrado | rechazo | 409, sigue `cerrada` | **PASS** |
| **C5b** no hay reapertura | el módulo no la expone | sin `reabrir`/`despublicar` | **PASS** |
| **C6** plan incoherente | 400, no publica **ni corrige** | 400, `borrador`, línea y orden intactas | **PASS** |
| **C6b** orden sin `programada_para` | también bloquea | 400 | **PASS** |
| **C6c** línea cancelada | no bloquea | 200 | **PASS** |
| **C6d** todos los problemas | 2 problemas, no 1 | 2 | **PASS** |
| **C7** rollback | nada persiste | `borrador`, sin sello | **PASS** |
| **C7b** rollback desde fuera | la base tampoco lo tiene | `borrador`, NULL, NULL | **PASS** |
| **C8** concurrencia | una sola transición | `[200, 409]`, un solo sello | **PASS** |
| **C9** técnico no publica | 403 | 403, `borrador` | **PASS** |
| **C9b** sin sesión | rechazo | 403 | **PASS** |
| **C9c** sin actor | no representable | `ErrorProgramacion` | **PASS** |
| **C9d** los tres roles de gestión | los tres pueden | ADMIN, SUPERVISOR, OPERACIONES → 200 | **PASS** |
| **C10** no modifica ninguna orden | 8 campos sin cambio | los 8 | **PASS** |
| **C11** no crea asignaciones ni novedades | conteos sin cambio | asignaciones, novedades y eventos iguales | **PASS** |
| **C11b** no toca propuestas ni disponibilidad | 0 y 0 | 0 y 0 | **PASS** |
| **C12** efectos externos | 0, con el instrumento probado | sonda registrada; 0 externos | **PASS** |
| no toca H-05 ni M09 | 0 propuestas | 0 | **PASS** |
| **apaga `programacion_sin_publicar`** | 1 señal → 0 | 1 → 0 | **PASS** |
| transición en una sola dirección | publicada y cerrada rechazan | ambas | **PASS** |
| **lock desarmado** (control) | C8 **debe fallar** | **FAILED** | **PASS** |

```
30 passed · 0 failed · 0 skipped
```

Las cuatro pruebas `postgres_only` (C2, C7b, C8 y el control) **corrieron**: 30
recolectadas, 30 pasadas, 0 saltadas.

### Tabla de planes — lectura independiente del ORM (§24, §25)

| Plan | Estado antes | Estado después | Actor | Fecha | HTTP | Coherente |
|---|---|---|---|---|:--:|:--:|
| P1 coherente con 1 línea | borrador | **publicada** | jefe.a@m03cev.test | 2026-09-18T… | 200 | **SÍ** |
| P2 vacío | borrador | **publicada** | jefe.a@m03cev.test | 2026-09-18T… | 200 | **SÍ** |
| P3 incoherente | borrador | **borrador** | — | — | 400 | **SÍ** |
| P4 cerrado | cerrada | **cerrada** | — | — | 409 | **SÍ** |
| P5 de otra organización | borrador | **borrador** | — | — | 404 | **SÍ** |

*"Coherente" = el estado cambió exactamente en los casos en que debía cambiar.*

---

## 12. Un fallo propio, y qué era

La primera corrida dio **1 failed**: `test_c10_publicar_no_modifica_ninguna_orden`
decía que `programada_para` había pasado de `None` al valor correcto.

**El fallo era de la prueba, no del código.** Mi ayudante `_linea_coherente`
devolvía el objeto `OrdenTrabajo` **en memoria**, anterior a la escritura:
`programar_orden` opera sobre la fila que bloquea y relee, no sobre esa copia. La
foto del "antes" salía de un objeto desfasado.

Corregido con un `refresh_from_db()` **y un comentario que explica por qué no es
decorativo** — una prueba así mide el desfase del ORM en vez de lo que dice medir.

---

## 13. Regresión (§23)

**Medida, no asumida:**

```
pytest operaciones/tests/ campo/tests/ --no-cov
  536 passed, 0 failed, 0 skipped      en 225s
```

| | |
|---|---|
| Baseline medido (M03-B) | **506** |
| M03-C | **+30** |
| **Total** | **536** |

**Ningún fallo nuevo.** Nada que clasificar como PREEXISTENTE, INTRODUCIDO ni
AMBIENTAL.

### La guarda de M09-F, actualizada con su motivo

`test_no_existe_ninguna_ruta_de_ejecucion` fija el **inventario exacto** de rutas
de `operaciones`, y añadir `programacion-publicar` la hizo fallar. Es la guarda
funcionando: obliga a venir a declarar que la ruta nueva no ejecuta nada.

**Qué hice:** actualizar el conjunto **y escribir en el docstring por qué publicar
no es ejecutar** — no toca ninguna orden, no cambia `programada_para`, no crea
asignaciones, no llama a ningún sistema externo, y hay una prueba que lo afirma
sobre el efecto.

**Qué NO hice:** relajarla. El conjunto sigue siendo exacto y los substrings
prohibidos (`ejecutar`, `aplicar`, `despachar`) siguen comprobándose.

---

## 14. Efectos externos (§17)

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP saliente 0 · scheduler 0
```

Instrumentado en `socket.socket.connect`, y **el cero se leyó después de probar el
instrumento**: la sonda deliberada a `127.0.0.1:9` quedó registrada.

**No hay publicación automática**: ni IA, ni scheduler, ni autonomía. El servicio
rechaza un `actor` nulo, y el endpoint exige sesión con rol de gestión.

---

## 15. H-05 y M09 (§18, §19)

**No se tocó nada**: ni `supervisor.py`, ni los detectores, ni `PropuestaSupervisor`,
ni habilidades, ni autonomía.

### Lo que sí cambió, medido sin tocar M09

**[MEDIDO]** `_programaciones_sin_publicar` emite cuando la semana empezó y el plan
sigue en borrador. **Llevaba existiendo sin que nadie pudiera apagarla: no había
forma de publicar.** Ahora sí:

```
antes de publicar  →  1 señal
después            →  0 señales
```

> Es el primer detector de M09 que pasa de "no se puede satisfacer" a
> "satisfecho por una acción humana". **No se modificó H-05 ni se emitió ninguna
> señal suya.**

**H-05 sigue bloqueado** por asignación + ausencia. M03-C no aporta ninguna de las
dos.

---

## 16. Producción (§20)

# SIN CAMBIOS

Medida con `read_only = True`, idéntica a M03-A y M03-B:

```
ledger 50 · django_migrations 192 · tenant_config v146 · kill switch detenido
OrdenTrabajo 3 · programada_para 0/3 · ProgramacionSemanal 0 · ProgramacionOrden 0
NovedadOperativa 0 · AsignacionTrabajo 3 · EventoTrabajo 12 · evento 'programacion' 0
DisponibilidadTecnico 0 · PropuestaSupervisor 0 · operaciones_externas 0
```

Todo en un contenedor PostgreSQL 16 aislado (`pg-m03c`), con un runner **sin una
sola credencial de producción** — medido. Entorno eliminado al terminar.

---

## 17. Criterio de éxito (§28)

| | Criterio | Prueba |
|:--:|---|---|
| **✔** | publicación válida funciona | C1 |
| **✔** | transición es atómica | C7, C7b |
| **✔** | estado persiste | C2 |
| **✔** | actor persiste | C1, C2 |
| **✔** | timestamp persiste | C1, C2 |
| **✔** | cross-tenant bloqueado | C3, C3b |
| **✔** | actor no autorizado bloqueado | C9, C9b, C9c |
| **✔** | plan publicado no se publica de nuevo | C4, C4b |
| **✔** | plan cerrado no se publica | C5, C5b |
| **✔** | inconsistencias impiden publicación | C6, C6b, C6d |
| **✔** | rollback funciona | C7, C7b |
| **✔** | concurrencia funciona | C8 + control |
| **✔** | publicación NO modifica OT | C10 |
| **✔** | publicación NO crea asignación | C11 |
| **✔** | efectos externos = 0 | C12 |
| **✔** | regresión sin fallos nuevos | 536 / 0 |
| **✔** | producción sin cambios | 15 claves idénticas |

**17 de 17.**

---

## 18. Entrega (§29)

### Archivos creados (1)

| Archivo | |
|---|---|
| `django-crm/backend/operaciones/tests/test_m03c_publicacion.py` | 30 pruebas |

### Archivos modificados (4)

| Archivo | Cambio |
|---|---|
| `django-crm/backend/operaciones/programacion.py` | **+2 excepciones, +3 funciones**: `PlanNoPublicable`, `PlanIncoherente`, `_lineas_vigentes`, `revisar_coherencia`, `publicar_programacion` |
| `django-crm/backend/operaciones/views.py` | **+1 vista** `PublicarProgramacionView` |
| `django-crm/backend/operaciones/urls.py` | **+1 ruta** `programacion-publicar` |
| `django-crm/backend/operaciones/tests/test_m09f_gobernanza.py` | **1 guarda**: inventario de rutas + el motivo |

### Migraciones

# 0

`makemigrations --check --dry-run` → *No changes detected*. **No se creó ningún
archivo de migración.**

### NO modificados — verificado

`operaciones/models.py` · `campo/` entero · `supervisor.py` · los 10 detectores ·
H-05 · `habilidades.py` · `PropuestaSupervisor` · `DisponibilidadTecnico` ·
`AsignacionTrabajo` · `NovedadOperativa` · `common/rls/__init__.py` · políticas RLS ·
roles · `ROLES_GESTION` · grants · `DBUSER` · B-7 · producción.

### Resultado

# M03-C = VALIDADO

30/30 propias, 536/536 en regresión, persistencia y rollback verificados desde
fuera del ORM, lock verificado desarmándolo, 0 efectos externos, producción sin
cambios.

**No se hizo commit. No se implementó M03-D.**

---

## 19. Lo que sigue abierto

| # | Pendiente | Tipo |
|:--:|---|---|
| **P-1** | **Cerrar** un plan (`publicada → cerrada`) — declarado, sin operación | M03-D o posterior |
| **P-2** | **Reprogramar** con `NovedadOperativa` (antes/después/motivo) | M03-D |
| P-3 | `Activity.ENTITY_TYPE_CHOICES` sin `ProgramacionSemanal` → sin estado anterior | **[GAP]**, requiere migración |
| P-4 | ¿Un plan publicado admite líneas nuevas? Hoy **sí** (M03-B lo permite) | **decisión de negocio** |
| P-5 | ¿Las líneas pueden cruzar semanas? (regla derivada, heredada de M03-B) | **decisión de negocio** |
| P-6 | D-6: ¿quién programa y publica? Hoy los tres roles de gestión | **decisión de negocio** |
| P-7 | El plan **no dice quién**: `ProgramacionOrden` sin FK a técnico | modelo |
| **P-8** | **`campo_*` sin RLS** (7 tablas) — **B-7 no lo resuelve** | **seguridad** |
| P-9 | No existe perfil `SUPERVISOR` en producción | operativo |

> **P-4 merece atención antes que las demás:** hoy nada impide agregar una línea a
> un plan ya publicado, porque M03-B acepta planes en `borrador` **y** `publicada`.
> Si publicar debe congelar el plan, eso es una restricción nueva en M03-B — y una
> decisión de negocio, no un arreglo evidente.
