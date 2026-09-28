# M03-E4 — Implementación de secuenciación

**Fecha:** 2026-09-18
**Estado:** **[VALIDADO]** — con **un caso reportado** que la autorización no cubría (§5).

---

## Resumen

```
Archivos creados:      1        Archivos modificados:   5
Migraciones:           0        ← "No changes detected"
Modelos:               0        Roles: 0        Constraint UNIQUE: NO creada

Tests M03-E4:         30 passed / 0 failed / 0 skipped
Regresión completa:  641 passed / 0 failed / 0 skipped   (611 base + 30)

Locks:        línea → plan, orden fijo  -- verificado desarmándolos
Producción:   SIN CAMBIOS -- 17 claves idénticas a la foto de E3
Commit:       no
```

---

## 1. Estado previo

**[MEDIDO]** Antes de E4, la única forma de cambiar la `secuencia` de una línea
ya escrita era **reprogramar la orden** — mover el *trabajo* para corregir el
*orden* en que se propone hacerlo.

**[MEDIDO]** Producción, solo `SELECT`, **idéntica a la foto de M03-E3**:

```
ProgramacionSemanal 0 · ProgramacionOrden 0 · EventoTrabajo 12 (0 de secuencia)
NovedadOperativa 0 · PropuestaSupervisor 0 · acciones_propuestas 40
operaciones_externas 0 · kill switch detenido
django_migrations 192 · tablas public 135 · índices public 829
```

---

## 2. Diseño implementado

**[IMPLEMENTADO]** Una operación de servicio y un endpoint. **Nada nuevo en el
modelo.**

```python
actualizar_secuencia(*, org, linea, secuencia, actor,
                     causa="", motivo="", contexto=None)
    → (linea, evento, novedad|None)
```

### Lo que revisé antes de escribir (§ANTES DE IMPLEMENTAR)

| Pieza | Decisión |
|---|---|
| modelo | **no se toca** — `secuencia` ya existe, `NOT NULL`, `CHECK >= 0` |
| serializer | **+1 nuevo** `SecuenciaSerializer`; se **corrigió** `LineaJornadaSerializer` (§17) |
| permisos | **reutilizado** `EsJefeDeOperaciones` → `ROLES_GESTION` |
| views | **+1** en `operaciones/views.py`, junto a las demás del módulo |
| servicios | **+1 función** en `operaciones/programacion.py`, con los helpers que ya existían |
| lectura de E2 | **reutilizada** — `LineaJornadaSerializer` devuelve la línea |
| M03-B / C / D3 | **sin tocar** |
| auditoría | **reutilizado** `EventoTrabajo`; `_novedad_de` y `_validar_causa` ya existían |
| idempotencia | **reutilizada** `manejar_idempotencia` — **no se creó otro sistema** |

**No se creó ninguna estructura duplicada.**

---

## 3. Endpoint

```
POST /api/operaciones/programacion/linea/<uuid:linea_id>/secuencia/
{ "secuencia": 3, "causa": "...", "motivo": "...", "contexto": {...} }
```

**[DISEÑO]** `SecuenciaSerializer` declara **solo `secuencia`** (más causa,
motivo y contexto). **No declara** `dia`, `plan`, `zona`, `prioridad` ni
`programada_para`: *lo que esta operación no debe tocar, no se declara* — mismo
criterio que A-3.3 con `org`.

| Respuesta | Cuándo |
|---|---|
| **200** | cambiada |
| **400** | secuencia negativa · falta causa en plan publicado · organización |
| **403** | rol sin gestión · sin sesión |
| **404** | la línea no existe **en esta organización** |
| **409** | **`SECUENCIA_SIN_CAMBIO`** — ver §5 |

---

## 4. Reglas de `secuencia = 0`

**[DECISIÓN APROBADA]** `0` = **SIN SECUENCIAR**. No es primera posición, no es
prioridad.

**[IMPLEMENTADO]** De ahí se siguen tres conductas, y las tres tienen prueba:

| | Conducta | Prueba |
|---|---|---|
| 1 | **poner 0 es legítimo** — es *dessecuenciar* | `test_2` |
| 2 | **varias líneas en 0 NO son empate** | `test_5` |
| 3 | el evento **declara** el significado en vez de dejarlo deducir | `test_1` |

```python
if secuencia == 0:
    return {"hay_empate": False,
            "razon": "secuencia 0 significa sin secuenciar: no hay empate"}
```

**[IMPLEMENTADO]** El evento guarda `anterior_sin_secuenciar` y
`nuevo_sin_secuenciar` como booleanos explícitos: **quien lea la bitácora dentro
de un año no tiene por qué recordar qué significa el 0.**

---

## 5. Tratamiento de duplicados

**[DECISIÓN APROBADA]** Los duplicados **> 0** se permiten. No se recompacta, no
se reasigna, no se desplaza, **no se toca ninguna otra línea**.

**[IMPLEMENTADO]** El empate se **calcula y se anota**, nunca se valida:

```jsonc
"empate": {"hay_empate": true, "con": [{"linea": "<uuid>", "orden": 9520}]}
```

**[VALIDADO]** `test_6` comprueba que el cambio se acepta **y** que la otra línea
conserva su número. `test_no_se_toca_ninguna_otra_linea` lo verifica sobre tres
líneas vecinas.

### El caso que la autorización NO cubría — **[REPORTADO]**

**Pedir la secuencia que la línea ya tiene.** El encargo no dice qué hacer, y el
código tiene que hacer algo: escribir un evento con `anterior == nuevo`, o
rechazar.

**[IMPLEMENTADO]** Se **rechaza** con **409** y la respuesta lo declara:

```json
{"error": "SECUENCIA_SIN_CAMBIO",
 "pendiente": "DECISION_EMPRESARIAL_SecuenciaSinCambio"}
```

> **Rechazar no es la decisión: es la única salida REVERSIBLE.** Aceptarlo
> escribiría en una bitácora **append-only** un cambio que no ocurrió, y eso no
> se puede quitar después. Es además **la misma forma que M03-D3.2 ya aprobó**
> para `YaEnEsaFecha` en la reprogramación.

**[PENDIENTE]** Requiere firma. Si el negocio prefiere registrar el intento nulo,
es una guarda de tres líneas.

---

## 6. Plan borrador

**[IMPLEMENTADO]** **No exige causa.** Se mantiene D1.1-D: *"un borrador no
compromete a nadie: las cuadrillas no lo ven"*.

**[VALIDADO]** `test_8`: cambio aceptado, **0 `NovedadOperativa`**, `causa` vacía
en el evento.

---

## 7. Plan publicado

**[DECISIÓN APROBADA — E-4]** Publicar **no congela**. Una modificación posterior
es **formal y trazable**.

**[IMPLEMENTADO]**

| | |
|---|---|
| **se permite** el cambio | sí |
| **exige causa** | **sí** — se aplica D1.1-D: *el motivo es obligatorio cuando existe compromiso operativo*, y un plan publicado lo es |
| tipo de evento | **`secuencia_en_plan_publicado`**, distinto de `secuencia` |
| `NovedadOperativa` | **solo si hay causa**, y con la causa del **catálogo cerrado existente** — no se inventó ningún tipo nuevo |

**[VALIDADO]** `test_9` (sin causa → 400, nada cambia) y `test_10` (con causa →
200 y traza completa).

> **[DISEÑO] Por qué exigir causa aunque el encargo no la listara:** el §PLAN
> PUBLICADO enumera qué registrar, no si el motivo es obligatorio. D1.1-D **sí lo
> decidió**, y E4 no la contradice. Y entre las dos lecturas, **exigir es
> reversible y no exigir no lo es**: los eventos ya escritos sin motivo no se
> pueden completar después.

---

## 8. Trazabilidad

**[IMPLEMENTADO]** El evento registra **los ocho datos que el encargo exige**,
más dos:

| Exigido | Campo |
|---|---|
| valor anterior | `datos.anterior` |
| valor nuevo | `datos.nuevo` |
| plan | `datos.plan`, `plan_semana`, `plan_estado` |
| OT | `EventoTrabajo.orden_id` |
| actor | `EventoTrabajo.profile` |
| fecha/hora | `EventoTrabajo.created_at` |
| contexto de publicación | `datos.plan_estado` + el `tipo` del evento |
| **si quedó empate con otras OT** | **`datos.empate`** con la lista de líneas |
| *(añadido)* | `anterior_sin_secuenciar`, `nuevo_sin_secuenciar` |
| *(añadido)* | `datos.linea`, `datos.dia`, `causa`, `motivo`, `novedad` |

**[MEDIDO]** El valor anterior **se captura de la fila bloqueada antes de
mutarla** — R-8' de M03-D2. `test_11` encadena dos cambios y comprueba
`[(6,2), (2,9)]`.

**[DISEÑO]** **`common.Activity` no se usa**: sus `ENTITY_TYPE_CHOICES` no
incluyen entidades de M03 y declararlas exige migración.

---

## 9. Concurrencia

**[IMPLEMENTADO]** Dos locks, en **orden fijo: línea → plan**.

```python
fresca = ProgramacionOrden.objects.select_for_update().get(pk=..., org=org)
plan   = ProgramacionSemanal.objects.select_for_update().get(pk=..., org=org)
```

**[DISEÑO]** Dos decisiones de detalle, ambas deliberadas:

1. **El plan se bloquea el último**, igual que en M03-D3 (OT → plan). Así ninguna
   operación del módulo espera por otra y **no se cierra ningún ciclo**.
2. **Se piden por separado y sin `select_related`**: un `FOR UPDATE` sobre un
   JOIN bloquearía filas de las tablas unidas, que es justo lo que no hace falta.

**[IMPLEMENTADO]** **No se creó ninguna constraint `UNIQUE`** sobre `secuencia`
(§CONCURRENCIA lo prohíbe explícitamente) y **no hubo migración**.

### Verificado desarmándolo

**[VALIDADO]** `test_13` lanza dos cambios simultáneos a valores distintos y
comprueba que **la cadena de eventos encadena**: el `anterior` de cada evento es
el `nuevo` del anterior, y el último coincide con la fila.

```
sin locks  →  FAILED test_13_dos_cambios_simultaneos_no_pierden_actualizacion
con locks  →  30 passed
```

> **Por qué esa aserción y no "solo una gana":** las dos peticiones son
> legítimas. Lo que no puede pasar es que **la bitácora afirme una transición que
> no ocurrió** — sin lock, la segunda diría que venía del valor viejo y el cambio
> de la primera desaparecería del historial.

---

## 10. Idempotencia

**[IMPLEMENTADO]** Se reutiliza **`manejar_idempotencia`** tal cual — el mismo
decorador que usan las vistas de campo. **No se creó un segundo sistema.**

**[VALIDADO]** `test_14`: dos POST con la misma `Idempotency-Key` → el segundo
devuelve `Idempotent-Replay: true` y **queda un solo evento**.

**[MEDIDO]** Es la primera vez que una vista de `operaciones/` usa ese decorador.
Funciona porque solo depende de `request.org`, `request.data`, `request.path` y
`MutacionIdempotente` — nada específico de campo.

---

## 11. Rollback

**[VALIDADO]** Se rompe la operación en el **último** paso, con la secuencia ya
escrita en la transacción:

| Verificación | Resultado |
|---|---|
| secuencia modificada **sin** evento | **no ocurre** — vuelve a 4 |
| evento **sin** modificación | **no ocurre** — 0 eventos |
| estado parcial | **ninguno** — 0 novedades |
| leído **desde conexión independiente** | `secuencia = 4` | 

---

## 12. Multi-tenant

**[VALIDADO]**

| Caso | Resultado |
|---|---|
| A cambia una línea de B | **404** — no 403: un 403 confirmaría que existe |
| servicio llamado con `org=A` y línea de B | `ErrorProgramacion` |

**[DISEÑO]** **El id por sí solo nunca alcanza**: la vista busca la línea
`filter(id=..., org=request.org)`, **y el servicio revalida** — no confía en que
la vista lo haya hecho. Mismo criterio que M03-B, C y D3, con prueba propia.

---

## 13. Permisos

**[IMPLEMENTADO]** `EsJefeDeOperaciones` → `ROLES_GESTION` =
`{ADMIN, SUPERVISOR, OPERACIONES}`. **Reutilizado. 0 roles nuevos, 0 permisos
ampliados.**

**[VALIDADO]** Un `USER` → **403**; sin sesión → **403**.

---

## 14. Lectura de jornada

**[VALIDADO]** Las cinco comprobaciones del encargo:

| | Comprobación | Prueba |
|---|---|---|
| 1 | la lectura muestra el valor nuevo | `test_17` |
| 2 | **`secuencia = 0` aparece como 0** | `test_17` |
| 3 | los duplicados > 0 siguen visibles | `test_17b` |
| 4 | **el desempate por `id` sigue siendo determinista** | `test_17b`, 3 corridas idénticas |
| 5 | el desempate no se interpreta como decisión | el resumen marca `orden_arbitrario`; ningún veredicto |

---

## 15. I-1

**[DECISIÓN APROBADA — E-5]** La duplicidad de secuencia **NO es** el ERROR de
I-1.

**[VALIDADO]** `test_18`: con dos líneas vigentes de la **misma orden**, I-1
dispara; y **ninguno de sus mensajes menciona `secuencia`** — son invariantes
distintas.

**[VALIDADO]** `test_7`: dos órdenes distintas con la misma secuencia →
`revisar_coherencia` devuelve `[]`.

**[MEDIDO]** **`revisar_coherencia` no se modificó.** No hizo falta ningún cambio,
así que no hubo nada que reportar por esa vía.

---

## 16. M09

**[MEDIDO]** **No se modificó.** Y se comprueba por efecto, no por declaración:

```python
assert "secuencia" not in inspect.getsource(supervisor)
```

**[VALIDADO]** Tras cambiar una secuencia, `PropuestaSupervisor.objects.count()`
sigue en 0.

---

## 17. Tests propios

**[VALIDADO] 30 passed / 0 failed / 0 skipped.** Los 20 puntos del encargo:

| # | Punto | Prueba | |
|:--:|---|---|:--:|
| 1 | 0 → 1 | `test_1` | **PASS** |
| 2 | 1 → 0 | `test_2` | **PASS** |
| 3 | 1 → 2 | `test_3` | **PASS** |
| 4 | mantener secuencia | `test_4`, `4b` | **PASS** *(caso reportado, §5)* |
| 5 | varias OT en 0 | `test_5` | **PASS** |
| 6 | varias OT en 1 | `test_6` | **PASS** |
| 7 | duplicados > 0 permitidos | `test_7` | **PASS** |
| 8 | plan borrador | `test_8` | **PASS** |
| 9 | plan publicado | `test_9` | **PASS** |
| 10 | trazabilidad del publicado | `test_10` | **PASS** |
| 11 | valor anterior registrado | `test_11` | **PASS** |
| 12 | rollback | `test_12`, `12b` *(desde fuera del ORM)* | **PASS** |
| 13 | **concurrencia** | `test_13` *(verificada desarmando el lock)* | **PASS** |
| 14 | idempotencia | `test_14` | **PASS** |
| 15 | multi-tenant | `test_15`, `15b` | **PASS** |
| 16 | permisos | `test_16`, `16b`, `16c` | **PASS** |
| 17 | lectura E2 después del cambio | `test_17`, `17b` | **PASS** |
| 18 | I-1 no afectado | `test_18` | **PASS** |
| 19 | reprogramación D3 no afectada | `test_19`, `19b` | **PASS** |
| 20 | publicación M03-C no afectada | `test_20` | **PASS** |
| — | no se toca ninguna otra línea | `test_no_se_toca...` | **PASS** |
| — | M09 no consume secuencia | `test_m09_no_consume...` | **PASS** |
| — | 0 conexiones salientes | `test_ninguna_conexion...` | **PASS** |

### Un defecto de M03-E2 que este paso destapó

**[MEDIDO]** `test_14` falló la primera vez con:

```
TypeError: Object of type UUID is not JSON serializable
```

**La causa estaba en E2, no en E4.** `LineaJornadaSerializer` es un
`ModelSerializer`, y sus dos FK (`orden`, `programacion`) se mapeaban a
`PrimaryKeyRelatedField`, que devuelve el **objeto `UUID`** en `.data`.

> Al **renderizar** una respuesta da igual —el `JSONRenderer` lo convierte— pero
> `manejar_idempotencia` **guarda** ese `.data` en un `JSONField`, y ahí revienta.
> El defecto estaba latente desde E2 y **solo se veía por esta vía**.

**[IMPLEMENTADO]** Corregido en el origen: las dos FK se declaran
`UUIDField(source="..._id")`, que emite cadena. **La suite de E2 (25 pruebas)
vuelve a pasar completa.**

---

## 18. Regresión

```
pytest operaciones/tests/ campo/tests/
  641 passed, 0 failed, 0 skipped      en 268s
```

| | |
|---|---|
| Baseline (M03-E2) | **611** |
| M03-E4 | **+30** |
| **Total** | **641** |

**[VALIDADO]** Repetidas completas por haber tocado componentes validados:

| Suite | Motivo | Resultado |
|---|---|---|
| **M03-E2** (25) | se corrigió `LineaJornadaSerializer` | **25 passed** |
| **M03-B** (29), **M03-C** (30), **M03-D3** (33), **M03-D3.2** (17) | se extendió `programacion.py` | **todas passed** |
| **M09-F** | guarda de rutas actualizada | **passed** |

### La guarda de M09-F, otra vez con su motivo

`linea-secuencia` hizo fallar el inventario pinchado. Se actualizó **y se
escribió por qué no es una ruta de ejecución**: *escribe una columna de una línea
de plan y su evento; no llama a ningún sistema externo, no despacha, no reasigna
y no mueve trabajo — cambiar la secuencia NO es reprogramar*. La comprobación de
substrings prohibidos sigue intacta.

---

## 19. `makemigrations --check`

```
No changes detected
```

**[MEDIDO]** Limpio. **0 migraciones, 0 modelos, 0 campos, 0 constraints.**

---

## 20. Producción

# SIN CAMBIOS

**[MEDIDO]** Solo `SELECT`, `read_only = True`. **17 claves comparadas contra la
foto de M03-E3 → DIFERENCIAS: NINGUNA.**

```
django_migrations 192 · tablas public 135 · índices public 829
ProgramacionSemanal 0 · ProgramacionOrden 0 · EventoTrabajo 12
eventos de secuencia 0 · NovedadOperativa 0 · PropuestaSupervisor 0
acciones_propuestas 40 · operaciones_externas 0 · kill switch detenido
```

**[VALIDADO] 0 efectos externos**: instrumentado en `socket.connect`, y el cero
se leyó **después de probar que el instrumento dispara**.

Todo en un contenedor PostgreSQL 16 aislado (`pg-e4`), con un runner **sin una
sola credencial de producción**. Entorno eliminado al terminar.

---

## 21. GAPs restantes

| # | GAP | Tipo | ¿Bloquea? |
|:--:|---|---|:--:|
| **B-1** | **`SecuenciaSinCambio`**: ¿rechazar o registrar el intento nulo? Implementado como rechazo **reversible y declarado** | **[REPORTADO]** decisión | **sí, para cerrar E4** |
| R-1 | **Sin datos**: 0 planes, 0 líneas. Ninguna de las reglas de E4 se ha ejercitado con trabajo real | **[RIESGO]** | no |
| R-2 | **No hay pantalla**: la única vía para reordenar es API | **[PENDIENTE]** producto | no |
| R-3 | **`prioridad` sigue expuesta y sin ordenar** (E-6) | [PENDIENTE] | no |
| R-4 | **`zona` sigue sin catálogo ni orden** (E-7) | [PENDIENTE] | no |
| R-5 | `_programacion_vigente` de M09 sigue sin desempate (no se puede tocar) | [RIESGO] | no |
| R-6 | **`campo_*` sin RLS** — B-7 no lo resuelve | [RIESGO] seguridad | no |
| R-7 | No existe operación para **mover varias líneas a la vez** | [PENDIENTE] | no |

**[MEDIDO]** No apareció ninguna necesidad de migración, modelo, rol ni
constraint. **La única decisión no cubierta es B-1, y está reportada.**

---

## 22. Recomendación para M03-E5

**[DISEÑO]** Tres cosas, en orden de utilidad:

### 22.1 Cerrar B-1 antes que nada

Es de una línea y desbloquea el cierre formal de E4.

### 22.2 Reordenar varias líneas en una sola operación (R-7)

**[MEDIDO]** Hoy poner tres órdenes en 1-2-3 son **tres peticiones, tres
transacciones y tres eventos**, y entre la primera y la tercera el plan pasa por
estados intermedios que un lector de la jornada puede ver.

> **Eso no es un defecto de E4** —el encargo pedía explícitamente no tocar otras
> líneas— **pero es el siguiente hueco real**: secuenciar una jornada es
> inherentemente una operación sobre un conjunto.
>
> **[PENDIENTE]** Y trae una decisión: ¿un reordenamiento en bloque es **un**
> evento o **N**? Con lo que hay, `EventoTrabajo` cuelga de una orden, así que un
> evento por línea es lo natural — pero entonces nada los agrupa como una sola
> decisión.

### 22.3 La pantalla (R-2)

**[RIESGO]** Reordenar una jornada por API, línea a línea, es exactamente el tipo
de tarea que nadie hará a mano. **Las reglas de E4 están completas y sin uso
posible** hasta que exista una superficie donde arrastrar filas.

### 22.4 Y el recordatorio que no ha cambiado

**[RIESGO]** **0 planes y 0 líneas en producción**, y las 3 órdenes reales
clasifican como **contingencia**. E4 implementó correctamente reglas que **aún no
tienen ni un caso real que las ejercite**.

---

```
código ......... 1 archivo de pruebas + 5 modificados
migraciones .... 0     modelos .... 0     roles .... 0     constraints .... 0
M09 ............ sin tocar      revisar_coherencia ... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
