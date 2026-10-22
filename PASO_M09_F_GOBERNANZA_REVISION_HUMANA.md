# PASO M09-F — Gobernanza y ciclo de revisión humana

**Fecha:** 2026-09-17
**Alcance:** cerrar y probar funcionalmente el ciclo humano de revisión de
`PropuestaSupervisor`. Sin autonomía, sin efectos externos, sin tocar producción.
**Las tres salvedades de M09-E** (cobertura M02/M03, `orden_con_riesgo_operacional`
no validable, ejecutor del motor no montado) **no se resolvieron en este paso**:
ninguna impide el ciclo de revisión humana. Siguen abiertas tal como quedaron.

---

## A. Flujo actual — lo que ya existía antes de tocar nada

Auditado archivo por archivo antes de modificar una sola línea.

| Pieza | Dónde | Estado encontrado |
|---|---|---|
| `PropuestaSupervisor` | [models.py:561](django-crm/backend/operaciones/models.py#L561) | 6 estados, evidencia con `CheckConstraint`, `huella_condicion`, sin estado `ejecutada` |
| `supervisor.revisar` | [supervisor.py](django-crm/backend/operaciones/supervisor.py) | aceptar/modificar/rechazar, audita, exige actor |
| `supervisor.expirar_vencidas` | ídem | expira solo las que siguen en `propuesta` |
| `supervisor.ejecutar_propuesta` | ídem | levanta `EjecucionNoPermitida` siempre |
| `EsJefeDeOperaciones` | [permissions.py:31](django-crm/backend/operaciones/permissions.py#L31) | exige sesión + Profile + Org + rol de gestión |
| `ROLES_GESTION` | [campo/permissions.py:9](django-crm/backend/campo/permissions.py#L9) | `{ADMIN, SUPERVISOR, OPERACIONES}` — **importado**, no copiado |
| `misma_organizacion` | [permissions.py:52](django-crm/backend/operaciones/permissions.py#L52) | levanta `Http404`, nunca 403 |
| Endpoints | [urls.py](django-crm/backend/operaciones/urls.py) | 4 rutas: listar, detalle, revisar, ciclo |
| Auditoría | [auditoria.py](django-crm/backend/operaciones/auditoria.py) | escribe en `common.Activity`, dentro de la misma transacción |
| RLS | [0002_rls_operaciones.py](django-crm/backend/operaciones/migrations/0002_rls_operaciones.py) | `operaciones_propuesta_supervisor` **sí** tiene RLS |

**Este flujo no se reconstruyó.** Todo lo de arriba sigue en su sitio y se
reutilizó. Lo que sigue son los cuatro huecos que la auditoría encontró.

### Los cuatro huecos

| # | Hueco | Cómo se comprobó |
|---|---|---|
| 1 | **MODIFICAR no modificaba nada** | `revisar(decision="modificada")` solo ponía el estado y guardaba el comentario en `resultado` |
| 2 | **Sin control de concurrencia** | `grep "transaction\|select_for_update" operaciones/*.py` → **0 resultados** |
| 3 | **`cancelada` era inalcanzable** | el estado está en `ESTADOS` desde M09-C; ninguna función lo asignaba |
| 4 | Permisos sin granularidad | una sola clase para consultar, aceptar, modificar, rechazar |

---

## B. Cambios realizados

### B.1 — La carrera de concurrencia: primero reproducida, después cerrada

No se "arregló por si acaso". Se escribió una prueba contra el código de M09-D
**sin tocar**, que ejecuta el escenario textual del §12:

```
A carga la propuesta.  B carga la misma propuesta.
A acepta.              B rechaza.
```

Resultado medido el 17/09/2026, **antes** de cualquier cambio:

```
  estado final en la base : rechazada        <-- ganó el último
  decisiones auditadas    : 2                <-- debería ser 1
    - REJECTED: propuesta -> rechazada
    - APPROVED: propuesta -> aceptada
```

Dos decisiones contradictorias sobre la misma fila. La causa: `revisar`
comprobaba `propuesta.estado` sobre **la copia que ya tenía en memoria**, y dos
peticiones HTTP cargan cada una la suya con `get_object_or_404`.

El cierre es un bloqueo **de base**, no de proceso — dos contenedores del
backend detrás de un balanceador no comparten memoria, pero sí comparten
Postgres:

```python
with transaction.atomic():
    fresca = PropuestaSupervisor.objects.select_for_update().get(pk=propuesta.pk)
    if fresca.estado != PropuestaSupervisor.PROPUESTA:
        raise YaRevisada(...)
```

`YaRevisada` hereda de `ValueError` a propósito: la vista ya contestaba 400 ante
un `ValueError`, y que sea una clase propia permite distinguirla **sin leer el
texto del mensaje**.

### B.2 — MODIFICAR ahora modifica, con lista blanca

```python
CAMPOS_MODIFICABLES = frozenset({
    "accion_propuesta", "motivo", "prioridad", "impacto",
    "responsable_sugerido", "observaciones",
})
```

Lista **blanca**, no negra, por el mismo motivo que la de campos de WispHub: con
lista negra, un campo nuevo del modelo queda editable por defecto, y el día que
alguien agregue `ejecutar_ahora` nadie se entera.

Un campo fuera de la lista **se rechaza**, no se filtra en silencio: ignorar un
campo que el revisor creyó estar cambiando es peor que negarse, porque el
revisor se va convencido de que lo cambió.

### B.3 — Tres campos nuevos

| Campo | Para qué | Quién escribe |
|---|---|---|
| `responsable_sugerido` (FK Profile) | a quién propone el revisor | **solo un humano** |
| `observaciones` (Text) | contexto que el sistema no podía saber | **solo un humano** |
| `propuesta_original` (JSON) | copia literal de lo que recomendó la IA | el sistema, **una sola vez** |

`responsable_sugerido` **no está** en `CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR`, y eso
es lo que hace cumplir la regla de M09-C: el Supervisor describe condiciones, no
señala personas. Que exista la columna no habilita a la IA a usarla — lo que la
habilitaría sería escribirla, y ninguna ruta suya lo hace.

`propuesta_original` no es redundante con la auditoría. La auditoría registra la
transición; reconstruir desde ella la recomendación original exige encadenar
renglones hacia atrás y confiar en que ninguno falte. Y el Shadow Mode existe
justamente para **comparar lo que la IA propuso contra lo que el humano
decidió**: si esa comparación depende de una reconstrucción, no se puede medir.

### B.4 — `cancelar()`: el estado que no se podía alcanzar

`cancelada` estaba declarado desde M09-C y **ninguna función lo escribía**. Un
estado que no puede ocurrir es una promesa que el modelo no cumple, y la métrica
"canceladas" del §15 habría contado cero para siempre sin que ese cero
significara nada.

### B.5 — Una ruta nueva

```
POST /api/operaciones/propuestas/<id>/cancelar/
```

Aparte de `revisar` porque no es una decisión sobre el fondo: nadie opinó si la
recomendación era buena.

---

## C. Permisos

**No se inventó ningún permiso nuevo.** La granularidad se midió y se documenta
tal como es — medida **por HTTP contra las rutas**, no leyendo la clase de
permiso, porque lo que protege al sistema es lo que contesta el servidor.

| Rol | Consultar | Aceptar | Modificar | Rechazar | Cancelar | Administrar la org |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| ADMIN | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| SUPERVISOR | ✔ | ✔ | ✔ | ✔ | ✔ | ✘ |
| OPERACIONES (Jefe de Operaciones) | ✔ | ✔ | ✔ | ✔ | ✔ | ✘ |
| USER | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Sin sesión | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |

**Consultar y revisar comparten la misma puerta.** Es el modelo real, no un
descuido detectado: quien puede ver las recomendaciones del Supervisor es quien
puede decidir sobre ellas. Separarlas exigiría una segunda clase de permiso y
una decisión de producto que este paso no tiene mandato para tomar — **queda
documentado como pendiente (M-2), no implementado**.

**Revisar no es administrar**: `Profile.save()` deriva
`is_organization_admin = (role == "ADMIN")`, así que un Jefe de Operaciones pasa
el guardia de revisión sin quedar administrador. Medido, no supuesto.

---

## D. Estados

```
                        ┌──────────────┐
                        │  PROPUESTA   │  la IA la creó
                        └──────┬───────┘
          ┌──────────────┬─────┴─────┬──────────────┬──────────────┐
          ▼              ▼           ▼              ▼              ▼
     ┌─────────┐   ┌──────────┐ ┌─────────┐   ┌──────────┐   ┌──────────┐
     │ACEPTADA │   │MODIFICADA│ │RECHAZADA│   │ EXPIRADA │   │CANCELADA │
     └─────────┘   └──────────┘ └─────────┘   └──────────┘   └──────────┘
      un humano     un humano    un humano     nadie la      dejó de tener
      está de       la corrigió  dijo que no   miró a         sentido
      acuerdo                                  tiempo         mirarla
```

Los cinco finales son **terminales**: ninguno vuelve a `propuesta`, y ninguno
transiciona a otro.

### Los tres "no" no son sinónimos

| Estado | ¿Hay revisor? | ¿Hay motivo? | Qué dice |
|---|:--:|:--:|---|
| RECHAZADA | **sí** | **sí** | un humano la miró y dijo que no |
| EXPIRADA | no | no | nadie la miró a tiempo |
| CANCELADA | no | **sí** | la condición desapareció; nadie opinó |

`cancelar` **no escribe `revisado_por`** a propósito: cancelar no es una
decisión humana sobre el fondo, y firmar con el nombre de alguien sería
atribuirle una opinión que no dio.

### `ejecutada` sigue sin existir

No es un estado del modelo, no hay ruta que lleve a él, y `ejecutar_propuesta`
levanta. Las tres cosas juntas, no una sola.

**ACEPTADA ≠ EJECUTADA · MODIFICADA ≠ EJECUTADA · RECHAZADA ≠ EJECUTADA.**
Comprobado además sobre el ruteador entero: los nombres de ruta son exactamente
`{propuestas, propuesta-detalle, propuesta-revisar, propuesta-cancelar, ciclo}`
y ninguno contiene `ejecutar`, `aplicar` ni `despachar`.

---

## E. Auditoría

Cada decisión humana deja un renglón en `common.Activity`, **dentro de la misma
transacción que el cambio**: si no se puede anotar, la transición no ocurre.

Las ocho cosas exigidas por el §10, comprobadas una por una sobre las tres
decisiones:

| Exigido | Dónde queda |
|---|---|
| actor | `Activity.user` (el Profile) |
| organización | `Activity.org` |
| propuesta | `Activity.entity_id` + `entity_type` |
| estado anterior | `metadata.estado_anterior` |
| estado nuevo | `metadata.estado_nuevo` |
| fecha/hora | `Activity.created_at` |
| motivo | `metadata.motivo` |
| evidencia | intacta en la propuesta — nunca se toca |

Verbos: `APPROVED` / `REJECTED` / `UPDATE` / `STATUS_CHANGED`. Ninguno inventado:
ya estaban en el registro de `Activity`.

**Modificar registra antes/después por campo:**

```json
"cambios": {"prioridad": {"antes": 42, "despues": 7}}
```

**Nada cambia en silencio**: hay una prueba que recorre los cuatro finales
(aceptada, rechazada, expirada, cancelada) y exige **exactamente un renglón**
por cada uno. Si mañana alguien agrega un quinto estado y olvida auditarlo, esa
prueba lo caza.

---

## F. Deduplicación

No se tocó — se **revalidó** que sigue correcta con los estados nuevos.

| Situación | ¿Vuelve a proponerse? | Por qué |
|---|:--:|---|
| Rechazada, misma huella | **no** | rechazar es una decisión; repetir la pregunta la ignora |
| Rechazada, huella nueva | **sí** | es otra condición, que nadie ha juzgado |
| Aceptada / Modificada | no | `ESTADOS_QUE_BLOQUEAN` |
| **Expirada** | **sí** | nadie la miró: volver a preguntar es lo correcto |
| **Cancelada** | **sí** | si la condición reaparece, es nueva |

`ESTADOS_QUE_BLOQUEAN = (PROPUESTA, ACEPTADA, MODIFICADA, RECHAZADA)` — sin
cambios respecto de M09-D. `cancelada` queda fuera por diseño, igual que
`expirada`.

---

## G. Concurrencia

Regla: **la primera decisión es la única.**

No se eligió "la última gana", ni "aceptar dos veces es idempotente y rechazar
dos veces no". Una sola regla para los cinco pares posibles, porque el revisor
tiene que poder predecir qué pasó con un doble clic **sin saber cuál de los dos
botones apretó**.

| Primera | Segunda | Resultado |
|---|---|---|
| ACEPTAR | ACEPTAR | 409, estado sigue `aceptada`, **1** renglón |
| RECHAZAR | RECHAZAR | 409, estado sigue `rechazada`, **1** renglón |
| ACEPTAR | RECHAZAR | 409, estado sigue `aceptada`, **1** renglón |
| RECHAZAR | ACEPTAR | 409, estado sigue `rechazada`, **1** renglón |
| MODIFICAR | ACEPTAR | 409, estado sigue `modificada`, **1** renglón |

**409 y no 400**: la petición era válida; lo que cambió fue el mundo entre que el
revisor abrió la pantalla y apretó el botón. Un 400 le diría "te equivocaste" a
alguien que no se equivocó, y el doble clic es el caso más común de los dos. La
respuesta incluye `estado_actual` para que la pantalla se pueda refrescar sola.

Probado de tres formas: dos instancias en memoria (el escenario §12 literal),
**dos hilos reales con dos conexiones** peleándose la fila, y dos POST por HTTP.

---

## H. Aislamiento entre organizaciones

Las dos capas, medidas por separado.

**Capa de aplicación** (por HTTP, con un cliente autenticado de la org A contra
objetos de la org B):

| Intento | Resultado |
|---|---|
| Ver una propuesta de B | **404** (no 403: un 403 confirma que el id existe) |
| Revisar una propuesta de B | **404**, y B queda en `propuesta` sin revisor |
| Cancelar una propuesta de B | **404**, y B queda en `propuesta` |
| Listar | solo las propias; `count` == las de la org A |
| Sugerir un responsable de B | **400**, no se escribe nada |

Esa última fila importa: la edición humana **no es una puerta lateral** al
aislamiento. El responsable sugerido se busca acotado a la organización de quien
pide, y además el dominio lo revalida.

**Capa de base**, medida contra el catálogo y no supuesta:

```
operaciones_propuesta_supervisor:  RLS habilitada = true
                                   RLS forzada    = true
                                   políticas      >= 1
```

Esto es **la diferencia con las tablas `campo_*`** que M09-E reportó sin RLS: la
tabla propia de M09 sí está aislada a nivel de base. Las `campo_*` siguen sin
estarlo — ver sección L.

---

## I. Pruebas

Archivo nuevo: [test_m09f_gobernanza.py](django-crm/backend/operaciones/tests/test_m09f_gobernanza.py)
— 50 funciones, **83 casos** con parametrización.

| Cobertura exigida por el §17 | Casos | Resultado |
|---|:--:|:--:|
| Consulta autorizada / no autorizada | 4 + 1 | ✔ |
| Aceptar | 4 | ✔ |
| Modificar | 12 | ✔ |
| Rechazar | 4 | ✔ |
| Expirar | 3 | ✔ |
| Cancelar | 8 | ✔ |
| Deduplicación | 4 | ✔ |
| Nueva evidencia | 2 | ✔ |
| Tenant isolation | 5 | ✔ |
| Auditoría | 5 | ✔ |
| Concurrencia | 2 | ✔ |
| Doble decisión | 6 | ✔ |
| Cero efectos externos | 7 | ✔ |

```
83 passed in 154.65s
```

### Regresiones: ninguna, y medido en dos pasos

Suite completa `operaciones/ + common/ + campo/`:

```
1516 passed, 13 failed, 6 skipped   (0:21:03)
```

Ninguno de los 13 fallos está en `operaciones/` ni en `campo/` — los 13 son de
`common/`. Pero eso solo es un indicio, no una demostración, y la FK nueva
apunta a `Profile`, así que `test_delete_user_as_admin` fallando **podía** ser
mía. Se midió en vez de suponerlo:

1. Se leyeron los errores: 12 de 13 eran
   `redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379`.
   El entorno aislado no tenía Redis.
2. Se levantó Redis y se volvieron a correr esas 13:

```
58 passed, 1 failed
FAILED common/tests/test_credenciales_postgres.py::
       test_la_guarda_detecta_que_el_rol_no_puede_alterar_lo_que_hay
       AssertionError: deberia detectar tablas ajenas; devolvio []
```

El único fallo que sobrevive es **el defecto preexistente de la Etapa B.4**, ya
reportado en M09-E y ajeno a este paso. Además, los campos nuevos
(`responsable_sugerido`, `propuesta_original`, `propuestas_sugeridas`) no
aparecen **ni una vez** en la salida de la suite completa.

**Regresiones introducidas por M09-F: 0.**

**La prueba de la prueba.** Hay un caso que desarma el espía a propósito y
comprueba que grita:

```python
def test_el_espia_si_detecta_una_llamada(espia_requests):
    with pytest.raises(AssertionError):
        requests.get("http://ejemplo.invalido/")
    assert len(espia_requests) == 1
```

Sin él, "0 llamadas" podría significar "el espía no estaba puesto" — que es
exactamente el error que M09-E documentó como riesgo.

---

## J. Efectos externos

Espía sobre `requests` **y sobre `requests.sessions.Session`** (9 métodos cada
uno), que **cuenta y levanta**: una prueba que solo cuenta puede terminar en
verde con la llamada ya hecha.

| Operación | Llamadas externas |
|---|:--:|
| ACEPTAR | **0** |
| MODIFICAR | **0** |
| RECHAZAR | **0** |
| EXPIRAR | **0** |
| CANCELAR | **0** |
| Ciclo completo por HTTP | **0** |

Además, sobre cada decisión: `accion_propuesta_ref` queda en `""`, y la respuesta
de la API dice `"ejecutada": false` explícitamente.

**La misma salvedad de M09-E sigue en pie**: el ejecutor del motor no está
montado en este contenedor, así que lo que se afirma es *"ninguna decisión humana
sale por `requests`"*, no *"se probó el ejecutor del motor"*.

---

## K. Migraciones

**Una, aditiva, y NO aplicada en producción.**

`operaciones/migrations/0004_m09f_gobernanza.py`:

```
AddField  propuestasupervisor.observaciones         TextField(default="")
AddField  propuestasupervisor.propuesta_original    JSONField(default=dict)
AddField  propuestasupervisor.responsable_sugerido  FK(Profile, null=True)
```

Operaciones destructivas (`RunPython`, `RunSQL`, `DeleteModel`, `RemoveField`,
`AlterField`): **0**. Sin índices nuevos, sin backfill, sin cambio de tipo.

Estado de producción al cerrar el paso:

```
ledger                : 50
kill switch           : detenido
filas ACTIVO          : 0
PropuestaSupervisor   : 0
acciones_propuestas   : 40
django_migrations     : 192
columnas M09-D/F      : NINGUNA
perfiles por rol      : {ADMIN: 1, USER: 4}
```

Ni la migración de M09-D (0040/0003) ni la de M09-F (0004) están aplicadas.
Producción no se tocó.

---

## §15 · Métricas definidas (sin implementar dashboards)

Definiciones, no código. Ninguna es un ranking ni un score de persona.

| Métrica | Definición exacta |
|---|---|
| Propuestas pendientes | `estado = 'propuesta'` y (`expira_en` nulo o futuro) |
| Tiempo hasta revisión | `revisado_en − created_at`, solo sobre las que tienen `revisado_en`. Se reporta **mediana y p90**, nunca promedio: una propuesta olvidada tres semanas mueve el promedio y no describe al resto |
| Aceptadas / Modificadas / Rechazadas | conteo por `estado`, sobre las que **sí** fueron revisadas |
| Expiradas | `estado = 'expirada'` — mide **la cola sin atender**, no el desempeño de nadie |
| Canceladas | `estado = 'cancelada'` — mide **condiciones que se resolvieron solas** |
| Tasa de revisión | revisadas ÷ (revisadas + expiradas). El denominador excluye canceladas: nadie dejó de revisar algo que dejó de existir |
| Propuestas con nueva evidencia | mismas `(tipo_senal, origen_tipo, origen_id)` con `huella_condicion` distinta de una anterior |
| Duplicadas evitadas | `correr_ciclo(...)["repetidas"]`, acumulado por ciclo |

**Lo que estas métricas NO son.** Ninguna se agrupa por `revisado_por` ni por
`responsable_sugerido`. Una tasa de rechazo alta puede significar que la IA
recomienda mal, que el revisor conoce contexto que el sistema no tiene, o que la
ventana de detección está mal calibrada — y un ranking de personas elegiría en
silencio la interpretación que más daño hace. Es la misma regla que impide la
señal `incumplimiento_de_persona`.

---

## L. Riesgos

| # | Riesgo | Estado |
|---|---|---|
| L-1 | **7 tablas `campo_*` sin RLS** | Heredado de M09-E. La tabla propia de M09 **sí** tiene RLS forzada, pero las órdenes de trabajo que M09 lee no. Dependencia de M10; no se tocó |
| L-2 | El ejecutor del motor no instrumentado | Heredado de M09-E, sin cambios |
| L-3 | Cobertura de datos reales M02/M03 nula | Heredado de M09-E, sin cambios |
| L-4 | `expirar_vencidas` solo corre dentro de `correr_ciclo` | Si nadie dispara el ciclo, nada expira. Hoy el ciclo es una ruta manual — a propósito: engancharlo al scheduler sería darle al Supervisor la capacidad de correr solo |
| L-5 | Consultar y revisar comparten puerta | Documentado en C. No es un defecto; es una decisión de producto no tomada |
| L-6 | `select_for_update` sin `nowait` | Dos revisores simultáneos hacen que el segundo **espere**, no que falle al instante. Con el volumen actual (decisiones humanas, no tráfico) es irrelevante; si algún día se automatiza, revisarlo |

---

## M. Pendientes

| # | Qué | Cuándo |
|---|---|---|
| M-1 | Aplicar `0040_m09d` + `0003_m09d` + `0004_m09f` en producción | requiere autorización explícita; **no** en este paso |
| M-2 | Decidir si consultar y revisar deben separarse | decisión de producto |
| M-3 | Pantalla de revisión (hoy la gobernanza es API) | cuando haya usuarios revisando de verdad |
| M-4 | Revalidar los 9 detectores de M02/M03 con datos reales | cuando esos módulos operen |
| M-5 | Instrumentar el ejecutor del motor | antes de cualquier nivel de autonomía |

---

## N. Decisión final

Los once criterios del §19, uno por uno:

| Criterio | Medido | |
|---|---|:--:|
| El Jefe de Operaciones puede revisar | ADMIN/SUPERVISOR/OPERACIONES → 200 por HTTP | ✔ |
| Las decisiones quedan auditadas | 8 campos exigidos, en las 3 decisiones | ✔ |
| La evidencia original permanece intacta | no es editable; se rechaza el intento | ✔ |
| Aceptar no ejecuta | 0 llamadas, `accion_propuesta_ref` vacío | ✔ |
| Modificar no ejecuta | 0 llamadas | ✔ |
| Rechazar no ejecuta | 0 llamadas | ✔ |
| Doble decisión controlada | 5 pares → 409, 1 sola decisión | ✔ |
| Concurrencia controlada | `select_for_update`; 2 hilos → 1 decisión | ✔ |
| Deduplicación correcta | 5 situaciones revalidadas | ✔ |
| Tenant isolation | 404 por aplicación + RLS forzada en base | ✔ |
| 0 efectos externos | 6 operaciones, espía que grita | ✔ |

### Veredicto

## GO

El ciclo humano de revisión queda **cerrado y probado**. Lo que este paso
encontró y arregló no era cosmético: **la carrera de concurrencia era real, se
reprodujo antes de tocarla** (dos decisiones contradictorias sobre la misma
fila, la última ganando), y MODIFICAR era una etiqueta que no modificaba nada.

**Lo que este GO autoriza:** dar por correcto el ciclo de gobernanza humana.

**Lo que este GO NO autoriza:** desplegar código, aplicar ninguna migración en
producción, activar ningún nivel de autonomía, ni describir las órdenes de
trabajo como aisladas a nivel de base de datos.

---

### Anexo — cómo se corrió

Base aislada `pg-m09f` (PostgreSQL 16.14, puerto 15498), nunca producción: el
`.env` de la raíz apunta a Supabase y por eso las variables de base se pasaron
explícitas en cada ejecución.

```
línea base (antes de tocar nada)   operaciones/tests/      97 passed
suite M09-F                        test_m09f_gobernanza    83 passed
suite completa                     operaciones+common+campo  1516 passed, 13 failed
las 13, con Redis levantado        (12 eran Redis ausente)   58 passed,  1 failed
```

Ese 1 que queda es el defecto preexistente de la Etapa B.4. Contenedores
`pg-m09f` y `redis-m09f` eliminados al cerrar el paso.
