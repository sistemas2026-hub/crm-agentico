# M03-D3 — Implementación de reprogramación

**Fecha:** 2026-09-18
**Estado:** **[VALIDADO]** con **un caso [BLOQUEADO]** — ver §9 y §20.

---

## Resumen

```
Archivos creados:      1        Archivos modificados:   4
Migraciones:           0        ← "No changes detected"
Modelos nuevos:        0        Tablas nuevas:  0        Roles nuevos: 0
Endpoints:             2        (+1 ajuste a programar)

Tests M03-D3:         33 passed / 0 failed / 0 skipped
M03-B + M03-C:        59 passed / 0 failed        (29 + 30, sin regresión)
Regresión completa:  569 passed / 0 failed / 0 skipped   (536 base + 33)

Locks:        select_for_update, orden OT → plan  -- verificado desarmándolo
Rollback:     verificado por ORM y por conexión independiente
Efectos externos: 0    -- con el instrumento probado antes de leer su cero
Producción:   SIN CAMBIOS (solo SELECT, read_only = True)
Commit:       no
```

---

## 1. Archivos creados / modificados

### Creado (1)

| Archivo | |
|---|---|
| `operaciones/tests/test_m03d3_reprogramacion.py` | **33 pruebas** |

### Modificados (4)

| Archivo | Cambio |
|---|---|
| `operaciones/programacion.py` | **+3 excepciones** (`NoEstaProgramada`, `RequiereContingencia`, `YaEnEsaFecha`), **+6 funciones** (`clasificar_ruta`, `reprogramar_orden`, `registrar_contingencia`, `_programacion_vigente_de`, `_validar_causa`, `_bloque_sla`, `_foto`, `_novedad_de`), **+ajuste** a `programar_orden` |
| `campo/despacho_views.py` | **+2 vistas**: `ReprogramarTrabajoView`, `ContingenciaTrabajoView`; **+causa/motivo** en la llamada de `ProgramarTrabajoView` |
| `campo/serializers.py` | **+2 serializadores**: `ReprogramarSerializer`, `ContingenciaSerializer`; **+2 campos** en `ProgramarSerializer` |
| `campo/urls.py` | **+2 rutas** |

**[MEDIDO]** `makemigrations --check --dry-run` → **"No changes detected"**.

---

## 2. Cambios funcionales

```
POST /api/campo/trabajos/<pk>/reprogramar/     rutas NORMAL y CORRECCIÓN
POST /api/campo/trabajos/<pk>/contingencia/    la ruta excepcional
POST /api/campo/trabajos/<pk>/programar/       + adición formal a plan publicado
```

**[MEDIDO]** Las tres rutas viven en `campo/`, así que **la guarda de rutas de
M09-F no se toca** — fija el inventario de `operaciones/`.

---

## 3. Reglas implementadas

| Regla | Origen | Estado |
|---|---|---|
| Tres rutas: normal, corrección, contingencia | D1.1-A | **[IMPLEMENTADO]** |
| La frontera es **la vuelta actual**, no `iniciada_en` | D1.1-A | **[IMPLEMENTADO]** |
| Agregar a plan publicado = **adición formal** | D1.1-B | **[IMPLEMENTADO]** |
| Causa en `NovedadOperativa`, efecto en `EventoTrabajo` | D1.1-C | **[IMPLEMENTADO]** |
| `tipo="reprogramacion"` **no sirve como causa** | D1.1-C | **[IMPLEMENTADO]**, con prueba |
| Motivo obligatorio con compromiso, no en borrador | D1.1-D | **[IMPLEMENTADO]** |
| Un solo acto: `ROLES_GESTION` | D1.1-E | **[IMPLEMENTADO]**, 0 roles nuevos |
| El SLA no se toca; se registra "no evaluado" | D1.1-F | **[IMPLEMENTADO]** |
| Capturar antes de mutar (R-8') | D2 §0.1 | **[IMPLEMENTADO]** |
| Locks OT → plan, en ese orden | D2 §9 | **[IMPLEMENTADO]** |
| La línea nunca cambia de plan: se marca y se crea otra | D2 §8 (I-3) | **[IMPLEMENTADO]** |

---

## 4. Ruta normal

```
asignada + programada  →  nueva fecha
```

**Caso A — mismo plan.** **[MEDIDO]** `unique(programacion, orden)` impide una
segunda línea, así que la línea **se actualiza**.

> El historial no se pierde: vive en el evento, que es append-only. **Lo que no
> se sobrescribe es el registro, no la fila** — la fila no puede duplicarse.

**Caso B — otro plan.** La línea anterior pasa a **`REPROGRAMADA`** y se crea una
nueva en el destino.

**[MEDIDO]** `REPROGRAMADA` existía en el modelo y **ningún código la escribía**:
M03-D3 es su primer escritor.

**Verificado:** la línea vieja conserva su `dia` y su `programacion_id` — **una
línea nunca cambia de plan** (I-3).

---

## 5. Ruta corrección

**[IMPLEMENTADO]** El caso que la regla anterior hacía imposible.

```python
ultima_reapertura = eventos(tipo="reapertura_correccion").order_by("-created_at").first()
if ultima_reapertura is None:
    return CONTINGENCIA if orden.iniciada_en else NORMAL      # fallback aprobado
inicio_posterior = eventos(datos__nuevo_estado__in=("en_camino","en_sitio"),
                           created_at__gt=ultima_reapertura.created_at).exists()
return CONTINGENCIA if inicio_posterior else CORRECCION
```

**[MEDIDO]** Se ancla en `datos.nuevo_estado` y no en nombres de evento porque
`_aplicar_transicion` lo escribe en **todos** los eventos de transición: una
acción operativa nueva queda capturada sola.

**Verificado en la prueba, por el camino real** (no fabricando eventos):

```
asignada → en_camino → en_sitio → completada_campo → correccion_requerida
```

y después:

| | |
|---|---|
| `programada_para` | **cambia** a la fecha nueva |
| `iniciada_en` | **NO se toca** — es el primer inicio histórico |
| `estado_operativo` | **NO se toca** — reprogramar no es una transición |
| causa | **siempre obligatoria** |
| evento | `reprogramacion_por_correccion`, con `datos.vuelta == 2` |

**Y si el técnico vuelve a salir**, la misma orden vuelve a ser contingencia —
probado.

---

## 6. Ruta contingencia

**[IMPLEMENTADO]** Registra y **no reprograma**.

| No se toca | Verificado |
|---|---|
| `programada_para` | sigue en la fecha original |
| la línea de plan | `dia` y `estado` intactos |
| `estado_operativo` | intacto |
| `revision` | **no sube** — no hay nada que la app deba re-sincronizar |

`NovedadOperativa` obligatoria, con `programada_nueva = None`: **una contingencia
no propone fecha**.

**[DISEÑO]** La operación normal **nunca** registra una contingencia por su
cuenta: devuelve **409 `REQUIERE_CONTINGENCIA`** y apunta a la otra ruta.

> Hacer algo distinto de lo que pidieron y contestar 2xx sería peor que rechazar.

---

## 7. Trazabilidad

**[IMPLEMENTADO]** El JSON de D2, sin cambiarlo:

```jsonc
{ "ruta": "...", "vuelta": 2,
  "anterior": {"programada_para","dia","hora_inicio","plan","plan_estado","linea"},
  "nuevo":    { … misma forma … },          // null en contingencia
  "causa": "ausencia", "motivo": "…", "novedad": "<uuid>",
  "contexto": {…},
  "sla": {"evaluado": false, "razon": "…"} }
```

| Evento | Cuándo |
|---|---|
| `reprogramacion` | ruta normal |
| `reprogramacion_por_correccion` | ruta corrección |
| `contingencia` | ruta contingencia |
| `adicion_a_plan_publicado` | agregar a un plan ya publicado |

**[MEDIDO]** `common.Activity` **no se usa**: sus `ENTITY_TYPE_CHOICES` no
incluyen entidades de M03 y declararlas exige migración. **No se forzó.**

**[DISEÑO]** Las seis claves originales del evento de M03-B se conservan tal
cual: su suite afirma sobre ellas, y **una traza no se renombra porque aparezca
un caso nuevo**.

---

## 8. Concurrencia — y una prueba que tuve que rehacer

**[IMPLEMENTADO]** `select_for_update()` sobre la **orden primero** y el **plan
destino después**. El orden no es arbitrario: M03-B bloquea solo la orden y
M03-C solo el plan, así que con OT→plan ninguna espera por otra.

### La primera versión de la prueba no medía nada

**[MEDIDO]** La escribí moviendo la orden a **dos días de la misma semana**, y
**pasó con el lock desarmado**.

> **Por qué:** dentro de un plan la constraint obliga a **actualizar** la única
> línea, así que los dos hilos pisan la misma fila. Hay actualización perdida,
> pero el estado final queda coherente — y la prueba no veía nada.

**La rehice con dos planes destino distintos.** Sin lock, los dos hilos leen la
misma línea vigente, los dos la marcan `reprogramada` y cada uno crea la suya:
**dos líneas vigentes**, I-1 rota.

```
sin lock  →  FAILED   "quedaron 2 lineas vigentes"
con lock  →  1 passed
```

**[VALIDADO]** Ahora sí mide el mecanismo. El comentario de la prueba deja escrito
por qué son dos planes y no dos días.

---

## 9. Idempotencia

**[IMPLEMENTADO]** Se reutiliza `manejar_idempotencia` tal cual — **no se creó un
segundo sistema**. Clave lógica: la cabecera `Idempotency-Key`, con ámbito
`(org, clave)` y comparación de método, endpoint y hash del cuerpo.

**Verificado:** dos POST con la misma clave → el segundo devuelve
`Idempotent-Replay: true` y **queda un solo evento**.

### `YaEnEsaFecha` — **[BLOQUEADO]**

**M03-D2 dejó este caso PENDIENTE de decisión empresarial**, y el encargo manda
detenerse y reportarlo en vez de decidir.

**El problema:** el código siempre hace algo. No implementar la guarda **también**
sería tomar la decisión — la contraria, y además irreversible.

**Lo que hice:** rechazar con **409**, y **declarar en la propia respuesta** que
la conducta es provisional:

```json
{"error": "YA_EN_ESA_FECHA", "pendiente": "DECISION_EMPRESARIAL_YaEnEsaFecha"}
```

> **Rechazar no es la decisión: es la única salida REVERSIBLE.** Aceptarlo
> escribiría en una bitácora append-only un cambio que no ocurrió, y eso no se
> puede quitar después. Si el negocio decide registrar el intento nulo, **es una
> guarda de tres líneas**.

**[BLOQUEADO]** Requiere firma antes de considerarse cerrado.

---

## 10. Rollback

**[VALIDADO]** Se rompe la operación en el **último** paso, con la línea marcada,
la línea nueva creada y `programada_para` ya escrito en la transacción.

| Verificado por | Resultado |
|---|---|
| ORM | `programada_para` original, línea original, 0 novedades |
| **conexión independiente** | `programada_para` original, **1** línea, **0** marcadas `reprogramada` |

---

## 11. Multi-tenant

**[VALIDADO]**

| Caso | Resultado |
|---|---|
| A → orden de B | **404** |
| A → su orden + plan de B | **404** |
| B → lo suyo | **200** |
| servicio llamado con `org=A` y plan de B | `ErrorProgramacion` |
| `organization_id` / `org` en el cuerpo | **ignorados**; 0 filas en B |

**404 y no 403**: un 403 confirmaría que el recurso existe.

**[RIESGO]** `campo_orden_trabajo` y `campo_evento_trabajo` **no tienen RLS**
(`relrowsecurity=false`, 0 políticas). El aislamiento lo da **solo la
aplicación**, y **B-7 no lo cambia**: la causa es `ORG_SCOPED_TABLES`
(`common/rls/__init__.py:34`), que no lista ninguna `campo_*`.

---

## 12. SLA

**[IMPLEMENTADO]** No se creó motor, ni vínculo OT→Case, ni se tocó el SLA.

**[MEDIDO]** No hay nada que impedir: `Case._sla_deadline` camina horas hábiles
desde `Case.created_at` y **no lee `programada_para`**.

Lo que se registra es **que no se puede evaluar**, y por qué:

```jsonc
"sla": {"evaluado": false, "razon": "la orden no tiene caso vinculado"}
"sla": {"evaluado": false, "razon": "la orden referencia un caso por texto
                                     ('origen_ref'), pero no existe vinculo
                                     que permita evaluarlo"}
```

**[VALIDADO]** Una fecha lejana **nunca bloquea** la reprogramación.

---

## 13-14. Pruebas ejecutadas y resultados

| # | Prueba | Resultado |
|:--:|---|:--:|
| 1 | misma semana: la línea se actualiza | **PASS** |
| 2 | otra semana: anterior `reprogramada` + nueva | **PASS** |
| 2b | persistencia por **conexión independiente** | **PASS** |
| 3 | borrador no exige causa | **PASS** |
| 4 | plan publicado **exige** causa; nada se escribe | **PASS** |
| 4b | con causa sí reprograma; novedad con la **causa** | **PASS** |
| 4c | `reprogramacion` **no sirve** como causa | **PASS** |
| 5 | adición a plan publicado: sin causa 400, con causa 201 | **PASS** |
| 5b | **el borrador sigue sin exigir nada** (M03-B intacto) | **PASS** |
| 6 | **corrección: una OT devuelta recibe fecha nueva** | **PASS** |
| 6b | la corrección siempre exige causa | **PASS** |
| 7 | si la nueva vuelta arrancó → contingencia otra vez | **PASS** |
| 8 | OT en curso no entra por la ruta normal | **PASS** |
| 9 | contingencia registra y **no reprograma** | **PASS** |
| 9b | la contingencia exige causa | **PASS** |
| **10** | **concurrencia: una sola línea vigente** | **PASS** |
| 11 | rollback por ORM | **PASS** |
| 11b | rollback **desde fuera** | **PASS** |
| 12 | cross-tenant en las dos direcciones | **PASS** |
| 12b | el servicio no confía en la vista | **PASS** |
| 12c | `organization_id` del cuerpo no decide | **PASS** |
| 13 | OT sin programación → `NO_ESTA_PROGRAMADA` | **PASS** |
| 14 | ida y vuelta: no deja dos líneas en un plan | **PASS** |
| 14b | una orden terminada no se reprograma | **PASS** |
| 15 | SLA no evaluado, **no bloquea** | **PASS** |
| 15b | con referencia de caso por texto tampoco se evalúa | **PASS** |
| 16 | idempotencia: un solo evento | **PASS** |
| 17 | `YaEnEsaFecha` → 409, 0 eventos | **PASS** *(conducta [BLOQUEADA])* |
| — | un técnico no reprograma ni registra contingencia | **PASS** |
| — | sin sesión | **PASS** |
| — | no toca asignaciones ni propuestas | **PASS** |
| — | **ningún evento histórico se borra** | **PASS** |
| — | **0 efectos externos**, con el instrumento probado | **PASS** |
| **control** | **lock desarmado → la prueba 10 FALLA** | **PASS** |

```
33 passed · 0 failed · 0 skipped
```

Las cuatro `postgres_only` (2b, 10, 11b y el control) **corrieron**: 33
recolectadas, 33 pasadas.

---

## 15-16. Regresiones M03-B y M03-C

```
pytest test_m03b_programacion.py test_m03c_publicacion.py
  59 passed, 0 failed        (29 de M03-B + 30 de M03-C)
```

**[VALIDADO] Ninguna regresión**, pese a que M03-D3 **modifica
`programar_orden`**.

**[MEDIDO] Por qué no regresaron:** ninguna prueba de M03-B/C programa en un plan
**publicado** — el ajuste solo se activa ahí. La prueba **5b** de M03-D3 fija esa
frontera explícitamente: *el borrador sigue sin exigir nada*.

### Regresión completa

```
pytest operaciones/tests/ campo/tests/
  569 passed, 0 failed, 0 skipped      en 246s
```

| | |
|---|---|
| Baseline (M03-C) | **536** |
| M03-D3 | **+33** |
| **Total** | **569** |

---

## 17. `makemigrations --check`

```
No changes detected
```

**[MEDIDO]** 0 migraciones, 0 modelos, 0 campos. **Ningún cambio de esquema.**

---

## 18. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP saliente 0
```

Instrumentado en `socket.socket.connect` alrededor de la ruta normal **y** de la
contingencia. **El cero se leyó después de probar el instrumento**: la sonda
deliberada a `127.0.0.1:9` queda registrada.

---

## 19. Estado de producción

# SIN CAMBIOS

**[MEDIDO]** Solo `SELECT`, `read_only = True`:

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
OrdenTrabajo 3 · programada_para 0/3 · AsignacionTrabajo 3 · EventoTrabajo 12
evento 'reprogramacion*' 0 · evento 'contingencia' 0
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · acciones_propuestas 40 · operaciones_externas 0
kill switch detenido · tenant_config v146
```

Todo en un contenedor PostgreSQL 16 aislado (`pg-m03d3`), con un runner **sin una
sola credencial de producción** — medido. Entorno eliminado al terminar.

---

## 20. GAPs restantes

| # | GAP | Tipo | ¿Bloquea? |
|:--:|---|---|:--:|
| **B-1** | **`YaEnEsaFecha`**: ¿rechazar o registrar el intento nulo? Implementado como rechazo **provisional y reversible**, declarado en la respuesta | **[BLOQUEADO]** — decisión | **sí, para cerrar D3** |
| R-1 | La **contingencia no tiene salida**: nada marca ni cierra una abierta | [PENDIENTE] | no |
| R-2 | La bicondicional `programada_para` ⟺ línea vigente **no es invariante** | [PENDIENTE] | no |
| R-3 | **SLA no evaluable**: falta el vínculo OT ↔ Case, que D1.1-F prohíbe crear | [DEPENDENCIA] | no |
| R-4 | `datos` JSONB **sin índice** para `clasificar_ruta` | [RIESGO] rendimiento | no |
| R-5 | **`campo_*` sin RLS** — B-7 no lo resuelve | [RIESGO] seguridad | no |
| R-6 | Catálogo de motivos **no ampliado** (clima, cliente reagenda, acceso denegado) | [PENDIENTE] | no |
| R-7 | `NovedadOperativa` **sin FK a plan**: el plan solo viaja en `datos` | [PENDIENTE] modelo | no |
| R-8 | **I-1 no está en `revisar_coherencia`**: publicar no detecta dos líneas vigentes | [PENDIENTE] | no |

**No apareció ninguna necesidad** de migración, modelo, rol ni regla empresarial
nueva durante la implementación.

---

## 21. Recomendación para M03-E

**[DISEÑO]** M03-E (secuencia de jornada) hereda dos cosas concretas de este paso:

1. **Reprogramar deja huecos de `secuencia`.** Mover una OT de día no recompacta
   la secuencia del día origen ni inserta en el destino: la línea nueva nace con
   el `default` del modelo. **M03-E tendrá que decidir si se recompacta**, y es
   una decisión de negocio (¿la secuencia es un orden propuesto o un compromiso?).

2. **La invariante I-1 conviene llevarla a `revisar_coherencia`** (R-8): así
   publicar un plan detectaría una reprogramación mal hecha, en vez de esperar a
   que M09 lea la línea obsoleta.

**[RIESGO] Y un recordatorio que sigue vigente:** las 3 órdenes de producción
están **las tres con la vuelta actual iniciada**. Hoy, de las tres rutas, **solo
la contingencia tiene casos reales**.

---

```
código nuevo ... 1 archivo de pruebas + 4 modificados
migraciones .... 0     modelos .... 0     roles .... 0     tablas .... 0
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
