# M03-G — Capacidad operacional

**Fecha:** 2026-09-18
**Veredicto:** **M03-G = GO**

```
Pruebas propias ........  28 passed / 0 failed / 0 skipped
Regresion completa .....  4353 passed / 1 failed / 19 skipped
  el unico fallo ....... CATEGORIA C (entorno), probado: pasa bajo su
                         configuracion declarada
Migraciones ............  0        makemigrations --check: "No changes detected"
Modelos nuevos .........  0        Tablas nuevas: 0
Efectos externos .......  0        (espia probado que dispara primero)
Produccion .............  SIN CAMBIOS -- 18 claves, DIFERENCIAS: NINGUNA
Commit .................  no
```

---

## A. Auditoría mínima realizada

| Parámetro | Qué se midió | Veredicto |
|---|---|---|
| **Jornada** | `BusinessCalendar` existe; **1 fila** en producción: `timezone='UTC'`, lun–vie 09:00–17:00, sáb/dom NULL, **0 feriados** | **USABLE** |
| **Duración** | **No existe campo de duración en ningún modelo.** Pero `ProgramacionOrden.hora_inicio`/`hora_fin` ya existen (nullable), y `WorkTypeVersion.esquema` es un `JSONField` | **USABLE sin migración** |
| **Complejidad** | Barrido completo: **no existe** ninguna estructura | **NO DISPONIBLE** |
| **Productividad** | **1 sola** OT completada con duración real observable (OT 1844: 00:25→01:22, ~57 min) | **NO USAR** |
| **Desplazamiento** | GPS **sí** poblado (3/3 OTs, Medellín). **No existe** regla que convierta distancia en minutos, y llamar un servicio externo está prohibido | **NO USAR** |
| **Disponibilidad** | `DisponibilidadTecnico` con `(fecha, hora_inicio, hora_fin, disponible, motivo)`. **0 filas** en producción | **USABLE** |
| **Cuadrilla** | `AsignacionTrabajo` (M03-F-B) | **USABLE** |

**El repo ya había decidido lo más importante.** `operaciones/models.py:286-293`, escrito al crear `DisponibilidadTecnico`:

> *"Un numero de 'capacidad' depende de la disponibilidad, de la carga ya asignada, de la duracion estimada del tipo de trabajo, de la zona y de los bloqueos. **Guardarlo es garantizar que quede viejo** la proxima vez que cualquiera de esos cinco cambie. Se calcula cuando se necesita."*

Por eso M03-G **no crea modelo, ni tabla, ni migración**. La capacidad se deriva.

---

## B. Decisiones encontradas

### B.1 La jornada declara UTC y Colombia opera UTC−5

**[MEDIDO]** El calendario de producción dice `timezone='UTC'` con horario 09:00–17:00. Colombia opera UTC−5, así que esas horas **tal como están almacenadas** corresponden a las 04:00–12:00 hora local colombiana.

**Resolución, sin cambiar nada en silencio:** el servicio **lee y respeta `BusinessCalendar.timezone` tal como esté**. No lo reinterpreta. Si la jornada declarada no corresponde a la operación real, eso se corrige **editando el calendario** — es configuración que ya existe, no código.

**No es bloqueante:** el cálculo funciona con cualquier zona declarada. Queda como observación para el negocio.

### B.2 El ejemplo del encargo implica un descanso que el sistema no define

**[MEDIDO]** §15 plantea 08:00–17:00 → *"480 minutos efectivos"*. Ese tramo son **540** minutos; los 480 suponen un descanso de 60 que **ninguna estructura declara**. Y §15 prohíbe expresamente inventar descansos.

**Resolución:** se computa la ventana literal (540). Los 480 salen **cuando el descanso se declara**, y para eso **ya existe `DisponibilidadTecnico`**: una franja con `disponible=False` de 12:00 a 13:00. Probado en `test_8b`, que reproduce el ejemplo completo y da exactamente 480 / 420 / 60.

### B.3 El esquema de una versión publicada es inmutable

**[MEDIDO]** `WorkTypeVersion.clean()` (`campo/models.py:133`) impide modificar `esquema` una vez `PUBLICADA`. Lo descubrió una prueba que fallaba.

**Consecuencia real:** la versión `ftth_instalacion` v1 de producción **no puede recibir una duración retroactivamente** — haría falta publicar una v2. Es lo correcto (un cambio de plantilla queda versionado y auditado), pero hay que saberlo: **no es una migración, es una acción operativa del negocio**, y no la hago yo.

---

## C. Bloqueantes

# NINGUNO

Los tres parámetros sin datos —complejidad, productividad, desplazamiento— **no bloquean**: se excluyen del cálculo y se declaran como no disponibles, que es exactamente lo que §5, §6 y §7 ordenan.

---

## D. Modelo de capacidad

```
CAPACIDAD DISPONIBLE  =  ventana de BusinessCalendar del dia
                         ∩ franjas de disponibilidad de la persona
                         − franjas de ausencia

CARGA PROGRAMADA      =  suma de la duracion de las OTs de esa persona ese dia
                         (las de su cuadrilla, sea principal o auxiliar)

RIESGO                =  carga > capacidad
```

**No se guarda nada.** Sin modelo, sin tabla, sin migración: se calcula al preguntar.

### D.1 La regla que gobierna todo: un dato que falta no vale cero

Una OT sin duración conocida **no aporta 0 minutos**: aporta *desconocido*. De ahí la asimetría del veredicto:

| Datos | ¿Se puede afirmar SOBRECARGA? | ¿Se puede afirmar SIN_SOBRECARGA? |
|---|:--:|:--:|
| Completos | **sí** | **sí** |
| Parciales | **SÍ** — si lo conocido ya no cabe, agregar lo desconocido tampoco va a caber | **NO** → `INDETERMINADO` |
| Sin jornada | no | no → `CAPACIDAD_NO_DETERMINABLE` |

Un supervisor que lea *"sin sobrecarga"* sobre datos incompletos toma una decisión peor que uno que lea *"no se sabe"*. Probado en las dos direcciones (`test_11` y `test_11b`).

---

## E. Parámetros utilizados

| Parámetro | Fuente | Sin inventar nada |
|---|---|---|
| **Jornada** | `BusinessCalendar` + `BusinessHoliday`, en su `timezone` declarado | ✓ |
| **Duración** | 1º `ProgramacionOrden.hora_fin − hora_inicio` · 2º `WorkTypeVersion.esquema["duracion_estimada_minutos"]` · 3º **DESCONOCIDA** | ✓ nunca 0 |
| **Disponibilidad** | `DisponibilidadTecnico`, por franjas, con unión/intersección/resta de tramos | ✓ |
| **Composición** | `AsignacionTrabajo` (M03-F-B) | ✓ |

**La clave `duracion_estimada_minutos` no se sembró en ningún lado.** Es un lugar donde el dato *puede* declararse; si no está, la duración es desconocida. Y se valida con dureza: `True` (que en Python es `int` y valdría 1 minuto), `0`, negativos, strings y floats **se rechazan** como duración (`test_12c`).

---

## F. Parámetros NO disponibles

| Parámetro | Por qué no se usa | Estado |
|---|---|---|
| **Complejidad** | No existe ninguna estructura | `NO DISPONIBLE` |
| **Productividad** | 1 sola OT completada. Una muestra no es una métrica | `DEPENDENCIA FUTURA` |
| **Desplazamiento** | GPS existe, pero no hay regla distancia→minutos y no se permiten servicios externos | `DEPENDENCIA FUTURA` |

Ninguno entra al cálculo. No se les asigna un valor por defecto.

---

## G. Archivos modificados

| Archivo | Cambio |
|---|---|
| `operaciones/capacidad.py` | **CREADO** — 432 líneas, todo el servicio |
| `operaciones/tests/test_m03g_capacidad.py` | **CREADO** — 681 líneas, 28 pruebas |
| `operaciones/views.py` | +1 import, +1 vista `CapacidadJornadaView` (GET) |
| `operaciones/urls.py` | +1 ruta |
| `operaciones/tests/test_m09f_gobernanza.py` | +1 ruta declarada en el guarda, **con su justificación** (ver Q) |

**No se tocó:** M09 (`supervisor.py`) · `revisar_coherencia` · M03-E · M03-D · `programacion.py` · `campo/*` · ningún modelo.

---

## H. Modelos modificados

# 0

Ninguno. No se creó entidad de capacidad, ni campo, ni constraint, ni índice.

---

## I. Migraciones

```
makemigrations --check  ->  "No changes detected"
```

# 0

Todo el contrato se cumple leyendo estructuras que ya existían. `ProgramacionOrden.hora_inicio`/`hora_fin` ya estaban en el modelo (`hora_fin` nunca se ha poblado, pero el campo existe) y `WorkTypeVersion.esquema` es un `JSONField`.

---

## J. Endpoints

```
GET /api/operaciones/capacidad/jornada/?dia=YYYY-MM-DD
GET /api/operaciones/capacidad/jornada/?dia=YYYY-MM-DD&profile_id=<uuid>
```

**Uno solo, y es un GET.** No hay endpoint de escritura, ni de ejecución. Permiso: `EsJefeDeOperaciones`, el mismo del resto del módulo. 400 si falta o es inválido el día; 404 si el `profile_id` es de otra empresa.

Respuesta (extracto real de `test_api_devuelve_valores_no_solo_200`):

```jsonc
{
  "dia": "2026-10-05",
  "jornada": {"abierta": true, "apertura": "08:00:00", "cierre": "16:00:00",
              "minutos": 480, "zona_horaria": "UTC"},
  "personas": 1, "ordenes_programadas": 2, "con_sobrecarga": 1,
  "resultados": [{
    "resultado": "CALCULADA", "estado_datos": "DATOS_SUFICIENTES",
    "capacidad_minutos": 480,
    "carga": {"minutos_conocidos": 560, "ordenes": 2,
              "ordenes_sin_duracion": 0, "es_cota_inferior": false, "detalle": [...]},
    "disponible_restante_minutos": -80, "exceso_minutos": 80,
    "riesgo": "SOBRECARGA", "faltantes": ["SIN_REGISTRO_DISPONIBILIDAD"]
  }]
}
```

---

## K. Fórmula y reglas

```
jornada(org, dia):
    calendario por defecto de la org        -> si no hay:      SIN_CALENDARIO
    feriado ese dia                         -> si lo hay:      FERIADO
    apertura/cierre del dia de la semana    -> si son NULL:    JORNADA_CERRADA
    cierre <= apertura                      ->                 JORNADA_INVALIDA
    minutos = cierre - apertura

duracion(linea):
    hora_fin - hora_inicio de la linea      -> "franja_de_la_linea"
    esquema["duracion_estimada_minutos"]    -> "tipo_de_trabajo"   (int > 0)
    si no                                   -> None = DESCONOCIDA   (NUNCA 0)

disponibilidad(persona, dia):
    sin franjas   -> jornada completa, con el SUPUESTO declarado
    con franjas   -> (jornada ∩ union(positivas)) − union(negativas)
    estados: DISPONIBLE · DISPONIBILIDAD_PARCIAL · AUSENTE · SIN_REGISTRO

veredicto:
    jornada cerrada          -> CAPACIDAD_NO_DETERMINABLE / INDETERMINADO
    duraciones incompletas   -> SOBRECARGA si lo conocido ya no cabe, si no INDETERMINADO
    duraciones completas     -> SOBRECARGA si carga > capacidad, si no SIN_SOBRECARGA
```

**`secuencia` y `prioridad` no participan.** Probado variándolas y midiendo que la capacidad no cambia (`test_15_16_17_18`).

---

## L. Disponibilidad

Cuatro estados distinguidos, y el cuarto pesa tanto como los otros: **`SIN_REGISTRO` no es `DISPONIBLE`**. Cuando no hay franjas se toma la jornada completa —es lo único que permite calcular algo— pero **el supuesto viaja en la respuesta** (`disponibilidad.supuesto`) y `SIN_REGISTRO_DISPONIBILIDAD` aparece en `faltantes`.

Una ausencia **reduce la capacidad** y **no hace nada más**: no retira a nadie, no reasigna, no reprograma, no atribuye incumplimiento. El texto de la ausencia es un dato de disponibilidad, no una falta.

---

## M. Cuadrillas

Se lee la **pertenencia** a `AsignacionTrabajo`, no la principalía: un ayudante también está ocupado esas horas.

**Sin coeficientes inventados.** Una OT de 200 minutos con dos personas cuesta **200 minutos a cada una**. Ni se divide entre dos —eso supondría que rinden el doble— ni se multiplica. No existe regla empresarial de productividad de cuadrillas y no se inventa una (`test_14`).

---

## N. Programación

**Intacta, medido.** Tras consultar la capacidad tres veces, se comparan nueve campos:

```
programada_para · revision · estado_operativo · secuencia · dia · zona
prioridad · estado_linea · updated_at de la linea · hora_inicio · hora_fin
                        ->  TODOS IDENTICOS
```

Se compara también `updated_at`: los valores podrían coincidir y aun así haberse reescrito. `programacion.py` no se modificó.

---

## O. M09

**No se tocó.** El servicio no necesita que M09 lo lea para cumplir su objetivo, así que no se hizo integración alguna — la lectura más conservadora de *"no modificar M09 en profundidad"*.

Queda **listo para integrarse**: `capacidad_de_jornada()` devuelve `riesgo` y `con_sobrecarga`, que es lo que una señal futura necesitaría. M03-G **no propone ni ejecuta** nada.

**Único cambio en un archivo de M09:** una línea en su *prueba* de gobernanza, declarando la ruta nueva (ver Q).

---

## P. Pruebas

```
28 passed / 0 failed / 0 skipped
```

Las 24 exigidas por §19 que son ejecutables, más 4 de contrato (sin calendario, jornada inválida, las dos fuentes de duración, basura en el esquema). Las dos de regresión (§19.25–26) son la suite completa, en Q.

**Afirman sobre valores, no sobre HTTP 200.** Las más importantes:

| Prueba | Qué demuestra |
|---|---|
| `test_11` | Una duración desconocida **no suma 0**, y el veredicto pasa a `INDETERMINADO` |
| `test_11b` | Con datos parciales, la sobrecarga **sí** se puede afirmar |
| `test_8b` | El ejemplo del encargo (480/420/60) sale **declarando** el descanso, no inventándolo |
| `test_12c` | `True`, `0`, `-30`, `"120"`, `None`, `12.5` se rechazan como duración |
| `test_14` | La duración **no se reparte** entre la cuadrilla |
| `test_9` | Carga **igual** a capacidad no es sobrecarga |
| `test_23` | Consultar no mueve la programación, `updated_at` incluido |
| `test_24` | 0 llamadas externas, con el espía probado antes |

---

## Q. Regresión

```
4353 passed · 1 failed · 19 skipped        (21m 31s)
```

### Clasificación

| Cat. | Fallo | |
|:--:|---|---|
| **A** (por M03-G) | `test_m09f_gobernanza::test_no_existe_ninguna_ruta_de_ejecucion` | **CORREGIDO** |
| **B** (preexistente) | — | 0 |
| **C** (entorno) | `test_portal_rls::test_resolution_reads_estimate_that_empty_context_hides` | **1, probado** |
| **D** (test incorrecto) | — | 0 |

**El fallo A fue el guarda de gobernanza haciendo exactamente su trabajo.** Fija el inventario **exacto** de rutas de `operaciones/urls.py` para que ninguna se agregue sin venir a declarar que no ejecuta nada — su propio docstring lo dice: *"cualquier ruta nueva hace fallar esta prueba, y eso es lo buscado"*.

**No se relajó la prueba.** Se añadió `capacidad-jornada` al inventario **con su justificación escrita**, igual que hicieron `linea-secuencia` (M03-E4) y `jornada-secuenciar` (M03-E5-B). Suite de gobernanza después: **83 passed**.

**El fallo C está probado, no declarado.** Su propio docstring exige rol no-superusuario y `crm.test_settings_postgres`; se creó un rol `rlsuser` (`NOSUPERUSER`, `NOBYPASSRLS`) y bajo esa configuración da **2 passed**. Está además marcado `postgres_only`, que es lo que CI deselecciona. Mismo fallo ya clasificado en M03-F-B.

---

## R. Seguridad

| Verificación | Resultado |
|---|---|
| Cada org ve solo sus órdenes y su calendario | **sí** — `test_19_20_21`: org A 540 min / org B 240 min, sin mezclarse |
| `profile_id` de otra empresa | **404**, nunca 403 |
| Usuario sin rol de gestión | **403** |
| Escrituras | **ninguna** — el endpoint es GET |

**Sin matices sobre la deuda estructural:** `campo_*` sigue sin RLS y `campo_asignacion_trabajo` sin `org_id` propio. El aislamiento vive en la capa de aplicación. M03-G **no lo resuelve** y no pretende hacerlo.

---

## S. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

Instrumentado en `socket.socket.connect` alrededor de `capacidad_de_jornada` y `capacidad_de_persona`. El cero se leyó **después** de probar que el espía dispara con una sonda deliberada a `example.invalid`.

---

## T. Producción

# SIN CAMBIOS

Solo `SELECT`, `read_only = True`. **18 claves → DIFERENCIAS: NINGUNA.**

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · teams 0 · Disponibilidad 0 · operaciones_externas 0
MutacionIdempotente 14 · BusinessCalendar 1 · BusinessHoliday 0
kill switch detenido · tenant_config rapilink v146
```

**Qué diría hoy M03-G sobre producción, medido:** hay **0 `ProgramacionOrden`**, así que la respuesta sería `personas: 0`, `ordenes_programadas: 0`. No hay nada que calcular todavía — y eso es la respuesta correcta, no un error.

---

## U. Deudas no bloqueantes

Documentadas, **ninguna implementada**:

| # | Deuda |
|:--:|---|
| 1 | **Productividad** — hace falta más de una OT completada |
| 2 | **Desplazamiento** — falta una regla distancia→minutos; el GPS ya está |
| 3 | **Complejidad** — no existe estructura ni catálogo |
| 4 | **Zona** sin catálogo (E-7) · **Vehículo** sin modelo |
| 5 | **RLS de `campo_*`** y `org_id` propio · **B-7** |
| 6 | **H-05 mira solo al principal**; el punto ciego crece con las cuadrillas |
| 7 | **Autonomía 2+** |
| 8 | **Zona horaria del calendario** (B.1) — configuración, decisión del negocio |
| 9 | **Duración por tipo de trabajo** (B.3) — exige publicar una v2, acción operativa |
| 10 | `ProgramacionOrden.hora_fin` **existe y nunca se puebla**; poblarlo daría la duración más precisa sin migración |

---

## V. GO / NO-GO

| # | Criterio | |
|:--:|---|:--:|
| 1 | Cálculo de capacidad medible | **SÍ** |
| 2 | Carga programada medible | **SÍ** |
| 3 | Disponibilidad considerada | **SÍ** — 4 estados |
| 4 | Datos faltantes explícitos | **SÍ** — `faltantes`, `es_cota_inferior`, `NO_DETERMINABLE` |
| 5 | No se inventan valores | **SÍ** — ni duración, ni descansos, ni coeficientes, ni jornada |
| 6 | Programación intacta | **SÍ** — 11 campos idénticos |
| 7 | Cuadrillas reutilizan `AsignacionTrabajo` | **SÍ** |
| 8 | Tenant isolation | **SÍ** |
| 9 | 0 efectos externos | **SÍ** — espía probado |
| 10 | Sin regresiones atribuibles | **SÍ** — la única (A) corregida declarándola, no relajándola |
| 11 | Producción intacta | **SÍ** — 18 claves |
| 12 | `makemigrations --check` limpio | **SÍ** — 0 migraciones |
| 13 | Limitación de datos ≠ dato falso | **SÍ** — `CAPACIDAD_NO_DETERMINABLE` antes que un número inventado |

# M03-G = GO

---

```
codigo ......... 2 archivos creados · 3 modificados     modelos ... 0     tablas ... 0
migraciones .... 0     endpoints ... 1 (GET)     entidades nuevas ... 0
M09 ............ sin tocar (salvo declarar la ruta en su guarda de gobernanza)
revisar_coherencia · M03-E · M03-D · campo/* ....... sin tocar
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no
```
