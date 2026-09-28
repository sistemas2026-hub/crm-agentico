# D-1 — Fuente canónica de habilidades

# ESTADO: AUDITORÍA / NO IMPLEMENTADO

**Fecha:** 2026-09-17
**Naturaleza:** auditoría de código + decisión arquitectónica. No se modificó
código, ni tablas, ni migraciones, ni modelos, ni endpoints, ni producción, ni
PostgreSQL, ni permisos, ni autonomía, ni `PropuestaSupervisor`, ni
`asistente.habilidades`. No se crearon habilidades ni asistentes.
Contra producción, **solo lecturas**.

**Etiquetas:** **[MEDIDO]** · **[DISEÑO]** · **[DEPENDENCIA]** · **[RIESGO]** ·
**[PENDIENTE]**

---

## 1. Resumen ejecutivo

**[MEDIDO]** La afirmación que M09-J tomó del docstring —*"una habilidad no
ejecuta nada: es texto que entra al prompt"*— **se verificó en código y es
cierta**: el índice entra como mensaje `system` y `cargar_habilidad` devuelve un
diccionario con `pasos` (texto). No hay ninguna ruta de ejecución.

**[MEDIDO]** Pero la auditoría encontró algo que cambia la decisión: **una
habilidad del Motor y un detector de M09 no son el mismo concepto**, y no es una
cuestión de nombres.

```
HABILIDAD DEL MOTOR   =  TEXTO que se inyecta en el prompt de un LLM
                          para que un modelo no determinista siga pasos.
                          Su definición es un dato. No tiene código.

"HABILIDAD" DE M09    =  una FUNCIÓN Python determinista que ejecuta una
                          consulta y emite una señal. Su definición ES el código.
```

**[MEDIDO]** Tres hechos de aislamiento que ninguna decisión puede ignorar:

| Hecho | Medición |
|---|---|
| El CRM **no importa nada** de `nucleo/` | `grep "from nucleo" django-crm/backend/` → **0** |
| M09 **no referencia** habilidades | `grep habilidad operaciones/` → **0** |
| `crm_user` **no puede leer** `asistente` | `has_schema_privilege('crm_user','asistente','usage')` = **False** |

> **Conclusión:** no hay duplicación que evitar, porque no hay dos catálogos del
> mismo concepto. Y no hay integración posible sin romper un aislamiento que está
> puesto a propósito.

**[MEDIDO]** Además se encontró **un defecto real en el sistema existente**: los
63 usos tienen `conversation_id` **nulo en los 63**, y `analista.py` hace un
`JOIN` sobre esa columna. Su tercera señal de aprendizaje **devuelve cero
siempre**. Ver §5.3.

**Decisión: Opción D** — M09 no necesita catálogo de habilidades en base. Ver §14.

---

## 2. Evidencia del sistema existente

**[MEDIDO]** API pública del módulo (`nucleo/habilidades/`):

```
catalogo.py   indice_de(tenant, rol)      -> list[EntradaIndice]
              cargar(tenant, rol, codigo) -> Habilidad | None
              registrar_uso(tenant, codigo, rol, conversation_id=None) -> None
              bloque_de_indice(entradas)  -> str
analista.py   propone habilidades nuevas a partir de conversaciones reales
```

**[MEDIDO]** Dos dataclasses, ambas `frozen=True`: `Habilidad(codigo, nombre,
cuando_usarla, pasos)` y `EntradaIndice(codigo, nombre, cuando_usarla)`.
**Ningún campo ejecutable, ningún callable, ninguna referencia a herramienta.**

---

## 3. Auditoría de `asistente.habilidades`

### 3.1 — Estructura **[MEDIDO]**

```
id · organization_id · codigo · nombre · cuando_usarla · pasos
roles_permitidos · estado · version · origen · evidencia
motivo_rechazo · aprobada_por · creada_en · aprobada_en
```

| Aspecto | Medición |
|---|---|
| Habilidades | **5** |
| Vigentes | **1** (`HAB-CAMBIO-NOMBRE-CLAVE-WIFI`) |
| Propuestas | 2 · Obsoletas | 2 |
| Usos | **63** |
| RLS | **habilitada ✔ forzada ✔ 1 política** |
| Ámbito | `organization_id` **y** `roles_permitidos` |
| Migración | no vive en Django: es del esquema `asistente` (motor) |

### 3.2 — Quién la crea, modifica, consulta y consume **[MEDIDO]**

| Operación | Dónde |
|---|---|
| **Crea** | `POST /habilidades` (a mano, nace `propuesta`) · `analista.py` (`origen='analisis'`) |
| **Aprueba** | `POST /habilidades/<id>/aprobar` — **exige roles**: sin roles no la ve nadie |
| **Lista** | `GET /habilidades` (con conteo de usos) |
| **Consulta (caliente)** | `catalogo.indice_de` y `catalogo.cargar` |
| **Consume** | `motor.py:2682` (índice al prompt) y `motor.py:872` (cuerpo por herramienta) |
| **Registra uso** | `motor.py:887` |

### 3.3 — El SQL real, y la doble capa **[MEDIDO]**

```sql
-- indice_de
where organization_id = %s and estado = 'vigente'
  and roles_permitidos is not null and %s = any(roles_permitidos)

-- cargar  (el MISMO filtro, repetido a propósito)
where organization_id = %s and estado = 'vigente' and codigo = %s
  and roles_permitidos is not null and %s = any(roles_permitidos)
```

**[MEDIDO]** El filtro por rol se repite en `cargar` porque *"el código llega en
un argumento que produce el modelo, y un modelo puede nombrar uno que vio en otra
conversación o directamente inventarlo"*. Devuelve `None` tanto para "no existe"
como para "no es tuya" — y esa igualdad **se puede verificar**
(`tests/test_habilidades.py`).

**[MEDIDO]** La columna `version` **existe y el SQL no la usa**: no hay selección
por versión. La versión es documental, no funcional.

---

## 4. ¿Qué significa "habilidad" en el Motor? — respuesta con evidencia

**[MEDIDO]** Las 14 preguntas de la FASE 2:

| # | Pregunta | Respuesta | Evidencia |
|:--:|---|---|---|
| 1 | ¿Es texto/prompt? | **SÍ** | `historial.append({"role":"system","content": bloque_de_indice(...)})` — `motor.py:2689` |
| 2 | ¿Es una función? | **NO** | `Habilidad` es un dataclass `frozen` de 4 strings |
| 3 | ¿Es configuración? | **NO** | vive en tabla propia, no en `tenant_config` |
| 4 | ¿Es una instrucción? | **SÍ** | `pasos` + `instruccion_interna` |
| 5 | ¿Relación asistente↔conocimiento? | **parcial** | `roles_permitidos` la ata al rol; **no** hay FK a documentos |
| 6 | ¿Tiene lógica ejecutable? | **NO** | ningún callable en el modelo ni en la tabla |
| 7 | ¿Puede llamar herramientas? | **NO** *(matiz abajo)* | `cargar` devuelve un dict; el motor no despacha nada desde él |
| 8 | ¿Efectos externos? | **NO** | única escritura: `habilidad_usos` (telemetría) |
| 9 | ¿Tiene versión? | **columna sí, uso no** | `version` existe; el SQL no la consulta |
| 10 | ¿Activación/desactivación? | **SÍ** | `estado`: propuesta / vigente / obsoleta |
| 11 | ¿Ámbito por organización? | **SÍ** | `organization_id` + RLS forzada |
| 12 | ¿Evaluación? | **NO propia** | 84 casos dorados evalúan el motor, no la habilidad |
| 13 | ¿Métricas? | **una**: conteo de usos | `habilidad_usos` |
| 14 | ¿Historial? | **parcial** | `creada_en`, `aprobada_en`, `aprobada_por`; sin historial de ediciones |

### 4.1 — El matiz del punto 7, que importa

**[MEDIDO]** El texto de una habilidad **sí puede indicarle al modelo que use sus
herramientas**: *"si un paso te pide un dato que no tienes, conseguilo con tus
herramientas antes de seguir"*.

**[MEDIDO]** Pero eso **no concede** ninguna herramienta: el modelo solo puede
llamar las de `puede_consultar` de su rol, y toda escritura pasa por la frontera
y el kill switch.

> **La habilidad dirige el uso de permisos que ya existían. Nunca los crea.**
> Es exactamente la separación que la FASE 10 exige, y está construida.

---

## 5. Auditoría de los 63 usos

### 5.1 — Distribución real **[MEDIDO]**

```
HAB-CAMBIO-NOMBRE-CLAVE-WIFI · rol=soporte_tecnico_cliente · 63 usos
ventana: 2026-09-06 → 2026-09-12
usos con conversation_id: 0        ← de 63
```

**Los 63 son una sola habilidad, un solo rol.** Las otras cuatro: **0 usos**.

### 5.2 — Qué se registra **[MEDIDO]**

```
habilidad_usos: id · organization_id · habilidad_id · conversation_id · rol · creado_en
```

No hay resultado, no hay evidencia, no hay evaluación, no hay retroalimentación.
Es **observabilidad**, y el propio código lo declara: *"Es observabilidad, no
parte de la respuesta: si la inserción falla, el cliente no tiene por qué perder
su turno por eso."*

### 5.3 — **[RIESGO] Defecto encontrado: la señal 3 del analista no puede funcionar**

**[MEDIDO]**

```python
# nucleo/habilidades/catalogo.py:131
def registrar_uso(tenant, codigo, rol, conversation_id=None)

# nucleo/modelo/motor.py:887  -- la ÚNICA llamada
catalogo_habilidades.registrar_uso(config.identidad.slug, codigo, nombre_rol)
                                   # ^ sin conversation_id
```

```sql
-- nucleo/habilidades/analista.py:199-201
from asistente.habilidad_usos u
join asistente.conversations c on c.id = u.conversation_id   ← INNER JOIN
```

**[MEDIDO]** `conversation_id` es NULL en las 63 filas → el `JOIN` no empareja
ninguna → **la tercera señal del analista ("habilidad cargada y la conversación
igual escaló") devuelve cero, siempre.**

**[MEDIDO]** Y es justamente la señal que el propio módulo describe como la que
distingue *"falta un procedimiento"* de *"el que hay está mal escrito"*.

> **No lo corregí: este paso es auditoría.** Queda reportado y es una corrección
> de un renglón (pasar el `conversation_id` que el motor ya tiene en ese punto).
> **[PENDIENTE]** decidir si se arregla antes o después de M09-K.

---

## 6. Auditoría de los 8 asistentes

**[MEDIDO]** Los 8 "asistentes" **son** los roles de IA de `tenant_config.roles`.
No hay dos conceptos: *asistente* es el término del informe, *rol* es el término
del código y de la base — `roles_permitidos`, `rol_solicitante`, `nombre_rol`.

| Asistente/rol | Herramientas | Habilidades vigentes que puede cargar | Casos dorados |
|---|---:|:--:|---:|
| `soporte` | 28 | **0** | 10 |
| `soporte_tecnico_cliente` | 21 | **1** | 13 |
| `ventas` | 15 | 0 | 11 |
| `facturacion` | 11 | 0 | 2 |
| `administracion` | 9 | 0 | 4 |
| `facturacion_cliente` | 7 | 0 | 5 |
| `configuracion_guiada` | 2 | 0 | 1 |
| `cliente_final` | 1 | 0 | 38 |

**[MEDIDO]** **Un solo rol de ocho tiene una habilidad vigente.** El resto opera
sin ninguna. Modelo: ninguno declara uno propio. Conocimiento: el corpus (21
docs / 427 fragmentos) es **global al tenant**, no por asistente.

**[MEDIDO]** Las dos `propuesta` y las dos `obsoleta` apuntan a `cliente_final`,
que es el rol con **1 sola herramienta** (`derivar_a_area`) — coherente con que
sean procedimientos de derivación que nunca se aprobaron.

---

## 7. Auditoría de M09

**[MEDIDO]** **M09 no utiliza `asistente.habilidades` de ninguna forma.**

```
grep "habilidad|catalogo" django-crm/backend/operaciones/  →  0 resultados
grep "from nucleo"        django-crm/backend/            →  0 resultados
```

| Pieza M09 | Qué es realmente |
|---|---|
| `supervisor.py` | 10 funciones `_detector(org, ahora) -> list[Senal]` |
| `PropuestaSupervisor` | modelo Django, tabla `public.operaciones_propuesta_supervisor` |
| Detectores | **código Python determinista**, no texto |
| `conocimiento_version` | **[MEDIDO]** campo `CharField(128)`, **vacío en las 52 propuestas** |
| Evidencia | lista JSON con `CheckConstraint` |
| `acciones_propuestas` | tabla del **motor**, 40 filas históricas — M09 solo la referencia por `accion_propuesta_ref`, vacío |
| Herramientas | **ninguna**: M09 solo usa el ORM |

> **No existe integración.** M09 tiene lógica independiente, en otro servicio,
> otro esquema y otro rol de base.

---

## 8. Comparación semántica Motor vs M09

| Característica | Habilidad Motor | "Habilidad" M09 | ¿Mismo concepto? |
|---|---|---|---|
| **Propósito** | que un LLM siga un procedimiento | detectar una condición en datos | **NO** — uno guía a un modelo, el otro evalúa una consulta |
| **Entrada** | situación conversacional | `(org, ahora)` |**NO** |
| **Salida** | texto en el prompt | `list[Senal]` tipada | **NO** |
| **Conocimiento** | el propio texto **es** el conocimiento | conocimiento externo, hoy **sin declarar** | **NO** |
| **Procedimiento** | dato en una tabla | **código** en `supervisor.py` | **NO** — el más decisivo |
| **Herramientas** | dirige el uso de las del rol | ninguna; ORM directo | NO |
| **Evidencia** | ninguna estructurada | **obligatoria**, con `CheckConstraint` | **NO** |
| **Evaluación** | 84 casos dorados sobre el motor | 83 pruebas + validación M09-E | parcial |
| **Versionamiento** | columna `version` sin uso | `conocimiento_version` vacío | **ambos sin usar** |
| **Tenant** | `organization_id` + RLS forzada | `org` + RLS forzada | **SÍ** |
| **Autonomía** | no ejecuta (texto) | no ejecuta (`ejecutar_propuesta` levanta) | **SÍ** |
| **Auditoría** | `habilidad_usos` (telemetría) | `common.Activity` (transiciones) | NO |

### 8.1 — Lo que decide la comparación

**[MEDIDO]** Coinciden en **tres** características de doce, y las tres son
**propiedades transversales del sistema** (tenant, no-ejecución, auditoría), no
del concepto de habilidad.

**Difieren en la que define la naturaleza de la cosa:** el procedimiento del
Motor **es un dato**; el de M09 **es código**.

> **[RIESGO]** Y ese contraste ya tiene doctrina escrita en este repositorio.
> `nucleo/programador/registro.py` rechazó exactamente esta mezcla:
>
> *"un 'job_code' que llega de una fila de la base terminando en una búsqueda que
> resuelve a un callable convierte al catálogo —un dato— en código ejecutable. El
> catálogo lo edita un operador; el código lo revisa alguien."*
>
> Poner los detectores de M09 en una tabla repetiría ese error.

---

## 9. Análisis de duplicación — las 14 habilidades de M09-J

**[MEDIDO]** Ninguna de las 14 tiene equivalente en `asistente.habilidades`. Las
5 existentes son: cambio de WiFi, dos de atención de TV/reconexión, una de
derivación por problemas de conexión, y una de frustración escalada — **todas
conversacionales, con cliente final**.

| ID M09-J | ¿Existe equivalente? | Dónde | Veredicto |
|---|---|---|---|
| H-01 caso abierto antiguo | **no** | `_casos_abiertos_antiguos` (código) | **reutilizar el código, documentarlo** |
| H-02 completitud de datos | **no** | `_ordenes_desincronizadas` | ídem |
| H-03 programación vigente | **no** | `_ordenes_sin_programar` | ídem |
| H-04 plan sin publicar | **no** | `_programaciones_sin_publicar` | ídem |
| H-05 riesgo por capacidad | **parcial** | `_ordenes_en_riesgo` existe; **falta el conocimiento** | extender |
| H-06…H-10 | **no** | los 5 detectores M02/M05 | documentar |
| H-C1 prioridad | **no** | `_prioridad(base, componentes)` | **ya es función única** |
| H-C2 evidencia | **no** | `_observacion(...)` | ya es función única |
| H-C3 huella | **no** | `Senal.huella` + `_ya_propuesta` | ya es función única |
| H-C4 sin culpa | **no** | regla M09-C + 13 patrones en prueba | **solo existe como prueba** |

**[MEDIDO]** **Duplicación real: cero.** Las 14 ya existen **como código
funcionando**; lo que falta es su ficha documental, no su implementación.

**[RIESGO]** La duplicación que sí podría crearse es la contraria: **registrar
las 14 en una tabla crearía dos definiciones** —el código y la fila— que
divergirían en el primer cambio.

---

## 10. Análisis de integración Motor ↔ CRM

**[DISEÑO]** Qué pasaría si M09 leyera `asistente.habilidades` directamente:

| Dimensión | Consecuencia |
|---|---|
| **Código** | **[MEDIDO]** el CRM tendría que importar `nucleo/` — hoy son **0** imports. Rompe la separación de ARQUITECTURA.md |
| **Base de datos** | **[MEDIDO]** `crm_user` **no tiene USAGE sobre `asistente`**. Hoy solo funcionaría por ser `postgres`, y **B-7 lo cerraría** |
| **Despliegue** | son contenedores distintos con credenciales distintas (`DBUSER` vs `MOTOR_DBUSER`) |
| **Tenant** | compatible: ambos por `organization_id` con RLS forzada |
| **Versionamiento** | el Motor no versiona en el SQL; M09 necesitaría versión para `conocimiento_version` |
| **Cambios** | aprobar una habilidad en el Motor cambiaría el comportamiento de M09 sin pasar por su ciclo de revisión |
| **Rollback** | **[RIESGO]** revertir un despliegue del CRM no revertiría una fila del Motor |
| **Auditoría** | dos registros distintos (`habilidad_usos` vs `common.Activity`) sin punto de unión |
| **Rendimiento** | una consulta más por ciclo; irrelevante |
| **Aislamiento** | **se perdería**: hoy el CRM no puede ver el esquema del motor, y es deliberado |
| **Seguridad** | exigiría concederle a `crm_user` acceso a `asistente` — **lo contrario de B-7** |
| **Fallo del Motor** | **[RIESGO]** M09 dejaría de detectar si el esquema del motor no responde. Hoy son independientes |
| **Fallo del CRM** | el motor no se entera. Sin cambio |

> **[MEDIDO] La reutilización directa no es técnicamente viable sin deshacer B-7.**
> El aislamiento que impide la integración es el mismo que B-7 existe para
> reforzar. Integrar sería avanzar en una dirección y retroceder en la otra.

---

## 11. Análisis de versionamiento

**[MEDIDO]** Estado actual: `habilidades.version` existe y **el SQL no la usa**;
`PropuestaSupervisor.conocimiento_version` existe y **está vacío en las 52
propuestas** de M09-E.

**[DISEÑO]** Qué debería versionarse, y qué no:

| Elemento | ¿Versionar? | Por qué |
|---|:--:|---|
| **Habilidad (el detector)** | **sí** | si cambia la condición, cambian las señales |
| **Conocimiento** (umbral, definición) | **sí** | 7 días vs 10 días producen colas distintas |
| **Procedimiento** | **sí, junto con la habilidad** | son la misma cosa cuando el procedimiento es código |
| **Prompt** | **no aplica** a M09 | M09 no usa modelo |
| **Combinación** | **sí, y es lo que hay que guardar** | ver abajo |

**[DISEÑO]** La referencia mínima que debería quedar registrada para responder
*"¿qué conocimiento y qué habilidad usó la IA cuando generó esta
recomendación?"*:

```
conocimiento_version = "H-01@3 · umbral-caso-antiguo@1"
                        │      │    │                 └── versión del documento
                        │      │    └── conocimiento aplicado
                        │      └── versión de la habilidad
                        └── identificador de la habilidad
```

**[DISEÑO]** Tres propiedades exigibles:

1. **Una sola cadena, en un campo que ya existe.** No hace falta tabla.
2. **Debe cambiar cuando cambie la condición**, no en cada despliegue: una
   versión que se mueve sola entrena a la gente a ignorarla.
3. **Debe poder resolverse hacia atrás**: `H-01@3` tiene que seguir siendo
   legible dentro de un año, aunque la habilidad vaya por la @7.

---

## 12. Análisis multitenant

**[MEDIDO]**

| Pregunta | Respuesta |
|---|---|
| ¿Hay aislamiento? | **SÍ**: `organization_id` + RLS **habilitada y forzada**, 1 política |
| ¿Una habilidad es global? | **NO** |
| ¿Por organización? | **SÍ** — `organization_id` obligatorio, filtrado en las 3 consultas |
| ¿Por asistente? | **SÍ** — `roles_permitidos` (array), verificado **dos veces** |
| ¿Por combinación? | **SÍ, y es el modelo real: (organización × rol × estado vigente)** |

**[RIESGO]** El aislamiento de base es **hoy inefectivo para el runtime del
motor**: `motor_user` tiene `BYPASSRLS = true` (medido en B-7). El aislamiento
que sí opera es el del SQL, que filtra explícitamente por `organization_id`.
Es la misma clase de hallazgo que B-7 §B.1, y **no se resuelve aquí**.

---

## 13. Opciones A / B / C / D

### Opción A — `asistente.habilidades` como fuente canónica de ambos

| | |
|---|---|
| **Ventajas** | una sola tabla; reutiliza el flujo de aprobación |
| **Desventajas** | obliga a representar código como dato |
| **Riesgos** | **[MEDIDO]** exige darle a `crm_user` acceso a `asistente` — deshace B-7; acopla M09 a la disponibilidad del motor |
| **Dependencias** | B-7 en sentido contrario |
| **Impacto** | alto y estructural |
| **Esfuerzo** | alto |
| **Una sola verdad** | **no la logra**: el detector seguiría siendo código |
| **Veredicto** | **RECHAZADA por medición** |

### Opción B — Motor con la suya, M09 con estructura propia (leída como "otra tabla")

| | |
|---|---|
| **Ventajas** | respeta el aislamiento; cada sistema evoluciona solo |
| **Desventajas** | **crea una segunda definición del detector**: la fila y el código |
| **Riesgos** | **[RIESGO]** divergencia en el primer cambio; es el error de `registro.py` |
| **Una sola verdad** | **no la logra** |
| **Veredicto** | **RECHAZADA en su lectura literal** |

### Opción C — Catálogo común para ambos

| | |
|---|---|
| **Ventajas** | una fuente conceptual |
| **Desventajas** | fuerza un concepto común donde la comparación (§8) mostró **9 diferencias de 12** |
| **Riesgos** | acopla despliegues; exige un esquema nuevo accesible a dos roles que hoy están separados a propósito |
| **Esfuerzo** | el más alto |
| **Veredicto** | **RECHAZADA: uniría dos cosas que no son la misma** |

### Opción D — **M09 no necesita catálogo de habilidades en base**

| | |
|---|---|
| **Qué es** | la definición canónica de una habilidad de M09 **es su código**, más un **registro literal congelado** y una **versión** estampada en `conocimiento_version` |
| **Ventajas** | **una sola verdad por construcción**; cero tablas; cero acoplamiento; respeta B-7; tiene **precedente en el repositorio** (`programador/registro.py`) |
| **Desventajas** | cambiar una habilidad exige despliegue, no una fila |
| **Riesgos** | **bajo**: no cambia comportamiento |
| **Dependencias** | ninguna. **No depende de B-7 ni de M10** |
| **Esfuerzo** | bajo: documentación + un registro + poblar un campo existente |
| **Migración** | **ninguna** |
| **Compatibilidad** | total: no toca `asistente.habilidades` ni `PropuestaSupervisor` |
| **Veredicto** | **RECOMENDADA** |

**[DISEÑO]** Y la desventaja de D es en realidad una propiedad buscada: un
detector que cambia **debe** pasar por revisión de código y pruebas. Los 10
detectores ya tienen 83 pruebas; una fila editable no las tendría.

---

## 14. Recomendación

> ## FUENTE CANÓNICA PROPUESTA: **el código de M09, con registro literal y versión** *(Opción D)*

**[DISEÑO]** Las diez preguntas de la FASE 13:

| # | Pregunta | Respuesta |
|:--:|---|---|
| 1 | ¿Reutilizamos `asistente.habilidades`? | **NO.** `crm_user` no puede leerla y son conceptos distintos |
| 2 | ¿La extendemos? | **NO.** Sigue siendo del motor y no se toca |
| 3 | ¿Creamos una capa de referencia? | **NO en base.** Sí una **documental**: la ficha de cada habilidad |
| 4 | ¿M09 debe tener representación propia? | **Sí, en código**: registro literal congelado, no tabla |
| 5 | ¿Cómo evitamos duplicar? | **No creando la segunda definición.** El código es la única |
| 6 | ¿Una sola verdad? | por construcción: la habilidad **es** la función |
| 7 | ¿Habilidad ↔ conocimiento? | por la cadena `conocimiento_version`, con documento versionado |
| 8 | ¿Qué versión produjo la propuesta? | `conocimiento_version = "H-01@3 · umbral@1"` — campo que **ya existe** |
| 9 | ¿Permiso de ejecución separado? | **ya lo está**: ninguna habilidad de M09 toca una herramienta, y la autorización vive en la frontera |
| 10 | ¿Evitar acoplar Motor y CRM? | **no integrándolos.** Hoy hay 0 imports y 0 privilegios cruzados |

**[DISEÑO]** Lo único **compartido** entre los dos sistemas es el **vocabulario**,
no la infraestructura:

```
código · nombre · cuando_usarla · pasos · evidencia · estado · version
```

Que M09 use los mismos nombres de campo hace que las dos mitades se lean igual.
**Compartir el contrato no exige compartir la tabla** — y es el mismo criterio
por el que `operaciones/permissions.py` **importa** `ROLES_GESTION` en vez de
copiarlo: se comparte lo que debe ser idéntico, no lo que solo se parece.

---

## 15. Decisión D-1

```
DECISIÓN D-1:

    [ ] A — reutilizar asistente.habilidades
    [ ] B — estructura propia M09 (tabla)
    [ ] C — catálogo común
    [X] D — otra:  el código de M09 es la fuente canónica.
                   Registro literal congelado + versión en conocimiento_version.
                   CERO tablas nuevas. CERO integración con el motor.
```

**Por qué, en una línea:** porque **el procedimiento del Motor es un dato y el de
M09 es código**, y los tres caminos que los unifican exigen tratar código como
dato —lo que este repositorio ya rechazó por escrito— o deshacer el aislamiento
que B-7 refuerza.

### ¿M09-K puede comenzar después de este informe?

## SÍ

**[DISEÑO]** D-1 queda resuelto y M09-K no necesita ninguna decisión adicional
para su alcance mínimo:

| # | Alcance habilitado | Toca |
|---|---|---|
| 1 | Escribir la ficha de las 10 habilidades de dominio y las 4 transversales | **documentación** |
| 2 | Crear el registro literal congelado `HABILIDADES = {...}` en `operaciones/` | código, sin cambio de comportamiento |
| 3 | Poblar `conocimiento_version` al registrar una propuesta | un campo que ya existe |

**[PENDIENTE]** Lo que **no** entra en M09-K y sigue necesitando decisión:

| # | Decisión | Bloquea |
|---|---|---|
| **D-2** | Quién aprueba un cambio de habilidad operativa (en el motor es `aprobada_por`) | el ciclo de gobierno, no M09-K |
| **D-3** | Los 5 documentos de conocimiento (M09-J FASE 7) | la parte de `conocimiento_version` que cita documentos |
| **D-4** | Definición de capacidad operativa | **solo H-05** |
| **D-5** | ¿Se arregla `conversation_id` en `registrar_uso`? (§5.3) | nada de M09-K; es del motor |

---

## 16. Riesgos

| # | Riesgo | Evidencia | Mitigación | ¿Bloquea? |
|---|---|---|---|:--:|
| R-1 | **Tratar código como dato** | `registro.py` ya lo rechazó | Opción D | evitado |
| R-2 | **Acoplar CRM y motor** | 0 imports, 0 privilegios cruzados | no integrar | evitado |
| R-3 | **Deshacer B-7** | `crm_user` sin USAGE en `asistente` | no conceder | evitado |
| R-4 | **La señal 3 del analista devuelve 0 siempre** | 63 usos, `conversation_id` NULL en los 63 | corregir un renglón en `motor.py:887` | **no** (es del motor) |
| R-5 | `version` del motor declarada y sin usar | el SQL no la consulta | no replicar el patrón en M09 | no |
| R-6 | `conocimiento_version` vacío | 52 propuestas | M09-K punto 3 | no |
| R-7 | 4 de 5 habilidades del motor con 0 usos | medido | revisión de catálogo, fuera de alcance | no |
| R-8 | `motor_user` con `BYPASSRLS` | B-7 | B-7 | para autonomía |
| R-9 | Que M09-K documente y el código cambie sin actualizar la ficha | — | versión en la misma constante que el detector | no |

---

## 17. Dependencias

| Dependencia | ¿Bloquea D-1? | ¿Bloquea M09-K? |
|---|:--:|:--:|
| **B-7** | **no** — la decisión D lo respeta | **no** |
| **M10** (RLS `campo_*`) | no | no |
| D-2 · quién aprueba | no | no |
| D-3 · documentos de conocimiento | no | **parcialmente** |
| D-4 · capacidad operativa | no | **solo H-05** |
| Corrección de `conversation_id` | no | no |

---

## 18. Siguiente paso

**[DISEÑO]** **M09-K — Formalización de las habilidades operativas.** Alcance
exacto, ya desbloqueado:

1. Ficha de 14 habilidades (10 de dominio + 4 transversales): `codigo`, `nombre`,
   `cuando_usarla`, `procedimiento`, `evidencia obligatoria`, `escalamiento`,
   `nivel` (0/1), `metrica`, `version`.
2. Registro literal congelado en `operaciones/`, al estilo de
   `nucleo/programador/registro.py`: sin `importlib`, sin registro dinámico.
3. Poblar `conocimiento_version` con `"<ID>@<version>"`.

**Sin tablas nuevas. Sin tocar `asistente.habilidades`. Sin asistentes. Sin
cambiar el comportamiento de ningún detector.**

**H-05 queda fuera** hasta D-4.

**No lo ejecuto. Espero autorización.**

---

### Anexo — qué se midió en este paso

| Medición | Herramienta | Resultado |
|---|---|---|
| ¿La habilidad ejecuta algo? | lectura de `motor.py:865-895` y `2670-2700` | **NO**: índice como `system`, cuerpo como dict de texto |
| API del módulo | `grep "^def"` | 4 funciones, ninguna ejecutable |
| Filtro de `indice_de` / `cargar` | SQL literal | `organization_id` + `estado='vigente'` + `roles_permitidos`, **doble capa** |
| Uso de `version` en el SQL | lectura | **ninguno** |
| Habilidades / vigentes / usos | SQL | **5 / 1 / 63** |
| Distribución de los 63 usos | SQL | 1 habilidad, 1 rol, 2026-09-06→12 |
| `conversation_id` en usos | SQL | **0 de 63** |
| `analista.py` señal 3 | lectura | `INNER JOIN` sobre esa columna → **cero siempre** |
| M09 → habilidades | `grep` en `operaciones/` | **0 referencias** |
| CRM → `nucleo/` | `grep` en `django-crm/backend/` | **0 imports** |
| `crm_user` → `asistente` | `has_schema_privilege` | **False** |
| `app_backend`/`motor_user` → habilidades | `has_table_privilege` | **True** |
| RLS de `habilidades` | `pg_class` / `pg_policies` | habilitada ✔ forzada ✔ 1 política |
| Habilidades por asistente | cruce config × tabla | **1 de 8 roles** tiene alguna vigente |

Producción al cerrar el paso, sin cambios:

```
habilidades 5 · usos 63 · roles de IA 8 · tenant_config v146
ledger 50 · kill switch DETENIDO · 0 PropuestaSupervisor · 192 django_migrations
```
