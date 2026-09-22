# M03-E5-C — Validación y cierre de secuenciación

**Fecha:** 2026-09-18

---

## 1. GO / NO-GO

# GO — E5 QUEDA CERRADO

```
Tests de cierre (E5-C):   13 passed / 0 failed / 0 skipped
Suites M03 juntas:       220 passed  (B 29 · C 30 · D3 33 · D3.2 17 · E2 25 · E4 38 · E5 35 · E5-C 13)
Regresión completa:      697 passed / 0 failed / 0 skipped   (684 base + 13)

makemigrations --check:  No changes detected
Producción:              SIN CAMBIOS -- 18 claves idénticas a la foto de M03-D3
Efectos externos:        0
Commit:                  no
```

**[VALIDADO]** Los catorce puntos del criterio de cierre se cumplen. Ninguno
falla.

**Una precisión que el informe hace explícita en vez de dejar pasar:** el §4D
del encargo —*forzar un fallo en la idempotencia y verificar 0 cambios
parciales*— **no se cumple como estaba enunciado**, y la medición explica por
qué (§5). No es un defecto de E5, y no impide el cierre; es una frontera del
mecanismo de idempotencia que existía desde antes y que **ahora queda
documentada y fijada por una prueba**.

---

## 2. Matriz de validación

| # | Punto del criterio de cierre | Evidencia | |
|:--:|---|---|:--:|
| 1 | contrato E4/E5 consistente | `test_b1_e4_y_e5...` (sin_cambios) + `test_1_6...` (aplicado) | **OK** |
| 2 | no-op consistente | E4 `test_4`, `4b`, `4c` · E5 `test_8`, `16b` | **OK** |
| 3 | replay consistente | `test_b1_B` · E5 `test_21_22` · E5-C `test_7_5`, `7_6` | **OK** |
| 4 | concurrencia validada | E5 `test_17`, `test_18` *(verificada desarmando el lock)* | **OK** |
| 5 | atomicidad validada | E5 `test_19`, `20`, `20b` · E5-C `test_4a` | **OK** |
| 6 | rollback validado | idem, leído desde **conexión independiente** | **OK** |
| 7 | idempotencia validada | E5-C `test_7_5`, `7_6` + E5 `test_21_22` | **OK** |
| 8 | auditoría validada | E5 `test_29_30`, `31`, `32` | **OK** |
| 9 | multi-tenant validado | E5-C `test_11` **verificado en los datos** | **OK** |
| 10 | permisos validados | E5-C `test_12` | **OK** |
| 11 | 0 efectos externos | E5-C `test_17` + spy en E4/E5 | **OK** |
| 12 | regresión sin fallos nuevos | **697 / 0 / 0** | **OK** |
| 13 | `makemigrations --check` limpio | *No changes detected* | **OK** |
| 14 | producción sin cambios | 18 claves idénticas | **OK** |

---

## 3. Pruebas ejecutadas

**[IMPLEMENTADO]** E5-C **no agrega funcionalidad**: agrega **13 pruebas** que
cubren lo que las suites previas no llegaban a afirmar. Todo lo demás se ejecutó
tal cual estaba.

| § | Hueco cubierto | Prueba |
|---|---|---|
| **6** | **el orden REAL de los locks**, medido sobre el SQL ejecutado | `test_6_el_lock_de_lineas_va_antes_que_el_del_plan` |
| **4A** | rollback por fallo de **validación** | `test_4a_rollback_por_fallo_de_validacion` |
| **4D** | la **frontera** de la idempotencia | `test_4d_la_frontera_...` |
| **7.5** | otro cuerpo con otra clave = operación nueva | `test_7_5...` |
| **7.6** | misma clave con otro cuerpo = protegida | `test_7_6...` |
| **1.6** | E4 y E5 coinciden también en `"aplicado"` | `test_1_6...` |
| **3** | duplicados `A=1, B=1, C=2` | `test_3...` |
| **10** | la OT intacta, **desde conexión independiente** | `test_10...` |
| **11** | multi-tenant **verificado en los datos** | `test_11...` |
| **12** | permisos: nada se creó ni amplió | `test_12...` |
| **17** | **deriva de arquitectura** | `test_17`, `test_17b` |
| **18** | **G-3 medido**, no corregido | `test_18_g3...` |

---

## 4. Concurrencia real

**[VALIDADO]** Dos procesos reales contra PostgreSQL, en ambos casos del
encargo, y el estado final leído **desde conexión independiente**:

### Caso A — A no sobrescribe a B *(E5 `test_17`)*

```
A lee la jornada (1, 2)
B cambia la línea b: 2 → 7      (vía individual, HTTP real)
A aplica la fotografía anterior  →  409 JORNADA_CAMBIO
```

| Desde fuera del ORM | |
|---|---|
| línea `a` | **1** — A no movió la suya |
| línea `b` | **7** — **B sobrevive** |
| eventos parciales de A | **0** |

### Caso B — dos secuenciaciones simultáneas *(E5 `test_18`)*

```
codigos = [200, 409]
estado persistido = (3,4) ó (5,6)   -- nunca una mezcla
lotes de eventos = 1
```

**[VALIDADO]** Verificado **desarmando el lock**:

```
sin select_for_update  →  FAILED   codigos == [200, 200]
con locks              →  passed   [200, 409]
```

---

## 5. Rollback y la frontera del §4D

**[VALIDADO]** Los cuatro puntos de fallo forzado, con lo que se midió en cada
uno:

| | Fallo forzado en | Resultado | Prueba |
|---|---|---|---|
| **A** | **validación** (tras lock y relectura) | **0 cambios, 0 eventos, 0 novedades** | E5-C `test_4a` |
| **B** | **actualización de una línea** (la 2ª de 2) | **0 cambios** — ni la primera, que ya se había escrito | E5 `test_19` |
| **C** | **escritura de `EventoTrabajo`** | **0 cambios**, verificado desde conexión independiente | E5 `test_20`, `20b` |
| **D** | **idempotencia** | **ver abajo — no es lo que la pregunta suponía** | E5-C `test_4d` |

### [MEDIDO] Qué pasa realmente con un fallo en la idempotencia

`manejar_idempotencia` trabaja en **tres transacciones separadas**
(`campo/services/idempotencia.py`):

```
1. crear la MutacionIdempotente en PROCESANDO     (transaction.atomic propio)
2. ejecutar la vista                              (su propio atomic)
3. marcarla COMPLETADA
```

Medido, los dos sub-casos se comportan distinto:

| Momento del fallo | Qué queda |
|---|---|
| **antes** del paso 2 | **nada**: la operación no llegó a ejecutarse |
| **después** del paso 2 | **el cambio SÍ queda**, con su evento — y la mutación se queda en `PROCESANDO` |

> **Un reintento con esa misma clave recibiría `409 OPERACION_EN_CURSO`
> indefinidamente.**

**[RIESGO] Esto NO lo introdujo E5.** Es una propiedad del mecanismo existente,
usado por **M03-B, M03-D3, M03-E4 y los endpoints de campo** desde antes de que
existiera la secuenciación. §21-22 del encargo obligan a reutilizarlo y a no
crear otro.

**[DISEÑO] Por eso la prueba no afirma algo falso: mide la frontera y la fija.**
Si mañana alguien mete la contabilidad de idempotencia dentro de la transacción
de negocio, `test_4d` lo detectará.

**[PENDIENTE]** Si el negocio quiere que una mutación huérfana en `PROCESANDO`
se pueda recuperar, es trabajo sobre `manejar_idempotencia` — **fuera de M03**.

---

## 6. Idempotencia

**[VALIDADO]** Los seis puntos del §7:

| # | | Resultado |
|:--:|---|---|
| 1 | primera petición → aplicada | `resultado: "aplicado"` |
| 2 | misma petición exacta → replay | `Idempotent-Replay: true` |
| 3 | el replay no genera un segundo evento | **1 evento**, no 2 |
| 4 | el replay no genera una segunda novedad | **1 novedad** por lote |
| 5 | **otro cuerpo con otra clave → operación nueva** | **lote distinto**, 2 eventos |
| 6 | **misma clave con otro cuerpo → protegida** | **409 `IDEMPOTENCY_KEY_REUSED`**, la 2ª no se aplica |

**[MEDIDO]** El replay devuelve **`"aplicado"`**, no `"sin_cambios"`: lo que se
repite es la **petición**, no el estado. Esa diferencia es la que separa B de A.

---

## 7. Auditoría

**[VALIDADO]** Evento por evento se comprobó: `orden_id`, `lote`, `actor`
(`profile_id`), `created_at`, `anterior`, `nuevo`, `anterior_sin_secuenciar`,
`nuevo_sin_secuenciar`, `causa`/`motivo`/`novedad` cuando corresponde, y
`lote_tamano` / `lote_cambiadas` / `lote_sin_cambio`.

| | |
|---|---|
| líneas modificadas | **un evento cada una** |
| líneas sin cambio | **ningún evento** |
| agrupación por lote | **todos los de una operación comparten `lote`** |
| evento de conjunto | **no existe** — `campo_evento_trabajo.orden_id` es `NOT NULL` |

**[MEDIDO]** El caso del encargo se reconstruye línea a línea:

```
A: 1 → 3      B: 2 → 1      C: 3 → 2
```

---

## 8. Multi-tenant

**[VALIDADO]** Verificado **en los datos**, no solo por código HTTP
(E5-C `test_11`):

| Intento | HTTP | Datos |
|---|:--:|---|
| A secuencia el plan de B | **404** | línea de B **sin tocar** |
| A cuela una línea de B en su jornada | **400** | **ninguna de las dos** se movió |
| B secuencia lo suyo | **200** | aplicado |

Leído desde conexión independiente: **0 eventos de secuencia** tras los dos
intentos fallidos.

---

## 9. Permisos

**[VALIDADO]** E5-C `test_12`:

```
ROLES_GESTION == {"ADMIN", "SUPERVISOR", "OPERACIONES"}
common.utils.ROLES == {"ADMIN", "SUPERVISOR", "OPERACIONES", "USER"}   -- no creció
JornadaView, SecuenciaLineaView, SecuenciarJornadaView
    → permission_classes == [EsJefeDeOperaciones]
```

**0 roles nuevos. 0 permisos ampliados.**

---

## 10. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

**[VALIDADO]** Dos comprobaciones independientes:

1. **Spy sobre `socket.connect`** en E4, E5 y B-1, con el instrumento **probado
   antes de leer su cero** (sonda deliberada a `127.0.0.1:9`).
2. **Lectura del fuente** (E5-C `test_17`): ni `wisphub`, ni `smartolt`, ni
   `whatsapp`, ni `requests.`, ni `httpx.`, ni `urllib.request` aparecen en
   `operaciones/programacion.py` ni en `operaciones/views.py`.

---

## 11. Regresión

```
Suite completa del backend ......... 697 passed / 0 failed / 0 skipped

Suites de M03 juntas ............... 220 passed
  B 29 · C 30 · D3 33 · D3.2 17 · E2 25 · E4 38 · E5 35 · E5-C 13
```

| Hito | Total |
|---|---|
| M03-E5-B | 676 |
| M03-B1 | 684 |
| **M03-E5-C** | **697** |

**[VALIDADO] Ninguna falla.** Nada que clasificar como *introducida*,
*preexistente*, *infraestructura* ni *entorno*.

**[MEDIDO]** Los tres fallos que aparecieron **al escribir** las pruebas de
cierre eran míos, y los tres están corregidos y explicados:

| Fallo | Qué era |
|---|---|
| `test_3` leía `[]` | la prueba no estaba marcada `transaction=True`: sin commit, la conexión independiente no ve nada |
| `test_12` | `Profile.ROLES` no existe — el catálogo vive en `common.utils.ROLES` |
| `test_4d` | **la prueba afirmaba algo falso**; reescrita para medir la frontera real (§5) |

---

## 12. `makemigrations --check`

```
No changes detected
```

# 0 migraciones · 0 modelos · 0 constraints

---

## 13. Producción antes / después

# SIN CAMBIOS

**[MEDIDO]** Solo `SELECT`, `read_only = True`. **18 claves, DIFERENCIAS:
NINGUNA** respecto de la foto de M03-D3:

```
django_migrations 192 · ledger 50 · tablas public 135 · índices public 829
ProgramacionSemanal 0 · ProgramacionOrden 0 · OrdenTrabajo 3
EventoTrabajo 12 · NovedadOperativa 0 · AsignacionTrabajo 3
PropuestaSupervisor 0 · acciones_propuestas 40 · operaciones_externas 0
kill switch detenido · tenant_config v146
```

---

## 14. Deriva de arquitectura

**[VALIDADO]** E5-C `test_17` lo afirma **leyendo el fuente**, no la intención:

| ¿Apareció…? | |
|---|:--:|
| nuevo sistema de tareas (`celery`, `shared_task`, `apply_async`) | **NO** |
| nuevo sistema de auditoría (`Activity`) | **NO** — sigue `EventoTrabajo` + `NovedadOperativa` |
| nuevo sistema de idempotencia | **NO** — usa `manejar_idempotencia` y **no** reimplementa `MutacionIdempotente` |
| nuevo sistema de permisos | **NO** — `EsJefeDeOperaciones` |
| nuevo sistema de programación | **NO** |
| **nueva entidad para secuencias** | **NO** — los 6 modelos de `operaciones` son los mismos |
| nueva lógica de SLA | **NO** |
| llamadas directas a WispHub / SmartOLT / WhatsApp | **NO** |

---

## 15. G-3 — `secuencia_leida`

# [DECISIÓN PENDIENTE] — no se resolvió

**[MEDIDO]** Dónde es opcional:

```python
# operaciones/serializers.py :: LineaSecuenciaSerializer
secuencia_leida = serializers.IntegerField(
    required=False, allow_null=True, default=None, min_value=0, max_value=32767)
```

**[MEDIDO]** Qué protección pierde la línea que no lo envía — **fijado por
`test_18_g3...`**:

```
línea en 1
alguien la cambia a 7 por la vía individual
un cliente que NO manda 'secuencia_leida' aplica 3   →  200 "aplicado"
resultado: el cambio a 7 se perdió, SIN AVISO
```

Y con el campo presente y desfasado, **el mismo caso sí da 409 `JORNADA_CAMBIO`**.

**[MEDIDO]** ¿Existe hoy una ruta para omitirlo? **Sí**: cualquier cliente que no
lo envíe. El servicio comprueba `if leida is not None`.

**[DISEÑO] Impacto de hacerlo obligatorio:**

| | |
|---|---|
| a favor | cierra el único hueco de "el último gana" que queda |
| en contra | **es un cambio de contrato**: un cliente que hoy funciona empezaría a recibir 400 |
| coste | una línea en el serializador (`required=True`) + adaptar pruebas |

**[RIESGO] Deuda de contrato, declarada:** mientras `secuencia_leida` siga siendo
opcional, **la garantía "no se sobrescriben cambios concurrentes" es
condicional: depende de que el cliente coopere.** Queda escrito aquí y fijado por
una prueba, para que no se descubra en producción.

---

## 16. Gaps restantes

| # | Gap | Tipo | ¿Impide cerrar E5? |
|:--:|---|---|:--:|
| **G-3** | `secuencia_leida` opcional → garantía condicional | **[DECISIÓN PENDIENTE]** | **no** — medido y documentado |
| **I-1** | fallo en la contabilidad de idempotencia deja la mutación en `PROCESANDO` | [RIESGO] **preexistente**, fuera de M03 | **no** |
| G-6 | duplicación E4 ↔ E5 ("capturar, comparar, escribir, auditar") | [PENDIENTE] alcance | no |
| R-1 | `_programacion_vigente` de M09 sin desempate (no se puede tocar sin migración) | [RIESGO] | no |
| R-2 | **`campo_*` sin RLS** (7 tablas) — **B-7 no lo resuelve** | [RIESGO] **seguridad** | no |
| E-6 | `prioridad` expuesta y **sin ordenar**, con su regla en el `help_text` | [PENDIENTE] | no |
| E-7 | `zona` texto libre **sin catálogo** | [PENDIENTE] | no |
| P-5 | **no existe ningún perfil `SUPERVISOR` en producción** (`{ADMIN: 1, USER: 4}`) | **operativo** | no |
| P-7 | **0 planes y 0 líneas en producción**; las 3 OT reales clasifican como contingencia | **operativo** | no |

---

## 17. Archivos modificados durante E5 / B-1 / E5-C

### Código (4)

| Archivo | E5-B | B-1 | E5-C |
|---|:--:|:--:|:--:|
| `operaciones/programacion.py` | +2 excepciones, +`secuenciar_jornada`, +`_semana_de`, corrección de `resumen_de_jornada` | −`SecuenciaSinCambio`, no-op → `return` | — |
| `operaciones/serializers.py` | +2 serializadores | — | — |
| `operaciones/views.py` | +1 vista | −1 manejador, +rama no-op, +`resultado` | — |
| `operaciones/urls.py` | +1 ruta | — | — |

### Pruebas (4)

| Archivo | |
|---|---|
| `operaciones/tests/test_m03e5_jornada.py` | **creado** en E5-B — 35 pruebas |
| `operaciones/tests/test_m03e5c_cierre.py` | **creado** en E5-C — 13 pruebas |
| `operaciones/tests/test_m03e4_secuencia.py` | B-1: 2 adaptadas + 6 nuevas |
| `operaciones/tests/test_m03e2_jornada.py` | E5-B: 3 aserciones alineadas con E-2 |
| `operaciones/tests/test_m09f_gobernanza.py` | E5-B: guarda de rutas + motivo |

---

## 18-19. Confirmaciones

# 18 · NO SE REQUIEREN MIGRACIONES

**[MEDIDO]** `makemigrations --check` → *No changes detected*. Toda la
secuenciación —E4, E5-B, B-1 y E5-C— se construyó **sobre el esquema existente**:
0 modelos, 0 campos, 0 constraints, 0 índices.

# 19 · NO SE REQUIERE INTERVENCIÓN EN PRODUCCIÓN

**[MEDIDO]** Producción no se tocó en ninguna de las cuatro fases —solo `SELECT`,
`read_only = True`— y no hay nada que aplicar: ni migración, ni backfill, ni
cambio de configuración, ni de permisos.

**[RIESGO]** Y no hay nada que **verificar** en producción tampoco, porque
**sigue habiendo 0 planes y 0 líneas**. Toda la secuenciación está probada sobre
datos de un entorno aislado; **la primera jornada real será la primera vez que
este código vea un dato de verdad.**

---

## 20. Estado de E5

# E5 QUEDA CERRADO

**[VALIDADO]** Los catorce puntos del criterio se cumplen. Lo que se implementó
en E4, E5-B y B-1 quedó:

| | |
|---|---|
| **coherente** | E4 y E5 responden igual al mismo hecho, en `sin_cambios` y en `aplicado` |
| **atómico** | fallo en validación, en escritura o en auditoría → **0 cambios parciales** |
| **auditable** | un evento por línea modificada, agrupables por lote, ninguno para las que no cambiaron |
| **seguro** | multi-tenant verificado en los datos; permisos existentes; 0 roles nuevos |
| **sin deriva** | ningún sistema paralelo de tareas, auditoría, idempotencia, permisos ni programación |

**Las dos salvedades, dichas en vez de omitidas:**

1. **G-3** — la garantía de concurrencia es **condicional**: depende de que el
   cliente envíe `secuencia_leida`. **Medida, fijada por una prueba, y pendiente
   de decisión.**
2. **La frontera del §4D** — la atomicidad cubre la **operación de negocio**, no
   la contabilidad de la idempotencia. **Preexistente, fuera de M03, y ahora
   documentada.**

Ninguna de las dos impide cerrar E5: la primera es una decisión de contrato, la
segunda una propiedad de un mecanismo que E5 tenía orden de reutilizar sin
modificar.

---

```
código nuevo ... 0 (E5-C solo valida)     pruebas nuevas ... 13
migraciones .... 0     modelos .... 0     roles .... 0     constraints .... 0
M09 ............ sin tocar     revisar_coherencia ... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no        M03-F ......... no iniciado
```
