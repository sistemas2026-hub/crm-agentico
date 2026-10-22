# M03-B1 — Alineación del contrato de secuenciación E4/E5

**Fecha:** 2026-09-18
**Estado:** **[VALIDADO]**

---

## Resumen

```
Archivos modificados:  2 de código · 1 de pruebas
Archivos creados:      0
Migraciones:           0    Modelos: 0    Roles: 0    Constraints: 0

Tests M03-E4:         38 passed  (30 previas + 8 de B-1)
Suites M03 juntas:   207 passed  (B 29 · C 30 · D3 33 · D3.2 17 · E2 25 · E4 38 · E5 35)
Regresión completa:  684 passed / 0 failed / 0 skipped   (676 base + 8)

Producción:   SIN CAMBIOS -- 18 claves idénticas a la foto de M03-D3
Commit:       no
```

---

## 1-2. Archivos

### Modificados — código (2)

| Archivo | Cambio |
|---|---|
| `operaciones/programacion.py` | **−1 excepción** (`SecuenciaSinCambio`, eliminada); el no-op de `actualizar_secuencia` pasa de `raise` a `return fresca, None, None` |
| `operaciones/views.py` | **−1 manejador** de `SecuenciaSinCambio`; **+1 rama** de no-op; **+`resultado`** en las dos respuestas |

### Modificados — pruebas (1)

| Archivo | Cambio |
|---|---|
| `operaciones/tests/test_m03e4_secuencia.py` | **2 pruebas adaptadas** (409 → 200) · **+6 nuevas** (4c, 4d, 4e y las cuatro de B-1) |

**[MEDIDO]** **Ningún archivo creado.** `SecuenciaSinCambio` se eliminó en vez de
dejarla muerta: su docstring decía *"se rechaza porque es la única salida
reversible"*, que **contradice** la decisión aprobada.

---

## 3. Comportamiento anterior de E4

```python
anterior = fresca.secuencia
if anterior == secuencia:
    raise SecuenciaSinCambio(
        f"La linea ya tiene secuencia {anterior}. No hay nada que cambiar.")
```

→ **409** `SECUENCIA_SIN_CAMBIO`, con `"pendiente":
"DECISION_EMPRESARIAL_SecuenciaSinCambio"` — declarado **provisional** desde M03-E4.

---

## 4. Comportamiento nuevo de E4

```python
anterior = fresca.secuencia
if anterior == secuencia:
    #  NO-OP -- DECISION B-1, unifica E4 con E5
    return fresca, None, None
```

```jsonc
HTTP 200
{
  "linea": { ... },
  "resultado": "sin_cambios",
  "traza": null,
  "aviso": "La línea ya tenía ese orden propuesto. No se modificó nada y no se
            registró ningún evento."
}
```

**[IMPLEMENTADO]** Lo que **no** se escribe, verificado:

| | |
|---|---|
| `EventoTrabajo` | **0** |
| `NovedadOperativa` | **0** |
| la fila | **ni se toca** — `updated_at` idéntico |
| la causa | **ni se valida** — un no-op no tiene nada que justificar |

**[DISEÑO]** El `return` sale **antes** de `_validar_causa`, igual que en E5. Por
eso un no-op sobre un **plan publicado** tampoco exige motivo (prueba `4c`) —
misma regla que `test_16b` de E5.

---

## 5. Confirmación de alineación

**[VALIDADO]** Probado de frente, con el **mismo hecho por las dos rutas** en una
sola prueba (`test_b1_e4_y_e5_responden_igual_al_mismo_hecho`):

| | `POST .../linea/<id>/secuencia/` | `POST .../jornada/secuenciar/` |
|---|---|---|
| HTTP | **200** | **200** |
| `resultado` | **`"sin_cambios"`** | **`"sin_cambios"`** |
| `EventoTrabajo` | **0** | **0** |
| `NovedadOperativa` | **0** | **0** |

**[DISEÑO]** Se añadió la clave **`resultado`** también al camino normal de E4
(`"aplicado"`), para que las dos rutas **hablen el mismo idioma** y no solo
coincidan en el código HTTP.

---

## 6. Las tres situaciones que se parecen y no son lo mismo

**[VALIDADO]** El encargo pide demostrar que el sistema las distingue. Hay **una
prueba por cada una**, para que ninguna tape a otra:

| | Situación | Respuesta | Qué la distingue |
|---|---|---|---|
| **A** | **NO-OP** — el estado pedido ya rige | **200** `sin_cambios` | **sin** cabecera `Idempotent-Replay`; **0 eventos** |
| **B** | **REPLAY** — la misma petición ya se ejecutó | **200** + **`Idempotent-Replay: true`** | devuelve **la respuesta de la primera**, con `resultado: "aplicado"` — porque aquella **sí** cambió algo. **1 evento**, no dos |
| **C** | **CONCURRENCIA** — otro cambió la línea en medio | comportamiento **sin tocar** | los eventos **encadenan**: el `anterior` de cada uno es el `nuevo` del previo, y el último coincide con la fila |

**[MEDIDO] Por qué B no es A:** en el replay la operación original **modificó**
la línea; lo que se repite es la *petición*, no el estado. Por eso devuelve
`"aplicado"` y no `"sin_cambios"` — y eso es exactamente lo que la prueba afirma.

**[IMPLEMENTADO]** **B-1 libera el 409 del no-op y no toca nada más.** El 409
queda reservado para conflictos reales: `JornadaCambio` (E5),
`JornadaIncompleta`, `YaProgramada`, `YaEnEsaFecha`, `RequiereContingencia`,
`NoEstaProgramada` y `PlanNoPublicable` **siguen igual**.

---

## 7. Pruebas

| # | Exigido por el encargo | Prueba | |
|:--:|---|---|:--:|
| 1 | E4: `1 → 1` → 200 sin cambios | `test_4` *(adaptada)* | **PASS** |
| 2 | E4: `0 → 0` → 200 sin cambios | `test_4b` *(adaptada)* | **PASS** |
| 3 | E4: `2 → 2` → sin evento | `test_4`, `test_b1_A` | **PASS** |
| 4 | E4: `1 → 2` sigue normal, genera evento | `test_4d` | **PASS** |
| 5 | E4: `2 → 0` sigue normal, semántica SIN SECUENCIAR | `test_4e` | **PASS** |
| 6 | E5: lote sin cambios sigue 200, 0 eventos | `test_8` de E5 | **PASS** |
| 7 | E5: lote parcial sigue funcionando | `test_9` de E5 | **PASS** |
| 8 | E5: replay conserva su comportamiento | `test_21_22` de E5 | **PASS** |
| 9 | E4: conflicto conserva su comportamiento | `test_b1_C` | **PASS** |
| 10 | E5: conflicto conserva su comportamiento | `test_17`, `test_18` de E5 | **PASS** |
| 11 | ningún no-op genera evento, novedad, cambio en OT ni efectos externos | `test_4`, `test_4c`, `test_b1_un_noop_no_produce_efectos_externos` | **PASS** |
| 12 | el 0 sigue correcto en `resumen_de_jornada` y en E4/E5 | `test_4b`, `test_4e`, `test_6` de E5, E2 completo | **PASS** |
| — | **E4 y E5 responden igual al mismo hecho** | `test_b1_e4_y_e5...` | **PASS** |
| — | no-op **no** es replay | `test_b1_A` | **PASS** |
| — | replay **no** es no-op | `test_b1_B` | **PASS** |
| — | no-op en plan publicado no exige motivo | `test_4c` | **PASS** |

```
38 passed · 0 failed · 0 skipped     (30 previas + 8 de B-1)
```

---

## 8. Regresión

```
Suites de M03 juntas .................. 207 passed
  M03-B 29 · M03-C 30 · M03-D3 33 · M03-D3.2 17 · M03-E2 25 · M03-E4 38 · M03-E5 35

Suite completa del backend ............ 684 passed / 0 failed / 0 skipped
```

| | |
|---|---|
| Baseline (M03-E5-B) | **676** |
| M03-B1 | **+8** |
| **Total** | **684** |

**[VALIDADO]** Ninguna falla. **Las suites de E5, E2, D3, D3.2, C y B no
cambiaron ni una línea**: B-1 tocó solo el camino que E4 tenía distinto.

---

## 9. `makemigrations --check`

```
No changes detected
```

# 0 migraciones · 0 modelos · 0 constraints

---

## 10. Producción

# SIN CAMBIOS

**[MEDIDO]** Solo `SELECT`, `read_only = True`. **18 claves comparadas contra la
foto de M03-D3 → DIFERENCIAS: NINGUNA**:

```
django_migrations 192 · ledger 50 · tablas public 135 · índices public 829
OrdenTrabajo 3 · programada_para 0/3 · ProgramacionSemanal 0 · ProgramacionOrden 0
NovedadOperativa 0 · EventoTrabajo 12 · AsignacionTrabajo 3
PropuestaSupervisor 0 · acciones_propuestas 40 · operaciones_externas 0
kill switch detenido · tenant_config v146
```

Todo en un contenedor PostgreSQL 16 aislado (`pg-b1`), con un runner sin una sola
credencial de producción. Entorno eliminado al terminar.

---

## 11. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

**[VALIDADO]** Instrumentado en `socket.socket.connect` **alrededor de un no-op**,
que es el camino nuevo. Y el cero se leyó **después de probar que el instrumento
dispara** con una sonda deliberada.

---

## 12. Gaps restantes

| # | Gap | Tipo | ¿Bloquea? |
|:--:|---|---|:--:|
| **B-1** | **CERRADO** en este paso | — | — |
| G-3 | **`secuencia_leida` es opcional en E5**: si el cliente no la envía, esa línea **no se comprueba** contra cambios concurrentes | [RIESGO] documentado | no |
| G-6 | **Duplicación E4 ↔ E5**: "capturar, comparar, escribir, auditar" sigue dos veces. Extraer el helper obligaría a repetir las 38 pruebas de E4 | [PENDIENTE] alcance | no |
| R-1 | `_programacion_vigente` de M09 sigue sin desempate (no se puede tocar sin migración) | [RIESGO] | no |
| R-2 | **`campo_*` sin RLS** (7 tablas) — **B-7 no lo resuelve** | [RIESGO] seguridad | no |
| E-6 | `prioridad` sigue expuesta y **sin ordenar**, con su regla escrita en el `help_text` | [PENDIENTE] | no |
| E-7 | `zona` sigue siendo texto libre sin catálogo | [PENDIENTE] | no |
| P-5 | **No existe ningún perfil `SUPERVISOR` en producción** (`{ADMIN: 1, USER: 4}`) | **operativo** | no |

### Lo que la alineación deja a la vista

**[RIESGO]** Con B-1 cerrado, **el 409 del módulo queda reservado a conflictos
reales** — y eso hace más visible el gap **G-3**: en E5, una línea enviada **sin**
`secuencia_leida` no participa de la comprobación de concurrencia. El campo es
opcional para no romper un cliente que no lo mande, pero **una petición sin él
vuelve a la conducta "el último gana"** para esa línea.

**[PENDIENTE]** Hacerlo obligatorio sería un cambio de contrato: **decisión**, no
corrección.

---

```
código ......... 2 archivos modificados     pruebas ... 1 archivo modificado
migraciones .... 0     modelos .... 0     roles .... 0     constraints .... 0
M09 ............ sin tocar     revisar_coherencia ... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
