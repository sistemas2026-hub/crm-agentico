# M03-E5-B — Secuenciación atómica de jornada

**Fecha:** 2026-09-18
**Estado:** **[VALIDADO]**

---

## Resumen

```
Archivos creados:      1        Archivos modificados:   6
Migraciones:           0        ← "No changes detected"
Modelos:               0        Roles: 0        Constraints: 0

Tests M03-E5-B:       35 passed / 0 failed / 0 skipped
Suites M03 juntas:   199 passed  (B 29 · C 30 · D3 33 · D3.2 17 · E2 25 · E4 30 · E5 35)
Regresión completa:  676 passed / 0 failed / 0 skipped   (641 base + 35)

Locks:        líneas por id ascendente → plan   -- verificado desarmándolos
Producción:   SIN CAMBIOS -- 18 claves idénticas a la foto de M03-D3
Commit:       no
```

---

## 1-2. Archivos

### Creado (1)

| Archivo | |
|---|---|
| `operaciones/tests/test_m03e5_jornada.py` | **35 pruebas** |

### Modificados (6)

| Archivo | Cambio |
|---|---|
| `operaciones/programacion.py` | **+2 excepciones** (`JornadaCambio`, `JornadaIncompleta`), **+1 servicio** `secuenciar_jornada`, **+1 helper** `_semana_de`; **corrección** de `resumen_de_jornada` (§ más abajo) |
| `operaciones/serializers.py` | **+2**: `LineaSecuenciaSerializer`, `SecuenciarJornadaSerializer` |
| `operaciones/views.py` | **+1 vista** `SecuenciarJornadaView` |
| `operaciones/urls.py` | **+1 ruta** |
| `operaciones/tests/test_m09f_gobernanza.py` | guarda de rutas + el motivo por el que no es ruta de ejecución |
| `operaciones/tests/test_m03e2_jornada.py` | **3 aserciones** alineadas con la decisión E-2 (§ más abajo) |

---

## Una contradicción encontrada al implementar, y corregida

**[MEDIDO]** `resumen_de_jornada` —escrito en M03-E2, **antes** de que se
aprobara E-2— contaba **cualquier** secuencia repetida como empate, **incluido el
0**. La regla aprobada dice lo contrario:

> *"secuencia=0 significa SIN SECUENCIAR. Varias órdenes con secuencia=0 **NO
> constituyen empate**."* (reglas 3 y 8)

La destapó la prueba 6 de E5 (una jornada entera puesta en 0): el resumen
informaba **3 líneas en empate** donde la regla dice que no hay ninguno. Y el
propio código ya era inconsistente consigo mismo: `_empate_de` (E4) **sí** trataba
bien el 0.

**[IMPLEMENTADO]** Corregido en `resumen_de_jornada`:

```python
grupos = {s: n for s, n in conteo.items() if n > 1 and s > 0}
```

**[IMPLEMENTADO]** Y `orden_arbitrario` conserva lo que de verdad significa —*"lo
que ves no significa nada"*— ahora por dos vías: el día entero sin secuenciar, **o**
todas sus líneas empatadas.

**[MEDIDO]** Eso obligó a alinear **3 aserciones de la suite de M03-E2**, que
codificaban la semántica anterior. Las tres llevan el comentario de por qué
cambiaron. **No es una regla nueva: es el código poniéndose al día con una
decisión ya aprobada.**

---

## 3. Endpoint

```
POST /api/operaciones/programacion/jornada/secuenciar/
```

**[DISEÑO]** Bajo `/api/operaciones/programacion/`, el patrón existente. No se
inventó estructura paralela.

**[MEDIDO]** La guarda de rutas de M09-F se actualizó con el motivo: es la misma
escritura que `linea-secuencia` repetida N veces con un lote común — no ejecuta
nada externo, no despacha, no reasigna.

---

## 4. Contrato

### Petición

```jsonc
{
  "plan": "<uuid>",
  "dia": "2026-10-07",
  "lineas": [
    {"linea": "<uuid>", "secuencia_leida": 1, "secuencia": 3},
    {"linea": "<uuid>", "secuencia_leida": 2, "secuencia": 1},
    {"linea": "<uuid>", "secuencia_leida": 3, "secuencia": 2}
  ],
  "causa": "cambio_de_prioridad",   // obligatoria si el plan está publicado
  "motivo": "el cliente pidió otro orden"
}
```

### Por qué cada línea declara lo que el cliente leyó

**[DISEÑO]** `secuencia_leida` **no es adorno**. La regla 27 exige *"no
sobrescribir silenciosamente cambios concurrentes"*, y **[MEDIDO]**
`ProgramacionOrden` **no tiene campo de concurrencia optimista** —ni `revision` ni
versión, a diferencia de `OrdenTrabajo`—.

> **Sin ese dato la regla 27 sería inaplicable.** Lo único disponible como token
> de versión es lo que el cliente afirma haber visto.

### Respuesta 200

```jsonc
{
  "jornada": {"plan": "...", "dia": "...", "plan_estado": "borrador",
              "plan_semana": "..."},
  "recibidas": 3, "modificadas": 2, "sin_cambio": 1,
  "lote": "<uuid>",            // null cuando no cambió nada
  "resultado": "aplicado",     // o "sin_cambios"
  "novedad": "<uuid|null>",
  "lineas": [ ... ],           // la jornada entera, ya ordenada
  "resumen": { ... },          // el de M03-E2
  "aviso": "..."
}
```

### Errores

| Código | Caso | Qué trae |
|:--:|---|---|
| **409** `JORNADA_CAMBIO` | alguien tocó la jornada entre la lectura y el envío | `conflictos: [{linea, leida, actual}]` + *"Recárgala: no se aplicó nada"* |
| **400** `JORNADA_INCOMPLETA` | el conjunto no es el real | `faltantes`, `sobrantes`, `desconocidas`, `ajenas` |
| **400** `NO_SE_PUDO_SECUENCIAR` | motivo faltante, día fuera de la semana, línea repetida | detalle |
| **404** `NO_EXISTE` | el plan no existe en esta organización | — |
| **403** | sin rol de gestión | — |

---

## 5. Locks

**[IMPLEMENTADO]**

```python
bloqueadas = (ProgramacionOrden.objects
              .select_for_update()
              .filter(Q(org=org) & (Q(id__in=pedidas) |
                                    Q(programacion=plan, dia=dia, estado__in=vigentes)))
              .order_by("id"))                      # 1. líneas, por id ascendente
plan = ProgramacionSemanal.objects.select_for_update().get(...)   # 2. el plan
```

**[MEDIDO] Por qué ese orden y no otro** — las seis operaciones del módulo:

| Operación | Bloquea |
|---|---|
| `programar_orden` | `OrdenTrabajo` |
| `publicar_programacion` | `ProgramacionSemanal` |
| `reprogramar_orden` | `OrdenTrabajo` → plan |
| `registrar_contingencia` | `OrdenTrabajo` |
| `actualizar_secuencia` (E4) | `ProgramacionOrden` → plan |
| **`secuenciar_jornada` (E5)** | **`ProgramacionOrden` (por id) → plan** |

> **El plan es siempre el último.** Si E5 lo bloqueara primero: E4 sostiene la
> línea y pide el plan; E5 sostiene el plan y pide la línea. **Ciclo.**
>
> Y ordenar las líneas por `id` elimina el ciclo simétrico entre dos E5
> concurrentes.

**[DISEÑO]** Se bloquea la **unión** de lo enviado y lo real: si el cliente omitió
una línea, esa línea también tiene que estar quieta mientras se comprueba que
falta.

---

## 6. Concurrencia

**[VALIDADO]** Dos mecanismos distintos, y **dos pruebas distintas** — porque no
miden lo mismo:

### `test_17` — A no sobrescribe a B  *(mide la comprobación optimista)*

```
A lee la jornada (1 y 2)
B cambia la línea b: 2 → 7          (por la vía individual de E4, HTTP real)
A aplica lo que había leído          → 409 JORNADA_CAMBIO
```

Leído **desde conexión independiente**: `a = 1` (A no movió la suya) y `b = 7`
(**B sobrevive**). **No se aplicó nada**, ni siquiera la línea que sí coincidía.

### `test_18` — dos secuenciaciones concurrentes  *(mide el lock)*

Dos peticiones HTTP reales contra PostgreSQL, en paralelo, sobre la misma
jornada:

```
codigos = [200, 409]
estado final = (3,4) ó (5,6)   -- nunca una mezcla
lotes de eventos = 1
```

**[VALIDADO] Verificado desarmando los locks:**

```
sin select_for_update  →  FAILED   codigos == [200, 200]   (las dos aplicaron)
con locks              →  passed   [200, 409]
```

> **`test_17` pasa incluso sin locks**, y es correcto que así sea: su conflicto lo
> detecta `secuencia_leida`, no el lock. Son dos protecciones para dos problemas
> distintos, y cada prueba mide la suya.

---

## 7. Idempotencia

**[IMPLEMENTADO]** Se reutiliza `manejar_idempotencia`. **No se creó un segundo
sistema.**

**[MEDIDO]** La clave identifica **la operación de jornada completa**: el
decorador compara `(org, Idempotency-Key)` más `método`, `endpoint` y el hash
canónico del cuerpo — y `calcular_hash_canonico` serializa listas igual que
diccionarios, así que un cuerpo con `lineas: [...]` se hashea bien.

**[VALIDADO]** El replay devuelve **el mismo `lote`**, no uno nuevo, y quedan
**2 eventos para 2 líneas** — sin duplicados.

---

## 8. Auditoría

**[MEDIDO]** El evento de conjunto **no se puede escribir**:
`campo_evento_trabajo.orden_id` es **`NOT NULL`**, y una jornada no tiene orden de
la cual colgar. Por eso, como E5-A anticipó: **un evento por línea modificada,
todos con un `lote` compartido**.

```jsonc
{
  "lote": "<uuid compartido>", "linea": "<uuid>",
  "anterior": 1, "nuevo": 3,
  "anterior_sin_secuenciar": false, "nuevo_sin_secuenciar": false,
  "jornada": {"plan": "...", "dia": "...", "plan_estado": "...", "plan_semana": "..."},
  "lote_tamano": 3, "lote_cambiadas": 3, "lote_sin_cambio": 0,
  "posicion_en_lote": 1,
  "empate": {...}, "causa": "...", "motivo": "...", "novedad": "<uuid|null>"
}
```

**[VALIDADO]** Comprobado evento por evento: `orden_id`, `lote`, `anterior`,
`nuevo`, semántica del 0, actor, timestamp y motivo.

**[IMPLEMENTADO]** **Las líneas sin cambio NO generan evento** (regla 23), y su
número queda en `lote_sin_cambio`.

**[IMPLEMENTADO]** **Una `NovedadOperativa` por lote, no una por línea**: la
jornada se reordenó por un motivo, no por N motivos. Verificado: 2 líneas
cambiadas en plan publicado → **1** novedad.

**[MEDIDO]** El caso del encargo se reconstruye línea a línea:

```
A: 1 → 3      B: 2 → 1      C: 3 → 2
```

---

## 9. Las 33 pruebas

| # | Prueba | |
|:--:|---|:--:|
| 1 | jornada vacía | **PASS** |
| 2 | una línea | **PASS** |
| 3 | varias líneas | **PASS** |
| 4 | **A 1→3, B 2→1, C 3→2 reconstruible** | **PASS** |
| 5 | secuencias repetidas → permitidas, empate anotado | **PASS** |
| 6 | **varias líneas en 0** → sin empate | **PASS** |
| 7 | mezcla 0 + >0 | **PASS** |
| 8 | **todas sin cambio → 200**, 0 eventos, ni se toca la fila | **PASS** |
| 9 | una sin cambio + otras modificadas | **PASS** |
| 10 | línea inexistente | **PASS** |
| 11 | línea de otra jornada | **PASS** |
| 12 | línea de otro plan | **PASS** |
| 12b | **falta una línea de la jornada** (G-2) | **PASS** |
| 13 | plan borrador, sin motivo | **PASS** |
| 14-15 | plan publicado con motivo | **PASS** |
| 16 | plan publicado sin motivo → rechazo | **PASS** |
| 16b | publicado **sin cambios** no exige motivo | **PASS** |
| **17** | **A no sobrescribe a B** (HTTP real) | **PASS** |
| **18** | **dos secuenciaciones concurrentes** | **PASS** |
| 19 | rollback por fallo de escritura | **PASS** |
| 20 | rollback por fallo de auditoría | **PASS** |
| 20b | rollback **desde conexión independiente** | **PASS** |
| 21-22 | idempotencia y replay | **PASS** |
| 23 | otra organización → 404 | **PASS** |
| 23b | el servicio no confía en la vista | **PASS** |
| 24 | permiso insuficiente → 403 | **PASS** |
| 24b | sin sesión | **PASS** |
| 25-28 | **no toca `programada_para`, estado, asignación ni prioridad** | **PASS** |
| 29-30 | un evento por línea, con lote común | **PASS** |
| 31 | las líneas sin cambio no generan evento | **PASS** |
| 32 | sin eventos duplicados | **PASS** |
| **33** | **no existe UNIQUE sobre `secuencia`** | **PASS** |
| — | la lectura de E2 muestra el resultado | **PASS** |
| — | E5 no toca M09 | **PASS** |
| — | **0 conexiones salientes** | **PASS** |
| — | **control: locks desarmados → test_18 FALLA** | **PASS** |

```
35 passed · 0 failed · 0 skipped
```

**[MEDIDO]** La prueba 19 verifica el rollback **rompiendo la segunda línea** — la
primera ya estaba escrita, y tampoco queda.

---

## 10. Regresión

```
Suites de M03 juntas .................. 199 passed
  M03-B 29 · M03-C 30 · M03-D3 33 · M03-D3.2 17 · M03-E2 25 · M03-E4 30 · M03-E5 35

Suite completa del backend ............ 676 passed / 0 failed / 0 skipped
```

| | |
|---|---|
| Baseline (M03-E4) | **641** |
| M03-E5-B | **+35** |
| **Total** | **676** |

**[VALIDADO]** Ninguna falla. Las 3 aserciones de M03-E2 que cambiaron están
explicadas en §"Una contradicción encontrada".

---

## 11-12. `makemigrations --check` y migraciones

```
No changes detected
```

# 0 migraciones · 0 modelos · 0 campos · 0 constraints

**[MEDIDO]** No se creó `UNIQUE` sobre `secuencia`, y hay una prueba (33) que
consulta `pg_constraint` y `pg_indexes` para comprobarlo.

---

## 13. Producción

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

Todo en un contenedor PostgreSQL 16 aislado (`pg-e5`), con un runner **sin una
sola credencial de producción**.

---

## 14. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

**[VALIDADO]** Instrumentado en `socket.socket.connect`, y **el cero se leyó
después de probar que el instrumento dispara** con una sonda deliberada.

---

## 15. Gaps restantes

| # | Gap | Tipo | ¿Bloquea? |
|:--:|---|---|:--:|
| **B-1** | **`SECUENCIA_SIN_CAMBIO` de E4 sigue en 409** mientras E5 responde **200** al mismo hecho en lote. G-1 cerró el caso del lote; **el individual sigue sin firma** | **[PENDIENTE]** — incoherencia visible entre dos endpoints | no |
| G-3 | **"El último gana"** cuando el cliente no envía `secuencia_leida`: el campo es opcional, y sin él **esa línea no se comprueba** | [RIESGO] documentado | no |
| G-4 | ¿Escribir evento para las líneas sin cambio? Hoy **no** (regla 23), y el conteo queda en `lote_sin_cambio` | [PENDIENTE] cerrado por regla | no |
| G-6 | **Duplicación E4 ↔ E5**: "capturar, comparar, escribir, auditar" está dos veces. Extraer el helper obligaría a repetir las 30 pruebas de E4 | [PENDIENTE] alcance | no |
| R-1 | `_programacion_vigente` de M09 sigue sin desempate (no se puede tocar) | [RIESGO] | no |
| R-2 | **`campo_*` sin RLS** — B-7 no lo resuelve | [RIESGO] seguridad | no |
| E-6 / E-7 | `prioridad` y `zona` siguen expuestas y **sin ordenar** | [PENDIENTE] | no |

### El que conviene mirar primero

**[RIESGO] B-1 ya no es solo una decisión pendiente: es una incoherencia
observable.** Pedir la misma secuencia que ya tiene una línea devuelve **409** por
la vía individual (E4) y **200** por la de jornada (E5). Las dos conductas están
aprobadas por separado —E4 provisional, E5 por G-1— pero un cliente que use las
dos rutas verá dos respuestas distintas al mismo hecho.

**[PENDIENTE]** Firmar B-1 alineando E4 con G-1 lo cerraría con un cambio de tres
líneas.

---

```
código ......... 1 archivo de pruebas + 6 modificados
migraciones .... 0     modelos .... 0     roles .... 0     constraints .... 0
M09 ............ sin tocar        revisar_coherencia ... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
