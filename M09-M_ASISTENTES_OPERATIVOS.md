# M09-M — Asistentes operativos de Programación y Compromisos

**Fecha:** 2026-09-19
**Veredicto:** **M09-M = GO**

---

## 1. GO / NO-GO

# GO

| # | Criterio de cierre (§L) | |
|:--:|---|:--:|
| 1 | Ambos asistentes funcionan en modo recomendación | **SÍ** |
| 2 | Reutilizan M02 / M03 / M09 | **SÍ** — 0 detectores nuevos |
| 3 | Generan `PropuestaSupervisor` cuando corresponde | **SÍ** |
| 4 | **No** generan propuesta cuando faltan datos | **SÍ** — probado desarmando el análisis |
| 5 | No crean segunda cola | **SÍ** |
| 6 | No crean `Task` | **SÍ** |
| 7 | 0 efectos externos | **SÍ** — espía probado |
| 8 | Respetan el kill switch | **SÍ** — no hay nada que apagar (§11) |
| 9 | Tenant isolation | **SÍ** |
| 10 | Deduplicación / concurrencia protegidas | **SÍ** |
| 11 | Evidencia trazable | **SÍ** |
| 12 | Revisión humana obligatoria | **SÍ** |
| 13 | Regresión ejecutada | **SÍ** — 4417 passed |
| 14 | Producción intacta | **SÍ** |

```
Pruebas propias ....  22 passed / 0 failed / 0 skipped
Regresion ..........  4417 passed / 1 failed / 19 skipped
Migraciones ........  0        Modelos: 0        Habilidades nuevas: 0
Rutas nuevas .......  1        Entidades nuevas: 0     Colas nuevas: 0
Efectos externos ...  0        Produccion: SIN CAMBIOS
Commit .............  no
```

---

## 2. Archivos modificados

| Archivo | Cambio |
|---|---|
| `operaciones/asistentes.py` | **CREADO** — 343 líneas, los dos asistentes |
| `operaciones/tests/test_m09m_asistentes.py` | **CREADO** — 684 líneas, 22 pruebas |
| `operaciones/views.py` | +1 vista `AsistenteView` |
| `operaciones/serializers.py` | +1 `AsistenteSerializer` |
| `operaciones/urls.py` | +1 ruta |
| `operaciones/tests/test_m09f_gobernanza.py` | +1 ruta declarada, **con su justificación** |

**Sin tocar:** `supervisor.py` · `habilidades.py` · `capacidad.py` ·
`actividades.py` · `programacion.py` · `models.py` · M02 · M03 · kill switch ·
B-7.

---

## 3. Modelos

# 0 creados · 0 modificados

Verificado leyendo la app real:

```python
{"ActividadOperativa", "DisponibilidadTecnico", "ProgramacionSemanal",
 "ProgramacionOrden", "NovedadOperativa", "PropuestaSupervisor"}
```

Sin `AssistantTask`, `AIRecommendation`, `AssistantQueue` ni `Task`.

---

## 4. Migraciones

```
makemigrations --check  ->  "No changes detected"
```

# 0

Los asistentes son una capa de lectura y recomendación sobre estructuras que ya
existían.

---

## 5. Rutas

```
POST /api/operaciones/asistentes/     {"dominio": "programacion" | "compromiso"}
```

**Una sola**, declarada en el guarda de gobernanza con su justificación.

**El dominio va en el CUERPO, no en la ruta.** La primera versión usaba
`asistentes/<str:dominio>/` y el guarda `test_malformed_id_routes` la rechazó:
existe para que ningún parámetro de ruta llegue crudo al ORM, y tiene una lista
blanca (`token`, `pack_id`) para lo que legítimamente no es UUID.

**No pedí la excepción.** Quité el parámetro de la ruta y lo pasé al cuerpo con
un `ChoiceField`: el catálogo se valida en DRF, un dominio inventado responde
**400**, y **no se tocó un guarda ajeno**.

---

## 6. Habilidades reutilizadas

**Las 14 siguen siendo 14.** Ninguna creada, ninguna modificada, ninguna huella
alterada.

| Asistente | Habilidades | Estado |
|---|---|---|
| **Programación** | H-03 `orden_sin_programar` · H-04 `programacion_sin_publicar` · H-02 `dato_incompleto` | VIGENTE |
| | **H-05** `orden_con_riesgo_operacional` | **BLOQUEADA** |
| **Compromisos** | H-06 `actividad_vencida` · H-07 `actividad_sin_responsable` · H-08 `actividad_bloqueada` · H-09 `compromiso_por_vencer` · H-10 `dependencia_pendiente` | VIGENTE |

`caso_abierto_antiguo` (H-01) no está en ninguno: es del dominio de Casos, y
este bloque no lo cubre.

### El hallazgo de §D, aplicado

**Cada recomendación declara con qué habilidad se sostiene Y en qué estado
está.** No es decoración: **H-05 está BLOQUEADA desde M09-J y su detector sigue
corriendo**, así que hay recomendaciones vivas apoyadas en una ficha que el
propio sistema marcó como todavía no confiable. Callarlo sería presentar como
firme algo que no lo es.

Cuando la ficha está bloqueada, el riesgo se **dice**:

> *"La habilidad que sustenta esta señal (H-05) está BLOQUEADA: su
> recomendación todavía no es plenamente defendible."*

Y el resumen lo cuenta: `con_habilidad_bloqueada`.

---

## 7. Habilidades nuevas

# 0

§D lo prohíbe y la lección de M09-L con H-05 se respetó: **una capacidad
técnica disponible no implica una habilidad autorizada.**

---

## 8. Flujo de cada asistente

```
supervisor.detectar(org)          <- los detectores QUE YA EXISTIAN
        |
        v  filtrado por dominio
   senales del dominio
        |
        +--> supervisor.analizar(senal)
        |         |
        |         +-- {}  --> DATOS_INSUFICIENTES, y NO se crea propuesta
        |         |
        |         +-- analisis
        |               |
        |               +--> supervisor._ya_propuesta()  --> REPETIDA
        |               |
        |               +--> supervisor.registrar_propuesta()  --> PROPUESTA
        v
  recomendacion estructurada
        |
        v
  PropuestaSupervisor  ->  revision humana  (Jefe de Operaciones)
```

**Sin camino propio de creación**: el registrador, la deduplicación, la
expiración y la auditoría son los de siempre.

### La forma estructurada: cuatro cosas separadas

Hasta ahora viajaban mezcladas en un párrafo. El asistente las distingue:

| Campo | Qué es |
|---|---|
| `observado` / `hallazgo` | **El hecho**, literal, tal como quedó en la evidencia |
| `inferencia` | **Lo que el análisis deduce** de ese hecho |
| `recomendacion` | **Lo que se propone hacer** |
| `datos_faltantes` | **Lo que NO se sabe**, nombrado campo por campo |

Más `riesgos`, `dependencias`, `habilidad` (con estado), `prioridad`,
`evidencia`, `requiere_revision_humana` y `propuesta_id`.

**`datos_faltantes` se MIDE sobre la fila**, no se deduce de una plantilla: se
lee qué campo está en null y por qué importa. Una actividad sin responsable y
sin fecha declara las dos cosas; una orden sin cuadrilla y sin duración
también.

**Cuando el resultado es `DATOS_INSUFICIENTES`, `recomendacion` e `inferencia`
quedan VACÍAS.** No se rellenan con una frase genérica que parecería un
consejo. Lo observado sí se conserva: el hecho ocurrió.

---

## 9. Pruebas propias

```
22 passed / 0 failed / 0 skipped
```

Las 18 de §I más 4 de contrato. Las que más pesan:

| Prueba | Qué demuestra |
|---|---|
| `test_2b` | Sin análisis → `DATOS_INSUFICIENTES` y **0 propuestas**. Probado **desarmando** `analizar`: sin eso la prueba no sabría fallar |
| `test_4` | Capacidad indeterminada **no** se vuelve cero; se nombran las OT sin duración y **ninguna** recomendación afirma que la jornada quepa |
| `test_14` | El módulo **no tiene con qué ejecutar** — verificado sobre el **AST**, no sobre el texto |
| `test_14b` | Una pasada completa no cambia **nada**: 6 conjuntos de datos operativos idénticos |
| `test_12` | Dos asistentes simultáneos **no** duplican |
| `test_17_18` | Ni segunda cola ni `Task` — leyendo la app real y el AST |
| `test_habilidades` | Siguen siendo 14; H-05 sigue BLOQUEADA y su riesgo se declara |
| `test_9` | Sin responsable: se nombra el dato faltante y **no se inventa a quién asignárselo** |

**Una corrección durante el trabajo:** `test_17_18` comparaba texto del archivo
y encontraba `AssistantTask` **en el docstring** que explica que no se creó. Se
rehízo sobre el **AST** — identificadores realmente usados — porque una
aserción que confunde un comentario con código no prueba lo que dice probar.

---

## 10. Regresión completa

```
4417 passed · 1 failed · 19 skipped        (19m 06s)
```

| Cat. | Fallo | |
|:--:|---|---|
| **FAIL REAL (por M09-M)** | `test_malformed_id_routes` · `test_m09f_gobernanza` | **2, RESUELTOS sin relajar nada** |
| **FAIL PREEXISTENTE** | — | 0 |
| **BLOCKED POR ENTORNO** | `test_portal_rls` | **1** |

- **Gobernanza de rutas**: se declaró `asistente` en el inventario con su
  justificación, como hicieron E4, E5-B, G, M02 y L.
- **Rutas malformadas**: se quitó el parámetro de la ruta en vez de pedir una
  excepción en la lista blanca (§5).
- **`test_portal_rls`**: `postgres_only`, exige rol no-superusuario y
  `crm.test_settings_postgres`; bajo esa configuración da 2 passed (probado en
  M03-F-B, M03-G y M02).

**Ningún test histórico se modificó** salvo el inventario de gobernanza, que es
el mecanismo previsto para declarar una ruta.

---

## 11. Seguridad

| Verificación | Resultado |
|---|---|
| Un asistente de A no ve ni escribe en B | **sí** — `PropuestaSupervisor` de B queda en 0 |
| Técnico corre el asistente | **403** |
| Técnico revisa una propuesta | **403** |
| Se serializa por organización | **sí** |

**El kill switch y por qué no se consulta.** El interruptor de autonomía vive
en el motor (`nucleo/seguridad/interruptor.py`), no en Django — lo declara el
propio `habilidades.py`. La pregunta correcta no es si algo apaga al asistente,
sino **si hay algo que apagar**, y la respuesta está verificada sobre el AST:
`asistentes.py` **no usa** `programar_orden`, `reprogramar_orden`, `asignar`,
`agregar_integrante`, `cambiar_principal`, `retirar_integrante`, `desasignar`,
`completar`, `cancelar`, `bloquear`, `validar`, `crear`, `requests`, `httpx`,
`urllib`, `celery` ni `apply_async`. Tampoco `revisar` ni `ACEPTADA`: **no
puede aprobar sus propias propuestas**.

**Sin afirmar aislamiento de base donde no lo hay:** `operaciones_*` tiene RLS
forzada; `campo_*` no — ahí el aislamiento es aplicativo, y este bloque no lo
cambia.

---

## 12. Concurrencia

El asistente **es** una frontera nueva de creación de propuestas, así que §H
exigía medirla. Se reutiliza el lock de organización de M09-L —
`select_for_update` sobre la fila de `Org`— **sin mecanismo paralelo**.

**[MEDIDO]** Dos asistentes simultáneos sobre la misma organización: **0
duplicados** por `(tipo_senal, origen_id, huella_condicion)`.

Y comprobado que asistente y ciclo **comparten** el registrador: correr el ciclo
después del asistente no duplica nada.

---

## 13. Producción

# SIN CAMBIOS

Solo `SELECT`, `read_only = True`. **20 claves → DIFERENCIAS: NINGUNA.**

**Esta vez el invariante es el correcto.** §K advierte que `common.Activity` es
una tabla viva y no sirve como única prueba de integridad — en M09-L subió de
610 a 612 por un caso de cliente del CRM real. Se reemplazó por el conteo que
sí es específico:

```
activity WHERE entity_type IN ('ActividadOperativa','PropuestaSupervisor') = 0
```

Cero filas de las entidades de estos módulos. Nada de lo construido escribió en
producción.

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
ActividadOperativa 0 · PropuestaSupervisor 0 · acciones_propuestas 40
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
teams 0 · Disponibilidad 0 · operaciones_externas 0 · MutacionIdempotente 14
BusinessCalendar 1 · kill switch detenido
```

Ni `migrate`, ni `seed`, ni `INSERT`/`UPDATE`/`DELETE`/`ALTER`. Todo el trabajo
en contenedores aislados **sin una sola credencial de producción**.

---

## 14. Deuda técnica

| # | Deuda |
|:--:|---|
| 1 | **H-05 BLOQUEADA** — las recomendaciones de riesgo operacional se emiten con la ficha bloqueada. Ahora al menos se **declara** |
| 2 | **`caso_abierto_antiguo` sin asistente** — es del dominio de Casos; no se le inventó uno |
| 3 | **Sin señal de sobrecarga** (viene de M09-L) — se observa en el ciclo, no se propone |
| 4 | **Duración por tipo de trabajo sin declarar** en producción: toda jornada real dará `DATOS_PARCIALES` |
| 5 | **`idx_propuesta_dedup` no es único**: la serialización la da el lock, no la base |
| 6 | **Sin scheduler**: los asistentes son manuales, y es deliberado |
| 7 | RLS de `campo_*` · B-7 · punto ciego de H-05 sobre cuadrillas · zona · vehículo · autonomía 2+ |

---

## 15. Decisiones pendientes

**Ninguna bloqueó este paso.** Las que siguen abiertas vienen de antes y no se
tocaron:

1. **¿Se desbloquea H-05?** (de M09-L). M03-G ya aportó la definición medible
   de capacidad que su ficha declaraba faltante. Mientras tanto: sus
   recomendaciones salen marcadas como apoyadas en ficha bloqueada, y la
   sobrecarga se observa sin proponerse.
2. **¿Se declara la duración por tipo de trabajo en producción?** Exige
   publicar una v2 del `WorkTypeVersion` — acción operativa del negocio, no
   migración.
3. **¿Se autoriza una habilidad para `jornada_sobrecargada`?** Es la que
   convertiría la observación de sobrecarga en recomendación.

---

## 16. Conclusión ejecutiva

Los dos asistentes funcionan **sin agregar un solo sistema**: cero entidades,
cero modelos, cero migraciones, cero colas, cero detectores, cero habilidades.
Una ruta y un módulo de 343 líneas que **recorta** las señales que ya existían
por dominio y las presenta separando lo observado, lo inferido, lo recomendado
y **lo que falta**.

Lo que aportan de nuevo es precisamente eso último. Un asistente que calla lo
que no sabe produce una recomendación que parece completa; aquí los datos que
faltan se **miden** sobre la fila y se nombran campo por campo, y cuando el
análisis no alcanza el resultado es `DATOS_INSUFICIENTES` **sin crear
propuesta** — una propuesta sin base es peor que ninguna.

Y aportan una segunda cosa que no estaba: **cada recomendación dice con qué
habilidad se sostiene y en qué estado está esa habilidad**. H-05 lleva
bloqueada desde M09-J con su detector corriendo; hasta hoy, quien leía esas
recomendaciones no tenía cómo saberlo.

Dos guardas ajenos detectaron mi trabajo y **ninguno se relajó**: uno se
resolvió declarando la ruta, el otro quitando el parámetro de la ruta en vez de
pedir una excepción.

```
codigo ......... 1 archivo creado (343) · 4 modificados
pruebas ........ 1 archivo creado (22 pruebas, 684 lineas)
migraciones .... 0   modelos ... 0   habilidades ... 0   colas ... 0   entidades ... 0
M02 · M03 · supervisor.py · habilidades.py · kill switch ....... sin tocar
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no      despliegue ... no      M10/M11/autonomia ... no
```
