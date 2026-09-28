# Paso M09-D — Supervisor NOC IA en Shadow Mode

**Fecha:** 17/09/2026
**Producción intacta:** ledger 50 · kill switch **DETENIDO** · 0 filas `activo` ·
`PropuestaSupervisor` 0 filas · `acciones_propuestas` **40, histórico intacto** ·
`django_migrations` **192** · `DBUSER` sin cambios · **cero llamadas externas**.

## Resultado: **GO**

Las cuatro condiciones de M09-C.1 quedaron cerradas con **cambios mínimos**: no
se reconstruyó nada de lo que ya existía.

---

## Lo que ya existía, y se reutilizó tal cual

`PropuestaSupervisor` · `EsJefeDeOperaciones` · `ROLES_GESTION` (importado de
`campo/permissions.py`, no copiado) · `supervisor.py` con sus 8 detectores ·
`operaciones/auditoria.py` · las 4 rutas de revisión · RLS+FORCE en las 6 tablas
`operaciones_*` · `Case` · `common.Activity` · `campo.OrdenTrabajo` ·
`ProgramacionSemanal` · `ProgramacionOrden` · `NovedadOperativa`.

**No se creó:** ningún Case, sistema de tareas, mecanismo de revisión, sistema
de auditoría, cola paralela, integración externa ni motor de SLA.

---

## A. Archivos creados

| Archivo | Qué es |
|---|---|
| `common/migrations/0040_m09d.py` | `AlterField` de `Profile.role` |
| `operaciones/migrations/0003_m09d.py` | `AddField huella_condicion` + `AlterField tipo_senal` + `AddIndex` |
| `operaciones/tests/test_m09d_shadow.py` | **45 tests** de este paso |

## B. Archivos modificados

| Archivo | Cambio |
|---|---|
| `common/utils.py` | `ROLES`: 2 → **4** (`+SUPERVISOR`, `+OPERACIONES`) |
| `operaciones/models.py` | 2 señales nuevas · `huella_condicion` · `ESTADOS_QUE_BLOQUEAN` · índice de dedup |
| `operaciones/supervisor.py` | huella en los 10 detectores · dedup corregida · `_ordenes_sin_programar` corregida · 2 detectores nuevos · 2 ramas de análisis |

**Sin tocar:** kill switch, idempotencia, frontera externa, ledger, M10,
`acciones_propuestas`, `permissions.py`, `views.py`, `urls.py`, `auditoria.py`.

## C. Migraciones creadas

```
common/migrations/0040_m09d.py
  AlterField profile.role
    choices=[('ADMIN','ADMIN'),('SUPERVISOR','SUPERVISOR'),
             ('OPERACIONES','OPERACIONES'),('USER','USER')]

operaciones/migrations/0003_m09d.py
  AddField   propuestasupervisor.huella_condicion  CharField(max_length=64, default='')
  AlterField propuestasupervisor.tipo_senal        (8 -> 10 choices)
  AddIndex   idx_propuesta_dedup
             (org, tipo_senal, origen_tipo, origen_id, huella_condicion)
```

## D. Migraciones aplicadas

**NINGUNA en producción.** Verificado contra la base productiva:

```
common      0040_m09d      aplicada: False
operaciones 0003_m09d      aplicada: False
django_migrations total: 192
columna huella_condicion en produccion: 0
```

Se aplicaron **sólo** en la base de pruebas efímera de la suite.

---

## 1. Gobierno — el rol del revisor

### El cambio, y por qué es de una línea

El permiso ya aceptaba tres credenciales; el catálogo emitía dos.

```python
ROLES = (("ADMIN","ADMIN"), ("SUPERVISOR","SUPERVISOR"),
         ("OPERACIONES","OPERACIONES"), ("USER","USER"))
```

**No es un cuarto mecanismo de autorización**: `EsJefeDeOperaciones` sigue
decidiendo con `ROLES_GESTION`, que **importa** de `campo/permissions.py`. Hay
un test que lo afirma (`test_no_se_creo_un_segundo_mecanismo_de_autorizacion`),
y comprueba la identidad del objeto, no que el nombre aparezca.

### Matriz de permisos

| Rol | Consultar | Revisar | Aceptar | Modificar | Rechazar | Ejecutar | Administrar |
|---|---|---|---|---|---|---|---|
| **ADMIN** | sí | sí | sí | sí | sí | **NO** | sí |
| **SUPERVISOR** | sí | sí | sí | sí | sí | **NO** | no |
| **OPERACIONES** | sí | sí | sí | sí | sí | **NO** | no |
| **USER** | **no** | no | no | no | no | **NO** | no |
| **Supervisor NOC IA** | escribe | **no** | no | no | no | **NO** | no |

Probado con `rf` y los cuatro roles: ADMIN/SUPERVISOR/OPERACIONES pasan,
**USER no**. Y un perfil `OPERACIONES` **no** queda `is_organization_admin`:
revisar no es administrar.

**«Ejecutar» es NO para todos**, y no por política: `ejecutar_propuesta()`
levanta siempre.

---

## 2. Deduplicación

### El defecto, y cómo se cerró

Antes: `filter(..., estado=PROPUESTA)`. Una recomendación **rechazada volvía
idéntica** al ciclo siguiente.

Ahora:

```python
filter(org, tipo_senal, origen_tipo, origen_id,
       huella_condicion=senal.huella,
       estado__in=ESTADOS_QUE_BLOQUEAN)     # propuesta, aceptada, modificada, rechazada
```

`expirada` y `cancelada` **no** bloquean: expirar significa que nadie la miró,
así que volver a preguntar es lo correcto.

### La huella: identidad, no magnitud

Casi toda señal tiene una magnitud que avanza sola — un caso suma un día cada
día. Si la huella los llevara, **una propuesta rechazada volvería mañana con
otra huella**, que es justo el defecto que este campo cierra.

| Señal | Huella | Si cambia… |
|---|---|---|
| `caso_abierto_antiguo` | `abierto_sin_resolucion` | los días son magnitud, no identidad |
| `actividad_vencida` / `compromiso_por_vencer` | `vence:<fecha-hora>` | otra fecha = otro compromiso |
| `actividad_sin_responsable` | `sin_responsable` | — |
| `actividad_bloqueada` | `bloqueo:<motivo>` | otro motivo = otro bloqueo |
| `dependencia_pendiente` | `depende:<id>` | otra dependencia = otra situación |
| `orden_sin_programar` | `estado:<estado>` | — |
| `orden_con_riesgo_operacional` | `prog:<fecha>|aus:<id>` | otra fecha u otra ausencia |
| `programacion_sin_publicar` | `semana:<fecha>` | otra semana |
| `dato_incompleto` | `campo:programada_para` | otro campo |

### Matriz de deduplicación

| Estado anterior | ¿Misma huella? | Resultado |
|---|---|---|
| `propuesta` | sí | **no se crea** (repetida) |
| `aceptada` | sí | **no se crea** |
| `modificada` | sí | **no se crea** |
| `rechazada` | sí | **no se crea** ← el defecto corregido |
| cualquiera revisado | **no** | **se crea**: los hechos son otros |
| `expirada` | sí | **se crea**: nadie la miró |
| `cancelada` | sí | **se crea** |

**El historial no se borra ni se sobrescribe**: hay un test que lo comprueba.

### Verificada desarmándola

No basta con que los tests pasen: hay que saber que **detectan el defecto**.
Se restauró la deduplicación anterior y se volvió a correr:

```
FAILED test_una_propuesta_rechazada_NO_vuelve_al_ciclo_siguiente
FAILED test_una_propuesta_aceptada_tampoco_vuelve
FAILED test_que_avance_una_MAGNITUD_no_la_hace_volver
3 failed, 1 passed
```

El cuarto (`expirada_SI_puede_volver`) pasa con las dos versiones, porque el
comportamiento viejo también lo permitía. Está bien que así sea.

---

## 3. `orden_sin_programar`

### La condición final

```python
estado_operativo == ASIGNADA
AND programada_para IS NULL
AND NOT EXISTS(ProgramacionOrden en 'planificada' o 'confirmada')
```

### Lo que se retiró, y por qué

M09-C.1 proponía añadir `iniciada_en IS NULL`. **Es redundante y se retiró:**
ninguna transición vuelve a `ASIGNADA`
(`campo/services/transiciones.py:19-32`) y `iniciada_en` sólo se escribe al
salir de ese estado. Agregarlo sugeriría una protección que la máquina de
estados ya da.

### Lo que se agregó, y por qué sí hacía falta

`ProgramacionOrden` y `programada_para` son cosas distintas y **nada las
sincroniza** — lo dice el propio modelo. Una OT puede estar en el plan con
`programada_para` en NULL, y la condición anterior habría propuesto **programar
algo ya programado**.

### Los nueve escenarios, probados

| | Escenario | Resultado |
|---|---|---|
| **A** | OT asignada, sin plan | **señal** |
| **B** | OT en plan **borrador** | sin señal — de eso habla `programacion_sin_publicar` |
| **C** | OT en plan **publicado**, sin `programada_para` | **`dato_incompleto`**, no una propuesta de programación |
| **D** | OT con `programada_para` | sin señal |
| **E–G** | `en_camino`, `en_sitio`, `completada_campo`, `cerrada`, `cancelada`, `correccion_requerida` | sin señal (6 casos parametrizados) |
| **H** | línea de plan **cancelada** | **señal** — una línea cancelada no compromete nada |
| **I** | línea **reprogramada** | **señal** — ya fue reemplazada |

Y un test afirma que la propuesta **no dice que la orden esté atrasada**.

---

## 4. `programacion_sin_publicar`

Condición: `estado == BORRADOR` **y** `semana_inicio <= hoy`.
Evidencia: `semana_inicio`, `estado`, `publicada_en` vacío, días corridos.

**No se infiere la publicación de que existan líneas de plan** — un borrador
también las tiene, y hay un test que lo comprueba. Tests para `PUBLICADA`,
`CERRADA` y semana futura: ninguna produce señal. Y **el Supervisor no publica
el plan**: se verifica que `estado` y `publicada_en` quedan intactos tras el
ciclo.

---

## 5. `dato_incompleto` — no es un comodín

**Nivel 0**, informativa, prioridad 90 (la más baja). Sólo se emite cuando hay
**un objeto concreto con un campo concreto que falta**: la OT está en un plan
**publicado** y su `programada_para` está vacío.

Registra objeto, campo (`programada_para`), evidencia de tres fuentes
(`orden_trabajo`, `programacion_orden`, `programacion_semanal`) y timestamp.

| Regla | Test |
|---|---|
| Nombra el campo y el objeto | sí |
| Es nivel 0 | sí |
| **No** se emite sobre un plan en borrador | sí — un borrador no compromete nada |
| **No** se emite si el campo está poblado | sí |
| **No** nombra a nadie ni atribuye culpa | sí — busca `incumpl`, `negligen`, `culpa`, `olvid`, `no quiso` |

`dato_contradictorio` **no se implementó**: es integridad, y M09-C.1 lo derivó a
**M10**. No se convierte en propuesta operativa.

---

## 6. Los detectores existentes

Los ocho se **validaron sin reescribirlos**. El único corregido fue
`orden_sin_programar`. A todos se les agregó la huella.

| Señal | Condición | Evidencia | Tenant | Nivel | Dueño | Efecto externo |
|---|---|---|---|---|---|---|
| `caso_abierto_antiguo` | abierto > 7 d | id, fecha, estado | `org=` | 1 | M01 | ninguno |
| `actividad_vencida` | `vence_en < now` | id, vence, estado | `org=` | 1 | M02 | ninguno |
| `actividad_sin_responsable` | `responsable NULL` | id, estado | `org=` | 1 | M02 | ninguno |
| `actividad_bloqueada` | `estado=bloqueada` | **motivo declarado** | `org=` | 1 | M05 | ninguno |
| `compromiso_por_vencer` | vence en 24 h | id, vence | `org=` | 1 | M02 | ninguno |
| `dependencia_pendiente` | `depende_de` abierta | ambas | `org=` | 1 | M02 | ninguno |
| `orden_sin_programar` | **corregida** | 3 observaciones | `org=` | 1 | **M03** | ninguno |
| `orden_con_riesgo_operacional` | ausencia declarada | OT + disponibilidad | `org=` | 1 | M03 | ninguno |

**No se usa `first_response_at`** — no hay ninguna señal sobre incumplimiento de
primera respuesta, y un test existente lo afirma.

---

## 7. Evidencia — las cuatro capas separadas

| Capa | Dónde vive |
|---|---|
| **HECHO** | dentro de cada observación de `evidencia[]` |
| **EVIDENCIA** | `{fuente, id, dato, observado_en}` — tabla, objeto, dato, hora de lectura |
| **INTERPRETACIÓN** | `motivo` |
| **PROPUESTA** | `accion_propuesta` |

Los componentes de la prioridad viajan **como evidencia**, así que se puede
reconstruir por qué quedó donde quedó en vez de confiar en un número.

**Prohibido y probado:** ninguna propuesta puede decir «el técnico incumplió» ni
equivalentes. Los motivos citan **causas declaradas** (`NovedadOperativa`), no
deducidas.

---

## 8. Autonomía

Todas las propuestas quedan en **nivel 0 o 1** — hay un test que recorre las
generadas y lo afirma. El modelo admite almacenar 2–4 por diseño futuro, y
**permanecen sin camino de ejecución**: `ejecutar_propuesta()` levanta siempre,
`ejecutada` no existe como estado, `accion_propuesta_ref` queda vacío.

**La IA no puede elevar su propio nivel:** `supervisor.py` no tiene ninguna
función que toque `Profile`, permisos, roles ni el interruptor — verificado por
análisis del AST, no por lectura.

---

## 9. Human in the loop

Se reutilizó el flujo existente. `revisar()` exige un `actor` que **no puede ser
`None`**: una transición sin persona detrás no es representable. Registra
`revisado_por`, `revisado_en`, decisión y `resultado`, más su renglón de
auditoría.

**Aceptar no ejecuta. Modificar no ejecuta. Rechazar no borra** — los tres
comprobados. **No se creó una segunda cola de revisión.**

---

## 10 y 11. Shadow Mode e idempotencia del ciclo

El ciclo hace: expirar vencidas → detectar → deduplicar → analizar → registrar →
auditar. **Y nada más.**

Análisis del AST de `supervisor.py`: de 194 identificadores usados por el
**código** (sin comentarios ni docstrings), **ninguno** es `wisphub`,
`smartolt`, `requests`, `httpx`, `urllib`, `ejecutor_http`, `operativo`,
`cerrar_todo`, `cerrar_vencidas`, `idempotencia` ni `nucleo`.

| Prueba | Resultado |
|---|---|
| Ciclo 1 → propuesta; ciclo 2 misma evidencia → **0 duplicados** | sí |
| Propuesta rechazada + misma evidencia → **no duplica** | sí |
| Nueva condición operacional → **sí** genera nueva | sí |
| Expirada → puede volver | sí |

---

## 12. Pruebas de seguridad — cero efectos externos, contados

No se mockea la lógica de M09: corre entera. Lo que se instrumenta es
`requests`, con un espía que **falla la prueba si alguien lo llama**.

| Prueba | Resultado |
|---|---|
| El ciclo no hace ni una llamada externa | **0 llamadas**, y ≥1 propuesta generada |
| El ciclo no modifica la OT ni el plan | estado, `programada_para`, `iniciada_en`, `publicada_en` intactos |
| El ciclo no cierra ningún caso | `status`, `resolved_at`, `closed_on` intactos |
| El Supervisor no publica el plan | `BORRADOR` y `publicada_en=None` tras el ciclo |
| Ninguna propuesta supera el nivel 1 | sí |
| Las señales nuevas no cruzan organizaciones | sí |

---

## E · F · G. Tests

### E. Tests nuevos — **45**, en `operaciones/tests/test_m09d_shadow.py`

| Grupo | Cuántos |
|---|---|
| Deduplicación (rechazada, aceptada, condición nueva, magnitud, expirada, ciclo repetido, historial) | 7 |
| `orden_sin_programar` — escenarios A–I | 11 (6 parametrizados) |
| `programacion_sin_publicar` | 7 |
| `dato_incompleto` | 5 |
| Rol y permisos del revisor | 7 (4 parametrizados) |
| Cero efectos externos, niveles, tenant, huella | 8 |

### F. Tests totales

| Suite | Resultado |
|---|---|
| Django · `operaciones/tests/` | **97 en verde** (12 M02 + 14 M03 + 26 M09 + **45 M09-D**) |
| Django · `operaciones` + `common` + `campo` | **1433 passed · 13 failed · 6 skipped** de 1452 |
| Motor · `tests/` del repositorio | **84 en verde, 2 en rojo** |

**Los 45 tests nuevos pasan, y los 97 de `operaciones/` también.** Los 13 fallos
de la suite ampliada están todos fuera de M09 y se diagnosticaron uno por uno.

### G. Tests fallidos y causa — **ninguno de los 15 es de este paso**

13 en la suite Django ampliada + 2 en la del motor. Ninguno se da por
preexistente de palabra: **todos** se midieron.

| Test | Causa medida | ¿De M09-D? |
|---|---|---|
| `test_magic_link.py` · **8 casos** | **`redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379. Connection refused.`** Verificar un magic link crea el usuario y despacha el correo por Celery | **no** |
| `test_teams.py::test_update_team` y `::test_update_team_with_users` | mismo `RuntimeError` de Celery | **no** |
| `test_users.py::test_delete_user_as_admin` | ídem | **no** |
| `test_auth.py::TestGoogleOAuthCallbackView::test_successful_oauth_new_user` | ídem. Aislado: **1 failed, 51 passed** — los otros 51 crean perfiles `ADMIN` y `USER` y pasan | **no** |
| `test_credenciales_postgres.py::test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay` | guarda de la **Etapa B.4** sobre roles de PostgreSQL. Aislado: **1 failed, 9 passed** | **no** |
| `tests/test_p2_inerte.py` (motor) | nombra `verificar_restauracion.py` y la migración `202609151705`, de B.7 y 10.5 | **no** |
| `tests/test_reloj.py` (motor) | contadores de reconciliación y lista de herramientas de Fase 2 | **no** |

### La prueba de causalidad, no la inferencia

El patrón «todos disparan Celery» era una hipótesis razonable, y una hipótesis
razonable no es una medición — sobre todo con
`test_delete_user_as_admin`, que toca permisos de administrador y era el
candidato natural a haber roto yo.

Así que se restauró la versión **HEAD** de `common/utils.py`
(`ROLES = (ADMIN, USER)`, sin los dos roles nuevos) y se corrieron los tres
archivos otra vez:

```
11 failed, 100 passed in 440.11s

FAILED test_magic_link.py  (los mismos 8)
FAILED test_teams.py::TestTeamsDetailView::test_update_team
FAILED test_teams.py::TestTeamsDetailView::test_update_team_with_users
FAILED test_users.py::TestUserDetailView::test_delete_user_as_admin
```

**La lista es idéntica.** Con el catálogo de roles anterior fallan exactamente
los mismos once. El cambio de `Profile.ROLES` no rompió ninguno.

`common/utils.py` quedó restaurado a la versión de este paso (los 4 roles);
el repositorio no conserva la versión de comparación.

### Y la señal que sí habría delatado un problema

`common/tests/test_is_org_admin.py` —el archivo más expuesto, porque prueba
justamente la derivación `is_organization_admin = (role == "ADMIN")`— pasa
**14 de 14**.

---

## Un defecto ajeno que conviene no perder

`test_credenciales_postgres.py::test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay`
falla con:

```
AssertionError: deberia detectar tablas ajenas; devolvio []
```

Es de la **Etapa B.4** y no tiene nada que ver con M09-D — el acoplamiento es
cero:

```
common/credenciales.py                      importa: __future__, dataclasses
common/tests/test_credenciales_postgres.py  importa: os, uuid, pytest,
                                                     common.credenciales
menciones a 'utils', 'ROLES', 'operaciones', 'supervisor' o 'Profile':  0
```

Pero **una guarda que debía detectar tablas de otro dueño está devolviendo lista
vacía**, y eso es justo lo que esa guarda existe para impedir. No lo arreglo
aquí porque está fuera del alcance de este paso; queda señalado para que alguien
lo mire.

---

## 13. RLS de `campo_*` — **DEPENDENCIA / RIESGO M10**

**No se resolvió aquí, y no se afirma que M09 tenga aislamiento completo.**

Medido en producción:

```
campo_orden_trabajo, campo_asignacion_trabajo, campo_evento_trabajo,
campo_evidencia_trabajo, campo_mutacion_idempotente, campo_work_type,
campo_work_type_version   ->  RLS=False, FORCE=False, 0 politicas

(las 6 tablas operaciones_* si tienen RLS + FORCE + 2 politicas)
69 de 135 tablas de public no tienen ninguna politica
```

Tres señales leen `campo_orden_trabajo` (`orden_sin_programar`,
`orden_con_riesgo_operacional`, `dato_incompleto`). Para ellas, **el aislamiento
por organización lo da el queryset de Django (`org=org`), no la base**.

Este paso **no lo empeora** —no agrega ninguna lectura nueva sin filtro de
organización— pero tampoco lo arregla. **Queda trasladado a M10.**

---

## H. Señales implementadas

**10**: las 8 anteriores (7 sin cambios, `orden_sin_programar` corregida) más
`programacion_sin_publicar` y `dato_incompleto`.

## I. Señales que permanecen NO DISPONIBLES

| | Motivo |
|---|---|
| `orden_con_riesgo_operacional` | `operaciones_disponibilidad` = **0 filas** en producción. El detector existe y es correcto; sin disponibilidad declarada no puede disparar, e inventarla sería inventar una ausencia |
| Capacidad / sobrecarga de cuadrillas | misma tabla vacía |
| Incumplimiento de primera respuesta | **prohibida por diseño**: `first_response_at` poblado en 4 de 197 |
| `dato_contradictorio` | derivada a M10 |

Cinco de las diez no dispararán en producción hasta que M02/M03 se pueblen
(`operaciones_actividad`, `_disponibilidad`, `_programacion_*` están en 0 filas).
**Es correcto, y conviene saberlo para no leer el silencio como fallo.**

---

## M. Riesgos trasladados a M10

1. **RLS de las 7 tablas `campo_*`** (§13) — el más importante.
2. **69 de 135 tablas de `public` sin política.**
3. **`dato_contradictorio`** como control de integridad transversal.
4. **El frontend** todavía no ofrece los roles nuevos en el selector de perfil:
   hasta que lo haga, asignar `OPERACIONES` requiere el admin de Django o la API.

## N. Confirmación de cero efectos externos

**Ninguna llamada a WispHub, SmartOLT ni al CRM externo** durante todo el paso.
Las pruebas instrumentan `requests` con un espía que **falla si alguien lo
llama**; el análisis del AST confirma que el módulo no importa nada externo; y
el único camino declarado hacia la ejecución levanta una excepción.

## O. Estado de producción

| | |
|---|---|
| Ledger | **50** |
| Kill switch | **DETENIDO** · 0 filas `activo` |
| `PropuestaSupervisor` | **0 filas** — no se creó ninguna propuesta en producción |
| `acciones_propuestas` | **40 filas, intactas** |
| `django_migrations` | **192** — ninguna migración de M09-D aplicada |
| Columna `huella_condicion` en producción | **no existe** |
| `DBUSER` | sin cambios |
| Autonomía | **NO OPERATIVA** |

---

## Criterio de cierre

| Requisito | |
|---|---|
| Shadow Mode funciona | **sí** |
| No hay ejecución externa | **sí** — contado, no deducido |
| Deduplicación funciona | **sí** — y verificada desarmándola |
| Evidencia obligatoria | **sí** — en el código y en la base |
| Tenant isolation se mantiene | **sí**, con la salvedad documentada de `campo_*` |
| Jefe de Operaciones puede revisar | **sí** — 3 roles sí, USER no |
| No existe autoelevación | **sí** |
| `orden_sin_programar` sin falsos positivos | **sí** — 9 escenarios |
| Publicación demostrable | **sí** — `estado` + `publicada_en` + `publicada_por` |
| `dato_incompleto` no es comodín | **sí** — 5 reglas, 5 tests |
| `acciones_propuestas` intactas | **sí** — 40 filas |
| No hay segunda cola de revisión | **sí** |
| Producción intacta | **sí** |

# DECISIÓN: **GO**

**Me detengo. No avanzo a autonomía. No activo nada. No despliego.**
