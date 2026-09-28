# M09-J — Asistentes operativos A-1 y A-2

**Fecha:** 2026-09-20

---

## 0. El hallazgo que cambia el encargo

**A-1 y A-2 ya estaban implementados.** No en el papel: en el código, con ruta,
pruebas y veredicto GO — es el bloque **M09-M**, cerrado el 19/09/2026.

Verificado leyendo la app real, no el informe:

```
operaciones/asistentes.py                     343 lineas   EXISTE
operaciones/tests/test_m09m_asistentes.py     684 lineas   EXISTE
operaciones/views.py::AsistenteView                        EXISTE
POST /api/operaciones/asistentes/                          DECLARADA
```

Así que este bloque **no reimplementa nada**. Mide el delta entre lo que existe
y lo que este encargo pide, e implementa sólo eso.

---

## 1. Qué ya existía, qué faltaba

| Lo que pide el encargo | Estado antes de este bloque |
|---|---|
| A-1 y A-2 en modo recomendación | **YA** — M09-M |
| OBSERVADO / INFERIDO / RECOMENDADO / DATOS_FALTANTES | **YA** — cuatro campos separados |
| `DATOS_INSUFICIENTES` sin propuesta | **YA** |
| Evidencia en toda recomendación | **YA** — CHECK en la base |
| Deduplicación de `PropuestaSupervisor` | **YA** — huella + `_ya_propuesta` |
| Revisión humana | **YA** — `requiere_revision_humana` |
| Habilidad bloqueada declarada | **YA** — H-05 se dice BLOQUEADA |
| Sin tablas/colas/entidades nuevas | **YA** |
| **A-2 distingue explícitamente los estados** | **FALTABA** — el estado sólo viajaba como texto dentro de la evidencia |
| **Ejecutado ≠ validado** | **FALTABA** — `resuelta` aplanaba los dos ejes |
| **Bloqueado ≠ no realizado** | **FALTABA** — la causa no llegaba a la salida |
| **A-1 expone jornada, secuencia, novedades** | **FALTABA** — `ProgramacionOrden` y `NovedadOperativa` se leían en el supervisor pero no llegaban al asistente |

### La decisión de negocio ya estaba tomada, y no la inventé

El encargo pide distinguir **ocho** estados. El modelo dice, donde los declara,
que **no son ocho**:

> `'validacion_pendiente' NO esta aca a proposito. "Completada" y "falta
> validarla" son dos ejes a la vez, no dos valores del mismo: con un solo eje
> hay que elegir, y se pierde poder decir "completada + requiere correccion",
> que es el caso real que la devolucion produce.`

Son **siete estados operativos + un eje de validación de seis valores**.
Aplanarlos a ocho habría sido inventar una decisión contraria a la que el
sistema ya tomó. La implementación devuelve los dos ejes por separado.

---

## 2. Qué se implementó

`operaciones/asistentes.py` — **343 → 480 líneas**. Tres funciones y dos
contadores. Ningún detector, ninguna habilidad, ningún modelo, ninguna ruta.

### `_estado_de(senal)` — los dos ejes de una actividad

```python
{"operativo": "bloqueada", "operativo_etiqueta": "Bloqueada",
 "validacion": "sin_evaluar", "validacion_etiqueta": "Sin evaluar",
 "es_final": False,
 "ejecutada": False,          # estado_operativo == COMPLETADA
 "validada": False,           # estado_validacion == APROBADO
 "validacion_pendiente": False,
 "motivo_bloqueo": "falta material en bodega"}
```

`ejecutada` y `validada` se contestan **por separado**: es la confusión que el
encargo nombra. `motivo_bloqueo` es lo que separa *"no se pudo, por esto"* de
*"no se hizo"*.

Las etiquetas salen de `models.ESTADOS_OPERATIVOS` y `ESTADOS_VALIDACION`, no de
un catálogo copiado — un segundo catálogo se desincroniza en silencio.

### `_contexto_operativo(senal)` — el plan vigente de una orden

```python
{"programacion": {"semana", "plan_estado", "plan_publicado",
                  "dia", "secuencia", "prioridad", "estado_linea"},
 "novedades": [{"tipo", "descripcion"}]}
```

Leído, no recalculado: si el plan dice secuencia 3, aquí dice 3. Un asistente
que recalcula el plan mientras lo describe deja de servir para contrastarlo.

Las novedades importan porque sin ellas *"sigue sin ejecutarse"* se lee como
desidia cuando puede ser una falta de material que alguien ya reportó.

### `_dependencias_de` — donde de verdad ocurre «ejecutado ≠ validado»

`resuelta` se dejó **como estaba**: es del eje operativo y está bien definido.
Al lado se agregó el otro eje:

```python
{"resuelta": True,              # dejo de avanzar
 "estado_validacion": "pendiente",
 "validada": False,
 "ejecutada_sin_validar": True} # todavia puede volver con requiere_correccion
```

### El resumen

`por_estado` (reparto por estado operativo) y
`dependencias_ejecutadas_sin_validar`.

> **Este segundo contador nació corregido.** Lo escribí primero sobre la
> actividad de la señal — y habría sido **siempre 0**: ningún detector de M09
> nace de una actividad completada, porque todos excluyen `ESTADOS_FINALES`. Un
> contador que nunca se enciende parece decir «no hay nada que mirar». Se mide
> sobre las **dependencias**, que es donde el caso ocurre de verdad.

---

## 3. Entregables

```
GO/NO-GO ................  GO
Archivos modificados ....  3
Modelos nuevos ..........  0        Migraciones nuevas: 0  ("No changes detected")
Rutas nuevas ............  0        (siguen 17)
Skills nuevas/modificadas  0        (siguen 14; H-05 sigue BLOQUEADA)
Entidades / colas nuevas   0        (siguen 6 modelos)
Pruebas propias .........  18 passed / 0 failed
Suite de asistentes .....  40 passed / 0 failed
Produccion ..............  SIN CAMBIOS
Commit / push ...........  NO
```

### Archivos

| Archivo | Cambio |
|---|---|
| `operaciones/asistentes.py` | +137 líneas: `_estado_de`, `_contexto_operativo`, `_por_estado`, dos campos en la recomendación, dos contadores |
| `operaciones/tests/test_m09j_estado_y_contexto.py` | **CREADO** — 541 líneas, 18 pruebas |
| `operaciones/tests/test_m09m_asistentes.py` | 1 línea: `test_14b` hecha determinista (§5) |

**Sin tocar:** `supervisor.py` · `habilidades.py` · `models.py` · `views.py` ·
`serializers.py` · `urls.py` · `capacidad.py` · `actividades.py` ·
`programacion.py` · M02 · M03 · kill switch · B-7.

La vista no filtra campos, así que los dos nuevos llegan a la API sin tocarla.

---

## 4. Pruebas propias — 18, todas en verde

| # | Prueba | Qué impide |
|---|---|---|
| 1 | `test_el_estado_viaja_en_dos_ejes_y_no_en_uno` | Que alguien aplane los ejes |
| 2 | `test_bloqueada_no_es_no_realizada` | Perder la causa |
| 3 | `test_los_estados_que_el_supervisor_ve_se_reportan_tal_cual` | Traducir o agrupar estados; el reparto cuadra con lo leído |
| 4 | `test_una_dependencia_completada_sin_validar_no_se_presenta_como_cerrada` | **La confusión central** |
| 5 | `test_validada_de_verdad_no_cuenta_como_pendiente` | Que el contador anterior esté siempre encendido |
| 6 | `test_una_devolucion_reabre_y_la_dependencia_deja_de_estar_resuelta` | Cachear `resuelta` |
| 7 | `test_el_plan_se_lee_no_se_recalcula` | Recalcular secuencia/prioridad |
| 8 | `test_el_contexto_llega_hasta_la_salida_del_asistente` | Inventar un plan que no existe |
| 9 | `test_una_orden_no_finge_tener_los_ejes_de_una_actividad` | Una forma común falsa |
| 10 | `test_si_la_fila_ya_no_existe_se_dice` | Callar lo que no se pudo leer |
| 11 | `test_el_contexto_nuevo_no_ejecuta_nada` | Escritura, medida sobre las 4 tablas que toca |
| 12 | `test_el_estado_no_se_cuela_entre_organizaciones` | Fuga entre tenants |
| 13 | `test_la_ruta_sigue_exigiendo_permiso` | Perder `EsJefeDeOperaciones` |
| 14 | `test_la_api_devuelve_los_campos_nuevos` | Que la vista los filtre |
| 15 | `test_datos_insuficientes_no_gana_una_recomendacion_por_traer_estado` | Que más campos vuelvan «suficiente» lo que no lo es |
| 16 | `test_la_deduplicacion_sigue_valiendo_con_los_campos_nuevos` | Romper la huella |
| 17 | `test_toda_recomendacion_sigue_llevando_evidencia_y_revision` | Evidencia o revisión perdidas |
| 18 | `test_no_se_importo_ningun_servicio_de_escritura_nuevo` | Un servicio de escritura por la puerta de atrás (**por AST**) |

La 18 se mide con AST, no con `in fuente`: los docstrings nombran justamente lo
que **no** se usa, y un `grep` los contaría como si existiera.

### Dos supuestos míos que la medición desmintió

1. **Escribí `test_una_devolucion...` esperando «completada + requiere
   corrección».** Falló. Medido en `actividades.py::validar`: una devolución
   **reabre** — vuelve a `EN_GESTION`, limpia `completado_en` y sube `vuelta`.
   El efecto real sobre la dependencia es el contrario del que supuse: **deja de
   estar resuelta**. La prueba quedó afirmando eso, que es más fuerte.
2. **Monté el caso del plan por el camino largo.** Una orden ya programada no
   dispara `orden_sin_programar`, y la señal de un plan en borrador es de la
   **semana**, no de la orden. Se prueba la función directamente, y la
   integración con una orden sin programar.

---

## 5. `[HALLAZGO]` Una prueba de M09-M fallaba un día de cada siete

`test_14b_una_pasada_no_ejecuta_nada` estaba en **rojo** al empezar este bloque.
No era una regresión: es sensible al día de la semana.

`_programar` agenda para **mañana**, y `programacion_sin_publicar` exige
`semana_inicio <= hoy`. En **domingo**, mañana es lunes y el plan cae en una
semana que todavía no empezó:

```
hoy=lunes..sabado -> semana_inicio=lunes de esta semana -> dispara     (6 de 7)
hoy=DOMINGO       -> semana_inicio=lunes que viene      -> NO dispara  (1 de 7)
```

Medido, no supuesto: el contenedor corre en `TIME_ZONE="UTC"` y era domingo
20/09. M09-M la corrió en sábado, y por eso reportó 22 en verde.

**Arreglo: una línea en la prueba, ninguna en el código.** Se le pasa un día de
esta semana, cuyo lunes siempre es `<= hoy`. El comportamiento del sistema no se
tocó — la prueba pasa a afirmar lo mismo los siete días.

---

## 6. Qué puede detectar A-1 (Programación)

Sobre `OrdenTrabajo`, `ProgramacionSemanal`, `ProgramacionOrden`,
`AsignacionTrabajo`, `WorkTypeVersion` y `NovedadOperativa`:

- órdenes **sin programar** (H-03);
- planes de una semana ya empezada que **siguen en borrador** (H-04);
- órdenes **con riesgo operacional** — declarando que H-05 está **BLOQUEADA**;
- **datos incompletos** que impiden calcular capacidad (H-02): sin fecha, sin
  cuadrilla, sin duración estimada — nombrando el campo y la orden;
- **exceso de carga de jornada**, consumiendo M03-G sin recalcularlo, y
  diciendo cuándo la carga conocida es una **cota inferior**;
- y ahora, para cada una: **jornada, día, secuencia, prioridad, estado de la
  línea, si el plan está publicado, y las novedades registradas**.

## 7. Qué puede detectar A-2 (Compromisos)

Sobre `ActividadOperativa`:

- actividades **vencidas** (H-06) y **compromisos por vencer** (H-09);
- actividades **sin responsable** (H-07);
- actividades **bloqueadas** (H-08), **con su causa**;
- **dependencias pendientes** (H-10), y si la previa está **ejecutada pero sin
  validar** o fue **devuelta**;
- el **estado en sus dos ejes**, con etiqueta, y el reparto por estado;
- qué **no se sabe** de cada actividad: sin responsable, sin fecha comprometida,
  bloqueada sin causa, completada sin que nadie resolviera su validación.

## 8. Qué NO puede hacer ninguno de los dos

- **No ejecuta.** No programa, no asigna, no reprograma, no completa, no cancela,
  no bloquea, no valida, no escala. No importa ni un servicio de escritura
  operativa — verificado por AST, no por lectura del texto.
- No modifica `Case`, `OrdenTrabajo`, programación, actividades ni asignaciones.
- No cambia SLA ni prioridades: las **lee**.
- No aprueba sus propias propuestas ni sube su nivel de autonomía.
- No llama a ningún sistema externo.
- No crea tablas, colas, entidades, skills ni `Task`.
- No usa `common.Activity` como agenda.
- **No inventa**: sin análisis, `DATOS_INSUFICIENTES` y ninguna propuesta.
- No se salta una habilidad bloqueada: H-05 sigue corriendo y su recomendación
  viaja **marcada como no plenamente defendible**.
- No cubre el dominio de **Casos** (H-01, `caso_abierto_antiguo`): ningún
  asistente lo reclama, y no se le asignó a ninguno por conveniencia.

---

## 9. Decisiones de negocio pendientes

**Ninguna bloqueó esta implementación.** La única que podría haber hecho falta
—si `validacion_pendiente` es un octavo estado o un eje aparte— ya estaba
resuelta y documentada en el modelo, y se respetó.

Queda una **observación**, no una decisión que yo deba tomar:

> `_dependencias_de` sigue devolviendo `resuelta = True` para una dependencia
> completada y **sin validar**. Es correcto en el eje operativo, y ahora se dice
> al lado que no está validada. Si el negocio decide que una dependencia sin
> validar **no habilita** a la siguiente, eso cambia el detector H-10 — no el
> asistente — y es una decisión tuya, no mía.

---

## 10. Producción

# SIN CAMBIOS

Leído con `transaction_read_only = on` verificado en el servidor, al cerrar:

```
migraciones aplicadas : 192      tablas en public : 135
roles                 : 41       FORCE RLS        : 66
por app: campo 3 · common 39 · operaciones 2
```

Idéntico a antes del bloque. **No se ejecutaron migraciones de producción, no se
cambiaron roles, permisos, RLS ni credenciales, no se tocó B-7.** Todo el
trabajo corrió en el entorno aislado (`pg-b7`, contenedor efímero con el código
montado).

**No se hizo commit ni push.**
