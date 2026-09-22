# PASO M09-E — Validación funcional del Supervisor NOC IA / Shadow Mode

**Fecha:** 2026-09-17
**Alcance:** validar que lo que M09 recomienda es correcto, explicable y está
respaldado por evidencia real. No se validó rendimiento, ni interfaz, ni
ejecución: M09 no ejecuta nada.
**Producción:** no se tocó. Toda la medición corrió contra una réplica.

---

## A. Réplica utilizada

| | |
|---|---|
| Contenedor | `pg-m09e` (PostgreSQL), puerto **15497**, aislado |
| Origen de los datos | respaldo productivo **`20260917_163739`** (restauración completa) |
| Migraciones M09-D | aplicadas **solo aquí**: `django_migrations` 192 → **194** |
| Estructura M09-D presente | columna `huella_condicion` ✔, índice `idx_propuesta_dedup` ✔ |
| Producción | **sin migrar**: 192 migraciones, sin `huella_condicion` |

No es una base sintética: son los datos reales de Rapilink, restaurados. Todo
lo que se sembró para probar escenarios se sembró **encima** de esos datos y
queda identificado como tal en la sección B.

Verificación de que producción no se movió, medida al cerrar el paso:

```
ledger                : 50
kill switch           : detenido
filas ACTIVO          : 0
PropuestaSupervisor   : 0
acciones_propuestas   : 40
django_migrations     : 192
huella_condicion      : 0   (la columna no existe en producción)
perfiles por rol      : {ADMIN: 1, USER: 4}
```

---

## B. Datos iniciales

Estado de la réplica **antes** de correr nada:

| Entidad | Filas |
|---|---|
| Organizaciones | 2 |
| Perfiles | 5 |
| `case` | **193** |
| `activity` | **578** |
| `campo_orden_trabajo` | **3** |
| `operaciones_*` (todas) | **0** |
| Ledger de migraciones | 50 |

Estado **después** de la validación, separando lo real de lo sembrado:

| Entidad | Final | Reales | Sembradas para probar |
|---|---|---|---|
| `campo_orden_trabajo` | 25 | **3** | 22 |
| `activity` | 632 | 578 | 54 |
| Perfiles | 9 | 5 | 4 (uno por rol, para la sección K) |

**Dato que condiciona todo el paso:** los módulos M02 (actividades,
compromisos, dependencias) y M03 (programación, disponibilidad) **están
vacíos en producción**. Los detectores que dependen de ellos no pudieron
validarse contra datos reales — se validaron contra escenarios sembrados.
Eso se declara explícitamente en la sección R y **no debe leerse como "no
hay problemas de ese tipo"**: significa **no hay cobertura de datos**.

---

## C. Ciclo ejecutado

Se ejecutó `supervisor.correr_ciclo(org, ahora)` una vez por organización.

Antes de importar una sola línea de M09, se instrumentó `requests` **entero**
— `get`, `post`, `put`, `patch`, `delete`, `request`, `head`, `options` —
reemplazando cada método por un espía que **cuenta y levanta excepción**. No
es un espía que observa: es uno que rompe el turno si alguien llama.

| Organización | Señales | Propuestas creadas | Llamadas externas |
|---|---|---|---|
| Rapilink | 37 | **37** (todas `caso_abierto_antiguo`) | **0** |
| Segunda organización | 0 | **0** | **0** |

**Salvedad honesta, y se registra aunque incomode:** el espía adicional sobre
`ejecutor_http` del motor reportó `MOTOR = False`, porque el código del motor
no está montado dentro del contenedor del backend — o sea, ese camino no se
pudo instrumentar *desde aquí*. Lo que sí quedó instrumentado por completo es
`requests`, que es la biblioteca por la que pasa cualquier salida HTTP del
backend, incluido el motor si alguna vez se montara. La afirmación exacta que
sostiene esta medición es: **M09 no realizó ninguna llamada saliente por
`requests`**, y no: "se probó el ejecutor del motor".

---

## D. Detectores

Los diez detectores del diseño, tal como quedaron implementados:

| Detector | Función | Módulo |
|---|---|---|
| `caso_abierto_antiguo` | `_casos_abiertos_antiguos` | M01 |
| `actividad_vencida` | `_actividades_vencidas` | M02 |
| `actividad_sin_responsable` | `_actividades_sin_responsable` | M02 |
| `actividad_bloqueada` | `_actividades_bloqueadas` | M05 |
| `compromiso_por_vencer` | `_compromisos_por_vencer` | M02 |
| `dependencia_pendiente` | `_dependencias_pendientes` | M02 |
| `orden_sin_programar` | `_ordenes_sin_programar` | M03 |
| `dato_incompleto` | `_ordenes_desincronizadas` | M10 |
| `programacion_sin_publicar` | `_programaciones_sin_publicar` | M03 |
| `orden_con_riesgo_operacional` | `_ordenes_en_riesgo` | M03 |

---

## E. Propuestas generadas

52 propuestas al cerrar el paso (37 del ciclo real + las de los escenarios
sembrados):

| Señal | n | Prioridad | Nivel | Estados |
|---|---|---|---|---|
| `caso_abierto_antiguo` | 37 | 42–43 | 1 | propuesta |
| `programacion_sin_publicar` | 4 | 15–29 | 1 | propuesta / aceptada |
| `orden_sin_programar` | 4 | 30 | 1 | propuesta |
| `actividad_bloqueada` | 2 | 25 | 1 | propuesta / rechazada |
| `compromiso_por_vencer` | 1 | 27 | 1 | propuesta |
| `dato_incompleto` | 1 | **90** | **0** | propuesta |
| `dependencia_pendiente` | 1 | 50 | 1 | propuesta |
| `actividad_vencida` | 1 | 33 | 1 | propuesta |
| `actividad_sin_responsable` | 1 | 45 | 1 | propuesta |

Integridad estructural, medida sobre las 52:

```
sin evidencia               : 0
sin huella                  : 0
con referencia de ejecución : 0
nivel de autonomía > 1      : 0
```

`dato_incompleto` es la única señal de **nivel 0** (no requiere autonomía: es
un problema de calidad del dato, no una acción sobre el mundo) y la única con
prioridad 90 — coherente con el diseño.

---

## F. Muestras revisadas

No se revisó "que la propuesta se vea razonable". Se volvió a leer la base y
se comprobó que **cada valor citado en la evidencia coincide con el dato
real**. Es lo único que detecta información inventada.

**Se revisaron las 52, no una muestra** — el volumen lo permitía.
**Problemas encontrados: 0.**

Criterios aplicados a cada una: el hecho es verdadero (el caso sigue abierto),
la fecha citada es la fecha real, el estado citado es el estado real, los días
citados coinciden con los días reales (±1), cada observación trae
`fuente`/`id`/`dato`/`observado_en`, el cálculo de prioridad viene explícito,
el nivel de autonomía no excede `RECOMENDAR`, y el texto no contiene ninguna
de 13 palabras de atribución de culpa (`incumpl`, `negligen`, `culpa`,
`olvid`, `descuid`, `no hizo`, `responsable de la demora`, …).

Muestra completa, contrastada contra la base:

```
PROPUESTA   Revisar el caso y registrar el avance o cerrarlo
SEÑAL       caso_abierto_antiguo
ORIGEN      case:b329b9f8-…
PRIORIDAD   42   NIVEL 1
MOTIVO      Lleva 8 días abierto sin resolución registrada. No se afirma
            que nadie lo haya atendido: solo que el sistema no tiene
            registro de cierre.
EVIDENCIA   fuente=case               dato=abierto desde 2026-09-09 (8 dias)
            fuente=case               dato=estado actual: New
            fuente=calculo_prioridad  dato=base 50 · antiguedad -8

CONTRASTE CONTRA LA BASE
  case.created_at  = 2026-09-09     → la evidencia cita la fecha real
  case.status      = New            → la evidencia cita el estado real
  case.resolved_at = None           → el hecho es cierto: sigue abierto
  días reales      = 8              → coincide con lo que dice el motivo
```

---

## G. Falsos positivos encontrados

**Ninguno.** Se buscaron activamente, no se esperó a que aparecieran.

### G.1 — Los diez escenarios de orden de trabajo

| # | Escenario | Esperado | Medido |
|---|---|---|---|
| A | OT sin ningún plan | señal | **señal** ✔ |
| B | OT con plan en borrador | sin señal | **sin señal** ✔ |
| C | OT con plan publicado | sin señal | **sin señal** ✔ (+ `dato_incompleto`) |
| D | OT ya programada | sin señal | **sin señal** ✔ |
| E | OT `en_sitio` | sin señal | **sin señal** ✔ |
| F | OT `completada_campo` | sin señal | **sin señal** ✔ |
| G | OT cancelada | sin señal | **sin señal** ✔ |
| H | OT en `correccion_requerida` | sin señal | **sin señal** ✔ |
| I | OT cuya línea fue reprogramada | señal | **señal** ✔ |
| J | OT cuya línea fue cancelada | señal | **señal** ✔ |

### G.2 — La medición decisiva: las 3 órdenes reales de producción

Este es el resultado que más pesa en el paso, porque es el único que usa
datos reales de M03 y porque mide la corrección hecha en M09-D:

```
OT 1842 | estado=en_sitio          | programada_para=NULL | iniciada_en=SI | propuestas=0
OT 1843 | estado=en_sitio          | programada_para=NULL | iniciada_en=SI | propuestas=0
OT 1844 | estado=completada_campo  | programada_para=NULL | iniciada_en=SI | propuestas=0

condición VIEJA (programada_para is null) habría dado: 3 falsos positivos
condición CORREGIDA                       da:          0 propuestas
```

Las tres órdenes reales tienen `programada_para` en NULL **y sin embargo ya
están en campo o terminadas**. La condición original ("sin fecha programada ⇒
sin programar") habría acusado de no programadas a tres órdenes que un técnico
ya estaba ejecutando. La condición corregida —que exige además que no exista
una `ProgramacionOrden` en estado `planificada`/`confirmada` y mira el estado
operativo real— las suprime exactamente.

### G.3 — `programacion_sin_publicar`

| Caso | Esperado | Medido |
|---|---|---|
| Programación publicada | sin señal | **sin señal** ✔ |
| Programación cerrada | sin señal | **sin señal** ✔ |
| Borrador de una semana futura | sin señal | **sin señal** ✔ |
| Borrador de una semana ya empezada | señal | **señal** ✔ |

La evidencia declara el estado exacto y el `publicada_en` vacío. El motivo
**no dice** "nadie la publicó": dice que la semana empezó y el sistema no
tiene registro de publicación.

---

## H. Falsos negativos

Se demostró por cruce independiente: se contó en SQL directo, sin pasar por
el código de M09, cuántos casos cumplen la condición, y se comparó contra las
propuestas emitidas.

```
casos abiertos hace más de 7 días (SQL independiente) : 37
propuestas caso_abierto_antiguo emitidas              : 37
```

**Coincidencia exacta: 0 falsos negativos** para `caso_abierto_antiguo`.

Para los demás detectores el cruce independiente no aporta: su universo real
es 0 filas. Cada uno se verificó individualmente disparando sobre su caso
sembrado — los cinco de actividades/compromisos/dependencias dispararon sobre
el suyo — pero eso demuestra que el detector **funciona**, no que **no se le
escape nada en producción**, porque en producción no hay nada que detectar
todavía.

---

## I. Deduplicación

| Prueba | Esperado | Medido |
|---|---|---|
| Primer ciclo tras sembrar escenarios | solo lo nuevo | **14 nuevas, 37 repetidas** ✔ |
| Segundo ciclo, sin cambios | nada | **0 nuevas** ✔ |
| Propuesta rechazada + misma evidencia | no reabrir | **0 nuevas** ✔ |
| Propuesta rechazada, ¿cambia de estado? | no | **sigue rechazada** ✔ |
| Cambia la condición operativa real | una nueva | **exactamente 1 nueva** ✔ |

La deduplicación es por `huella_condicion`, no por "misma señal": cuando el
hecho cambia, la huella cambia y nace una propuesta nueva. Cuando el hecho es
el mismo, no se repite ni aunque el humano la haya rechazado — que es
precisamente lo que evita que el sistema insista.

---

## J. Explicabilidad

Cada propuesta responde, sin que haya que abrir la base, a: **qué pasó**
(motivo), **cómo se sabe** (evidencia con fuente, id, dato y hora de
observación), **por qué importa** (impacto), **por qué está en ese lugar de
la lista** (cálculo de prioridad explícito como una observación más) y **hasta
cuándo vale** (`expira_en`).

Las 52 traen el cálculo de prioridad. Ninguna lo trae vacío.

Sobre el límite de la interpretación: las propuestas de `caso_abierto_antiguo`
y `orden_sin_programar` declaran **explícitamente** lo que NO se afirma. Se
verificó como criterio automático sobre el texto, no a ojo.
`incumplimiento_de_persona` sigue sin existir como tipo de señal, y
`first_response_at` no se usó para determinar incumplimientos SLA.

---

## K. Permisos y auditoría

**0 en rojo** sobre 16 comprobaciones.

| Comprobación | Resultado |
|---|---|
| ADMIN puede revisar | ✔ |
| SUPERVISOR puede revisar | ✔ |
| OPERACIONES puede revisar | ✔ |
| OPERACIONES **no** queda administrador de la organización | ✔ |
| USER **no** puede revisar | ✔ |
| Sin sesión **no** puede revisar | ✔ |
| Aceptar cambia el estado | ✔ |
| Queda registrado el revisor | ✔ |
| Queda registrada la fecha | ✔ |
| Queda registrado el comentario | ✔ |
| Queda el renglón de auditoría | ✔ |
| ACEPTADA **no** es EJECUTADA: `accion_propuesta_ref` vacío | ✔ |
| El único camino a la ejecución levanta `EjecucionNoPermitida` | ✔ |
| Una propuesta no se revisa dos veces | ✔ |
| Una revisión sin revisor no es una revisión | ✔ |
| `ejecutada` no existe como estado | ✔ |

El punto que cierra el Shadow Mode no es que nadie haya ejecutado nada: es que
**`ejecutar_propuesta` levanta**, y que "ejecutada" ni siquiera es un estado
posible del modelo. Aceptar una propuesta registra una opinión humana, no
dispara una acción.

---

## L. Aislamiento entre organizaciones

| Comprobación | Resultado |
|---|---|
| La segunda organización recibió propuestas | **0** ✔ |
| Todas las propuestas llevan la organización correcta | **1 sola org distinta** ✔ |
| Acceder a una propuesta de otra organización | **`Http404`** ✔ (no 403) |
| La propia organización sí la ve | ✔ |

Devolver 404 y no 403 es lo correcto: un 403 confirmaría que el objeto existe.

**Límite que hay que decir en voz alta:** este aislamiento es de **aplicación**
(filtro por `org` + `Http404`), no de base de datos, para las tablas `campo_*`.
Ver sección Q.

---

## M. Efectos externos

```
llamadas externas interceptadas        : 0
llamadas a WispHub                     : 0
llamadas a SmartOLT                    : 0
llamadas al CRM externo                : 0
escrituras HTTP                        : 0
propuestas con referencia de ejecución : 0
```

Con la salvedad de cobertura ya declarada en la sección C.

---

## N. Métricas descriptivas

Ver la tabla de la sección E. Resumen:

- 52 propuestas, 9 tipos de señal representados de 10 posibles.
- Rango de prioridad: **15 a 90**.
- Nivel de autonomía: **0 o 1**, nunca superior. Ninguna propuesta de M09
  pide permiso para actuar.
- 1 sola organización con propuestas, de 2 existentes.
- 0 propuestas sin evidencia, 0 sin huella, 0 con ejecución.

---

## O. Defectos

**Defectos de M09-D encontrados en esta validación: ninguno.**

Se registran, en cambio, tres hechos que no son defectos de M09 pero que
condicionan cómo debe leerse este informe:

1. **Cobertura de datos reales nula para M02/M03.** Nueve de los diez
   detectores no tienen en producción ni una fila sobre la que actuar. Se
   validaron contra escenarios sembrados. Es una limitación del entorno, no
   del código, y se refleja en la sección R.
2. **El ejecutor del motor no pudo instrumentarse** desde el contenedor del
   backend (`MOTOR = False`). Ver sección C.
3. **Defecto preexistente ajeno a M09**, ya reportado en su momento: en la
   Etapa B.4, `test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay`
   falla con "debería detectar tablas ajenas; devolvió []". No lo introdujo
   M09-D y no se tocó aquí.

---

## P. Correcciones necesarias

**Ninguna para dar M09-D por validado.**

Pendientes que no bloquean, ordenados por cuándo hay que resolverlos:

| # | Qué | Cuándo |
|---|---|---|
| 1 | Instrumentar el ejecutor del motor en un entorno donde esté montado, para cerrar la medición de la sección C sin salvedad | antes de activar cualquier nivel de autonomía |
| 2 | Revalidar los nueve detectores de M02/M03 cuando esos módulos tengan datos reales | cuando M02/M03 entren en operación |
| 3 | Reparar el test de la Etapa B.4 | cuando se retome esa etapa |

---

## Q. Riesgos para M10

**Siete tablas `campo_*` no tienen RLS ni una sola política:**

```
campo_asignacion_trabajo    rls=false  politicas=0
campo_evento_trabajo        rls=false  politicas=0
campo_evidencia_trabajo     rls=false  politicas=0
campo_mutacion_idempotente  rls=false  politicas=0
campo_orden_trabajo         rls=false  politicas=0
campo_work_type             rls=false  politicas=0
campo_work_type_version     rls=false  politicas=0
```

Consecuencia directa y concreta: **M09 no puede afirmar que tiene aislamiento
multi-tenant a nivel de base de datos sobre las órdenes de trabajo.** Lo que
tiene es aislamiento de aplicación, que es real y está medido (sección L),
pero que depende de que todo acceso pase por el ORM con el filtro de `org`.
Cualquier consulta directa a la base lo atraviesa.

No se modificó nada de esto: la instrucción vigente es no tocar masivamente
la RLS de las tablas `campo_*` en esta etapa. Queda como **dependencia de
M10**, y M09 no debe describirse como aislado a nivel de base mientras siga
abierta.

Riesgo secundario: cuando M02/M03 se pueblen, los nueve detectores validados
contra escenarios sembrados van a enfrentar por primera vez la variedad de
datos reales. La corrección de `orden_sin_programar` documentada en G.2 es
justamente el tipo de falso positivo que solo aparece al ver datos reales —
tres órdenes ya en campo, sin fecha programada. Hay que asumir que puede
haber más de esos.

---

## R. Decisión por detector

| Detector | Categoría | Base de la decisión |
|---|---|---|
| `caso_abierto_antiguo` | **A. VALIDADO** | 37 propuestas sobre datos reales; cada valor contrastado contra la base; cruce SQL independiente 37 = 37 |
| `orden_sin_programar` | **A. VALIDADO** | 10 escenarios A–J correctos + suprime los 3 falsos positivos de las OT reales |
| `dato_incompleto` | **A. VALIDADO** | dispara sobre la OT publicada; único nivel 0, prioridad 90 |
| `programacion_sin_publicar` | **A. VALIDADO** | 4 escenarios correctos; evidencia cita el estado exacto y el `publicada_en` vacío |
| `actividad_vencida` | **A. VALIDADO** | dispara sobre su caso; el texto no afirma incumplimiento de nadie |
| `actividad_sin_responsable` | **A. VALIDADO** | dispara sobre su caso; no inventa un responsable |
| `actividad_bloqueada` | **A. VALIDADO** | dispara sobre su caso; usa el motivo de bloqueo registrado |
| `compromiso_por_vencer` | **A. VALIDADO** | dispara sobre su caso; cita la fecha real del compromiso |
| `dependencia_pendiente` | **A. VALIDADO** | dispara sobre su caso; cita la actividad previa real |
| `orden_con_riesgo_operacional` | **C. NO VALIDABLE POR FALTA DE DATOS** | `operaciones_disponibilidad` tiene **0 filas**; sin disponibilidad declarada no hay riesgo que calcular |

**Condición que acompaña a los nueve primeros salvo `caso_abierto_antiguo`:**
la validación se hizo sobre escenarios sembrados porque **en producción no
hay cobertura de datos reales de M02/M03**. Eso significa **"no hay datos"**,
no **"no hay problemas"**. Cuando esos módulos operen, hay que rehacer esta
medición.

---

## S. Conclusión general

### Lo que quedó demostrado

- M09 no ejecuta nada, y no porque nadie lo haya intentado: el único camino a
  la ejecución levanta, y "ejecutada" ni siquiera existe como estado.
- M09 no llamó a ningún sistema externo durante el ciclo completo.
- Las 52 propuestas son verdaderas: cada fecha, cada estado y cada conteo de
  días citado en su evidencia coincide con el dato de la base.
- Ninguna propuesta atribuye culpa a una persona. Se verificó como criterio
  automático sobre el texto, con 13 patrones, no a ojo.
- La deduplicación distingue "el mismo hecho otra vez" de "un hecho nuevo", y
  respeta un rechazo humano.
- Los permisos se comportan como el diseño dice, incluidos los dos roles
  nuevos, y OPERACIONES no se convierte en administrador de la organización.
- El aislamiento entre organizaciones funciona a nivel de aplicación y
  devuelve 404, no 403.
- La corrección de `orden_sin_programar` hecha en M09-D suprime exactamente
  los 3 falsos positivos que la condición original habría producido sobre las
  únicas órdenes reales que existen.

### Lo que NO quedó demostrado, y hay que decirlo

- Nueve de los diez detectores no vieron datos reales, porque no existen.
- El ejecutor del motor no pudo instrumentarse desde este entorno.
- El aislamiento de las tablas `campo_*` es de aplicación, no de base.

### Veredicto

## GO

M09-D queda **validado funcionalmente en Shadow Mode**, con las tres
salvedades de arriba registradas, no disimuladas. Las salvedades son de
**cobertura**, no de comportamiento: donde hubo datos que medir, el sistema
se comportó correctamente en todas las mediciones.

**Lo que este GO autoriza:** dar por correcto el comportamiento de M09-D.
**Lo que este GO NO autoriza:** desplegar código, aplicar las migraciones
M09-D en producción, activar ningún nivel de autonomía, ni describir M09 como
aislado a nivel de base de datos.

---

### Limpieza

La réplica `pg-m09e` se eliminó al cerrar el paso. Producción quedó
verificada como intacta (sección A).
