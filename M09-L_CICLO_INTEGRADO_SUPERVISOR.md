# M09-L — Ciclo integrado del Supervisor NOC IA

**Fecha:** 2026-09-19
**Veredicto:** **M09-L = GO** — con una pieza deliberadamente **no** entregada y su decisión al final (§W)

```
Pruebas propias ........  21 passed / 0 failed / 0 skipped
Regresion completa .....  4395 passed / 1 failed / 19 skipped
  el unico fallo ....... CATEGORIA C (entorno), ya probado en F-B, M03-G y M02
Migraciones ............  0        makemigrations --check: "No changes detected"
Modelos nuevos .........  0        Entidades nuevas: 0     Rutas nuevas: 0
Habilidades nuevas .....  0        (siguen siendo 14)
Efectos externos .......  0        (espia probado que dispara primero)
Produccion .............  SIN CAMBIOS por M09-L -- ver §T
Commit .................  no
```

---

## A. Auditoría mínima

**El ciclo ya existía, y ya integraba M02 y M03.** `supervisor.correr_ciclo`
hacía: expirar → detectar → deduplicar → analizar → registrar. Con **10
detectores**, cinco de M02 y cuatro de M03.

| | [MEDIDO] |
|---|---|
| `detectar()` | 10 detectores ya encadenados |
| `PropuestaSupervisor` | 10 tipos de señal, evidencia obligatoria con CHECK en base |
| `_ya_propuesta` | deduplicación por `(org, tipo, origen, huella, estado)` |
| `registrar_propuesta` | exige evidencia y análisis; audita con `actor=None` (la IA) |
| `CicloSupervisorView` | ruta manual, sin scheduler |
| `habilidades` | 14 fichas; `referencia_de` devuelve `""` para señal sin ficha |
| Revisión humana | `RevisarPropuestaView`, rol `EsJefeDeOperaciones` |

**Lo que faltaba, y es el trabajo de este paso:**

1. **La capacidad de M03-G no llegaba al ciclo** — cerró después.
2. **El resultado eran solo contadores**: §12 pide RESUMEN **y** DETALLE.
3. **Dos ciclos simultáneos duplicaban propuestas** — medido, no supuesto.

---

## B. Arquitectura integrada

```
M02  ActividadOperativa ──┐
                          │   5 detectores  (ya existian)
M03  OrdenTrabajo         ├──> detectar() ──> _ya_propuesta ──> analizar
     ProgramacionSemanal  │        │              (dedup)          │
     ProgramacionOrden    │        │                               v
     DisponibilidadTecnico│        │                    registrar_propuesta
     capacidad (M03-G) ───┘        │                               │
                                   │                               v
                                   │                     PropuestaSupervisor
                                   │                               │
                                   └─> observar_capacidad          v
                                        (lectura, NO propone)  revision humana
```

**Nada nuevo se creó**: ni CRM, ni motor de tareas, ni cola, ni entidad
Supervisor, ni segundo ciclo, ni tabla de propuestas.

---

## C. El ciclo

```
LECTURA -> DETECCION -> CONSOLIDACION -> PRIORIZACION -> PROPUESTA
```

**Sin ejecución autónoma.** Lo único que el ciclo escribe son filas de
`PropuestaSupervisor` y su auditoría — verificado midiendo **todo** lo que
podría tocar (§R, `test_20`).

**El ciclo se serializa por organización** (ver §I).

---

## D. Detectores utilizados

Los 10 que ya existían, **reutilizados sin tocar**, más 1 nuevo que consume
M03-G:

| Origen | Detector | Señal |
|---|---|---|
| Casos | `_casos_abiertos_antiguos` | `caso_abierto_antiguo` |
| **M02** | `_actividades_vencidas` | `actividad_vencida` |
| **M02** | `_actividades_sin_responsable` | `actividad_sin_responsable` |
| **M02** | `_actividades_bloqueadas` | `actividad_bloqueada` |
| **M02** | `_compromisos_por_vencer` | `compromiso_por_vencer` |
| **M02** | `_dependencias_pendientes` | `dependencia_pendiente` |
| **M03** | `_ordenes_sin_programar` | `orden_sin_programar` |
| **M03** | `_ordenes_desincronizadas` | `dato_incompleto` |
| **M03** | `_programaciones_sin_publicar` | `programacion_sin_publicar` |
| **M03** | `_ordenes_en_riesgo` | `orden_con_riesgo_operacional` |
| **M03-G** | `_capacidad_de_jornada` | `dato_incompleto` ← **nuevo** |

**Ningún detector paralelo.** El nuevo **no recalcula capacidad**: llama a
`operaciones.capacidad`, la única fuente.

---

## E. Señales M02

Las cinco llegan al ciclo con datos reales, verificado creando la situación de
cada una y midiendo que `detectar()` las emite (`test_2`). M02 **no se
modificó**: el ciclo solo lee.

---

## F. Señales M03

Las cuatro previas, más la capacidad. **No se fabrican datos**: sin calendario,
sin órdenes programadas o sin duraciones, no se emite una señal inventada — se
emite la que corresponde, o ninguna.

---

## G. Capacidad — y la pieza que no se entregó

### G.1 Lo que sí entra al ciclo

**Cuando falta la duración** → `dato_incompleto`, nombrando las OT concretas:

> *"La jornada del 2026-09-20 de Carlos no se puede evaluar: #3012, #3013 no
> tienen duración estimada. La carga calculada es una **COTA INFERIOR**, no el
> total, así que no se puede afirmar que la jornada quepa. No se supone ninguna
> duración."*

Es exactamente lo que §6 autoriza decir, y encaja sin forzar nada:
`dato_incompleto` es *"un objeto concreto con un campo concreto que falta y se
puede nombrar"* — su propia definición.

**Cuando hay sobrecarga demostrable** → aparece en `resumen["capacidad"]`
con día, persona, capacidad, carga, exceso y si el exceso es una cota inferior.

### G.2 Por qué la sobrecarga se OBSERVA y no se PROPONE

**[MEDIDO] El propio módulo ya había cerrado esta puerta, y por una razón que
sigue siendo válida.** La habilidad **H-05** existe, se llama *"Estimar riesgo
operacional de una orden por capacidad"*, y está **`estado=BLOQUEADA`**:

> *"BLOQUEADA POR D-4: no existe una definición medible de capacidad operativa,
> y M09-J decidió no inventarla."*
>
> *"Sin definición de capacidad, cualquier umbral sería arbitrario y la señal
> no sería defendible ante quien la reciba."*

Y el guarda de M09-K es explícito: **"Ninguna señal puede quedar sin habilidad
que la explique."**

**M03-G levantó la mitad de ese bloqueo**: la capacidad ya es medible y
**derivada**, no inferida. La otra mitad sigue en pie — ninguna habilidad
explica una señal de sobrecarga.

Emitir la propuesta exigía una de dos cosas, y **el encargo prohíbe ambas**:

| Camino | Lo prohíbe |
|---|---|
| Crear una habilidad para la señal nueva | **§14** — *"No crear nuevas habilidades"* |
| Aflojar el guarda de M09-K | **§22** *"No relajar tests"* · **§23** *"No eliminar guardas existentes"* |

**Se eligió no hacer ninguna de las dos.** La sobrecarga se ve en el resumen,
con la razón escrita en la propia respuesta:

```jsonc
"capacidad": {
  "jornadas_sobrecargadas": [
    {"dia": "2026-09-20", "persona": "Carlos", "capacidad_minutos": 480,
     "carga_minutos": 560, "exceso_minutos": 80, "es_cota_inferior": false}
  ],
  "jornadas_no_determinables": [],
  "nota": "La sobrecarga se OBSERVA y no se propone: H-05 está BLOQUEADA y
           ninguna habilidad explica todavía esa señal. M03-G ya aportó la
           definición medible de capacidad que su ficha declaraba faltante;
           desbloquearla es una decisión pendiente."
}
```

**Callarla habría sido peor**: el dato existe, es defendible y quien revisa el
ciclo tiene que poder mirarlo. Lo que no se hace es convertirlo en una
recomendación que el sistema todavía no puede justificar.

### G.3 Respeto de INDETERMINADO

**[MEDIDO]** La asimetría de M03-G se hereda intacta:

| Datos | ¿Se observa sobrecarga? |
|---|---|
| Completos, carga > capacidad | **sí** |
| Parciales, lo conocido ya no cabe | **sí**, marcado `es_cota_inferior: true` |
| Parciales, lo conocido cabe | **no** — y se propone `dato_incompleto` |
| Sin jornada | **no** — aparece en `jornadas_no_determinables` |

Probado en las dos direcciones (`test_6` y `test_6b`).

---

## H. Propuestas

`PropuestaSupervisor`, **sin segunda tabla**. Cada una expresa qué ocurre, qué
se recomienda, por qué, con qué evidencia, prioridad, impacto y nivel de
autonomía requerido.

**No existe ningún `ejecutada=true`** ni equivalente — verificado.

---

## I. Deduplicación — y un defecto real encontrado

Se reutiliza `_ya_propuesta`: `(org, tipo, origen_tipo, origen_id, huella,
estado ∈ ESTADOS_QUE_BLOQUEAN)`. Una decisión tomada no se vuelve a preguntar;
una condición **distinta** sí.

**[RIESGO → CORREGIDO] Dos ciclos simultáneos dejaban propuestas duplicadas.**
Medido, no supuesto:

```
dos ciclos simultaneos -> {('programacion_sin_publicar', ..., 'semana:2026-09-14'): 2,
                           ('jornada_sobrecargada',      ..., 'sobrecarga:2026-09-20'): 2}
```

**Causa:** la deduplicación es *leer* y después *escribir*, y entre las dos
cosas cabe otro ciclo entero. El índice `idx_propuesta_dedup` acelera la
consulta pero **no es único**, así que la base no lo impedía.

**Corrección, sin mecanismo nuevo:** se bloquea la fila de la **organización**,
que ya existe — mismo patrón que `programar_orden` en M03. Sin tabla de locks,
sin migración, sin advisory locks.

**[RIESGO] Consecuencia que hay que saber:** el ciclo pasa a ser **una
transacción**. Si falla a la mitad no quedan propuestas a medias — antes
quedaban las de las señales ya procesadas. Para un ciclo manual que se puede
volver a correr, todo-o-nada es más fácil de explicar que un resultado parcial
silencioso. **Es un cambio de alcance transaccional en un módulo ya cerrado, y
por eso queda dicho aquí y en el código.**

---

## J. Evidencia

Obligatoria, en dos capas que ya existían: el servicio levanta
`ValueError` si falta, y la base tiene `propuesta_exige_evidencia`.

**Nunca se genera causa, responsable, incumplimiento ni resultado inventado.**
Cuando la evidencia es insuficiente, la propuesta **lo dice**: eso es
literalmente lo que hace la señal `dato_incompleto` de capacidad.

---

## K. Revisión humana

El mecanismo existente, sin rol nuevo: `EsJefeDeOperaciones`. Verificado que
el Jefe revisa (queda `revisado_por`, `revisado_en`, estado) y que un técnico
recibe **403**.

---

## L. Habilidades

**Siguen siendo 14.** No se creó ninguna, no se modificó ninguna, y ninguna
huella cambió.

**[MEDIDO]** Toda propuesta que el ciclo emite tiene ficha:
`prop.tipo_senal in habilidades.POR_SENAL` y
`conocimiento_version` empieza por `"habilidad:"` — comprobado sobre lo que el
ciclo produce de verdad, no sobre la tabla de fichas.

H-05 **sigue BLOQUEADA**, y la prueba lo afirma: desbloquearla es una decisión,
no un efecto lateral de este paso.

---

## M. Conocimiento

**No se creó documentación nueva.** No se presentó ninguna inferencia como
conocimiento. `referencia_de` sigue distinguiendo `habilidad:` de
`conocimiento:`, y solo agrega la segunda mitad donde el documento existe.

---

## N. Autonomía

**NIVEL 1, sin moverse.** Toda propuesta emitida tiene
`nivel_autonomia_requerido <= NIVEL_RECOMENDAR` y `estado = PROPUESTA` —
verificado sobre las propuestas reales.

El kill switch no se tocó. No se implementó autonomía 2+.

**La prioridad NO autoriza ejecutar**: son ejes separados, y la prueba lo
afirma.

---

## O. Seguridad

| Verificación | Resultado |
|---|---|
| Un ciclo de A no escribe en B | **sí** — `PropuestaSupervisor` de B queda en 0 |
| El resumen identifica su organización | **sí** |
| Ningún `origen_id` de otro tenant en el detalle | **sí** |
| Técnico no corre el ciclo | **403** |

**Sin afirmar aislamiento de base donde no lo hay:** `operaciones_actividad`,
`operaciones_propuesta_supervisor` y las demás tablas de `operaciones` **sí**
tienen RLS (forzada, medido en M02). Las `campo_*` **no** — ahí el aislamiento
es aplicativo, y este paso no lo cambia.

---

## P. Endpoints

# 0 rutas nuevas

Se reutiliza `POST /api/operaciones/supervisor/ciclo/`, que ya existía. §11 lo
pedía explícitamente y una prueba lo afirma: **hay exactamente un ciclo**
(`test_api_no_hay_segundo_ciclo`).

Su respuesta se **enriqueció** (aditivo, ninguna clave cambió de significado).

**No hizo falta tocar el guarda de gobernanza de rutas** — no hay ruta nueva
que declarar.

---

## Q. Migraciones

```
makemigrations --check  ->  "No changes detected"
```

# 0

Se llegó a generar una (`0006_m09l_jornada_sobrecargada`, un `AlterField` de
choices para la señal de sobrecarga) y **se eliminó** junto con el tipo de
señal, al concluir que la propuesta de sobrecarga no podía emitirse todavía
(§G.2). No queda rastro.

---

## R. Pruebas

```
21 passed / 0 failed / 0 skipped
```

Las 23 ejecutables de §21 (las tres de regresión van en §S). Las que más pesan:

| Prueba | Qué demuestra |
|---|---|
| `test_5` | La sobrecarga se **observa** con sus números exactos y **no** genera propuesta |
| `test_6` | Con duraciones faltantes **no** se afirma sobrecarga; se propone `dato_incompleto` |
| `test_6b` | Con datos parciales, si lo conocido no cabe, **sí** se observa, marcado como cota |
| `test_18` | Dos ciclos simultáneos **no** dejan duplicados |
| `test_20` | El ciclo **no ejecuta**: 6 conjuntos de datos operativos idénticos antes y después |
| `test_21_22` | Siguen siendo 14 habilidades; toda señal emitida tiene ficha; H-05 sigue bloqueada |
| `test_19` | 0 llamadas externas, con el espía probado antes |
| `test_9_10_11` | Dedup: repetida, rechazada con misma evidencia, y vuelve con evidencia nueva |

---

## S. Regresión

```
4395 passed · 1 failed · 19 skipped        (19m 13s)
```

| Cat. | Fallo | |
|:--:|---|---|
| **A** (por M09-L) | `test_m09k_habilidades::test_las_diez_senales_del_modelo_tienen_ficha` | **RESUELTO sin relajar nada** |
| **B** (preexistente) | — | 0 |
| **C** (entorno) | `test_portal_rls` | **1** |
| **D** (test incorrecto) | — | 0 |

**El fallo A fue el guarda de habilidades haciendo su trabajo**, y es el que
llevó al hallazgo de §G.2. **No se relajó**: se retiró el tipo de señal nuevo
y su migración, y la sobrecarga pasó a observarse en vez de proponerse. El
guarda quedó intacto — 144 pruebas de habilidades en verde.

**El fallo C** es el de siempre: `postgres_only`, exige rol no-superusuario y
`crm.test_settings_postgres`; bajo esa configuración da 2 passed (probado en
M03-F-B y M03-G).

---

## T. Producción

# SIN CAMBIOS POR M09-L

Solo `SELECT`, `read_only = True`. De 20 claves, **19 idénticas**. La vigésima
se movió y **hay que explicarla con precisión**:

```
Activity: 610 -> 612
```

**[MEDIDO] No fue M09-L.** Las dos filas nuevas son:

```
2026-09-19 02:16:14  CREATE  Case  "Consulta - MARIO SABANAGRANDE - #d303f332"
2026-09-19 02:16:14  ASSIGN  Case  "Consulta - MARIO SABANAGRANDE - #d303f332"
```

Un **caso de cliente** creado y asignado por el CRM vivo, 23 minutos antes de
la medición. Y la comprobación que lo cierra:

```
filas de activity con entity_type en (ActividadOperativa, PropuestaSupervisor): 0
```

Nada de lo que M02 o M09-L construyen escribió una sola fila en producción.
Todo el trabajo corrió en contenedores aislados **sin una sola credencial de
producción**, y las conexiones a producción fueron `read_only = True`.

**Lección para las próximas fotos:** `activity` es un contador **vivo** — el
CRM lo mueve solo. Las otras 19 claves son estables porque esas tablas están
inactivas. Usar `activity` como invariante de "producción intacta" produce
falsos positivos; lo que sí sirve es el conteo por `entity_type` de las
entidades del módulo.

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
ActividadOperativa 0 · PropuestaSupervisor 0 · acciones_propuestas 40
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
teams 0 · Disponibilidad 0 · operaciones_externas 0 · MutacionIdempotente 14
BusinessCalendar 1 · kill switch detenido
```

---

## U. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

Instrumentado en `socket.socket.connect` alrededor de un ciclo completo con
señales de M02 y M03. El cero se leyó **después** de probar que el espía
dispara con una sonda deliberada, **y** de comprobar que el ciclo efectivamente
detectó algo — un cero sobre un ciclo vacío no diría nada.

---

## V. Deudas

| # | Deuda |
|:--:|---|
| 1 | **H-05 bloqueada** — la decisión de §W |
| 2 | **El ciclo es ahora una transacción** (§I): fallar a la mitad no deja propuestas parciales |
| 3 | **`idx_propuesta_dedup` no es único**: la serialización la da el lock, no la base |
| 4 | **Sin asistentes separados** — §13 los difiere a propósito |
| 5 | **Sin scheduler**: el ciclo es manual, y es deliberado |
| 6 | **Duración por tipo de trabajo sin declarar** en producción: hasta que exista, la capacidad de cualquier jornada real será `DATOS_PARCIALES` |
| 7 | RLS de `campo_*` · B-7 · punto ciego de H-05 sobre cuadrillas · zona · vehículo · autonomía 2+ |

---

## W. GO / NO-GO

| # | Criterio | |
|:--:|---|:--:|
| 1 | M02 consumido correctamente | **SÍ** |
| 2 | M03 consumido correctamente | **SÍ** — incluida la capacidad de M03-G |
| 3 | Detectores existentes reutilizados | **SÍ** — 0 paralelos |
| 4 | No hay duplicación de propuestas | **SÍ** — y se corrigió un defecto real de concurrencia |
| 5 | Evidencia obligatoria | **SÍ** — servicio + base |
| 6 | Priorización coherente | **SÍ** — reglas existentes, explicadas como evidencia |
| 7 | Capacidad respeta INDETERMINADO | **SÍ** — probado en las dos direcciones |
| 8 | Revisión humana funciona | **SÍ** |
| 9 | Ciclo manual funciona | **SÍ** — el que ya existía, uno solo |
| 10 | No hay ejecución autónoma | **SÍ** |
| 11 | No hay efectos externos | **SÍ** |
| 12 | Tenant isolation correcto | **SÍ** |
| 13 | No hay regresiones atribuibles | **SÍ** |

# M09-L = GO

### La decisión que queda abierta, y que no tomé

**¿Se desbloquea H-05 para que la sobrecarga pueda proponerse?**

No es una deuda técnica: es la decisión que el propio módulo dejó escrita.
H-05 se bloqueó porque *"no existe una definición medible de capacidad
operativa, y M09-J decidió no inventarla"*. **M03-G ya la aportó** — derivada,
no inventada, con `CAPACIDAD_NO_DETERMINABLE` cuando no alcanza.

Lo que falta es autorizar la ficha que explique la señal. Mientras tanto la
sobrecarga **se ve y no se propone**, que es la única postura que no rompe ni
§14 ni el guarda de M09-K.

Las opciones, sin recomendación encubierta:

| | Opción | Costo |
|:--:|---|---|
| **A** | Desbloquear H-05 y extender su alcance a la jornada | Toca una ficha existente; su huella cambia |
| **B** | Autorizar una habilidad nueva para `jornada_sobrecargada` | 1 ficha nueva + 1 migración de choices (ya probada y revertida) |
| **C** | Dejarla como observación | Lo que hay hoy. El Jefe ve la sobrecarga pero no recibe una recomendación por ella |

---

```
codigo ......... 1 detector + 1 lectura + resumen consolidado + lock de ciclo
pruebas ........ 1 archivo creado (21 pruebas, 653 lineas)
migraciones .... 0     modelos ... 0     rutas ... 0     habilidades ... 0
M02 ............ sin tocar     M03 ... sin tocar     kill switch ... sin tocar
produccion ..... SIN CAMBIOS por M09-L (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no
```
