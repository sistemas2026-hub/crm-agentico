# M09-K — Informe de implementación

**Fecha:** 2026-09-17

---

## Archivos creados

| Archivo | Qué es | Líneas |
|---|---|---:|
| `django-crm/backend/operaciones/habilidades.py` | El registro literal congelado con las 14 fichas | ~700 |
| `django-crm/backend/operaciones/tests/test_m09k_habilidades.py` | 144 pruebas de consistencia | ~330 |
| `M09-K_HABILIDADES_OPERATIVAS.md` | Documentación (secciones 1–18) | — |
| `M09-K_IMPLEMENTACION.md` | Este informe | — |

## Archivos modificados

| Archivo | Cambio | Alcance |
|---|---|---|
| `django-crm/backend/operaciones/supervisor.py` | **una línea funcional** + su comentario, y un import | poblar `conocimiento_version` |

El cambio funcional, íntegro:

```python
from operaciones import auditoria, habilidades        # antes: solo auditoria

# dentro de registrar_propuesta(), al construir PropuestaSupervisor:
conocimiento_version=habilidades.referencia_de(senal.tipo),
```

**Ningún detector fue modificado.** Ninguna condición, ningún umbral, ninguna
consulta, ninguna huella.

## Archivos NO modificados — verificado

| Archivo / área | Estado |
|---|---|
| `nucleo/` **completo** | **sin cambios** — `find nucleo/ -newermt "-40 minutes"` → vacío |
| `nucleo/modelo/motor.py` | sin cambios |
| `nucleo/habilidades/catalogo.py` | sin cambios |
| `nucleo/habilidades/analista.py` | sin cambios |
| `registrar_uso()` | sin cambios |
| `asistente.habilidades` (tabla) | **sin tocar**: 5 filas, intactas |
| `asistente.habilidad_usos` | **sin tocar**: 63 filas, intactas |
| `operaciones/models.py` | sin cambios — **ningún campo nuevo** |
| `operaciones/views.py`, `urls.py`, `serializers.py`, `permissions.py` | sin cambios |
| Los 10 detectores de `supervisor.py` | sin cambios |
| `tenants/`, `supabase/`, `docker-compose*` | sin cambios |

## Pruebas ejecutadas

| Momento | Suite | Resultado |
|---|---|---|
| **Antes de tocar nada** | `operaciones/tests/` | **180 passed** |
| Nuevas, aisladas | `test_m09k_habilidades.py` | **144 passed** |
| **Después** | `operaciones/tests/` | **324 passed** |

```
324 = 180 (base) + 144 (nuevas)
regresiones: 0
```

Entorno: contenedor PostgreSQL 16 aislado (`pg-m09k`, puerto 15499), eliminado al
cerrar. **Nunca contra producción.**

### Un fallo durante el desarrollo, y cómo se resolvió

`test_ninguna_ficha_afirma_un_conocimiento_que_no_existe` falló en la primera
corrida: comparaba la cita con una lista de cadenas exactas, y la ficha H-08 dice
`'NovedadOperativa.TIPOS (catálogo cerrado de causas)'`.

Se corrigió **la prueba**, no la ficha, y se la hizo más fuerte: ahora resuelve
la cita **contra el modelo real** (`getattr(NovedadOperativa, "TIPOS")`) en vez
de contra una lista de cadenas — una lista envejecería en silencio el día que el
atributo se renombre, que es justo lo que hay que cazar.

## Datos modificados

**Ninguno.** No se escribió ninguna fila en ninguna base. Las propuestas de la
réplica de M09-E conservan su `conocimiento_version` vacío: **no se hizo
backfill** y producción tiene **0 propuestas**.

## Migraciones ejecutadas

**Ninguna. Ninguna creada.** `find ... -path "*migrations*" -newermt "-40 min"` → vacío.

`conocimiento_version` ya existía como `CharField(128)` desde M09-D: se pobló un
campo, no se agregó uno.

## Producción tocada

# NO — Producción no modificada

```
ledger                : 50            (sin cambios)
kill switch           : detenido      (sin cambios)
filas ACTIVO          : 0
PropuestaSupervisor   : 0
acciones_propuestas   : 40
operaciones_externas  : 0
django_migrations     : 192           (sin cambios)
tenant_config         : v146          (sin cambios)
asistente.habilidades : 5             (intactas)
asistente.habilidad_usos : 63         (intactos)
```

Las únicas operaciones contra producción en todo el paso fueron **lecturas**
(`read_only=True`) para verificar ese estado.

## Efectos externos

# 0

No se llamó a WispHub, SmartOLT, WhatsApp ni al CRM externo. Ninguna de las 14
habilidades declara herramienta de escritura — verificado por prueba sobre las 14.

## Autonomía modificada

# NO

- El kill switch no se tocó: sigue **DETENIDO**.
- La frontera de efectos externos no se tocó.
- Ninguna ficha declara nivel > 1.
- Las 4 transversales son nivel 0.
- `ejecutar_propuesta` sigue levantando.

---

## Criterio de éxito (§23)

| | Criterio | |
|:--:|---|:--:|
| ☑ | Las 14 habilidades están formalizadas | 14/14 |
| ☑ | No se creó un segundo catálogo de habilidades | registro en código |
| ☑ | `asistente.habilidades` no fue modificado | 5 filas intactas |
| ☑ | No se crearon asistentes | 0 |
| ☑ | No se modificó la lógica de los detectores | 0 cambios |
| ☑ | No se modificó autonomía | kill switch DETENIDO |
| ☑ | No se agregaron herramientas de escritura | 0, verificado en las 14 |
| ☑ | Existe versionamiento | `<ID>@<entero>`, las 14 en v1 |
| ☑ | Existe registro literal congelado | `MappingProxyType` + `frozen=True` + sha256 |
| ☑ | Existe trazabilidad | `conocimiento_version` poblado |
| ☑ | `conocimiento_version` solo con información respaldada | prefijo `habilidad:`; `""` si no hay ficha |
| ☑ | Existe definición de incertidumbre | las 14 |
| ☑ | H-05 permanece bloqueada | `estado=bloqueada`, 2 pruebas |
| ☑ | El defecto `conversation_id` del Motor queda fuera y documentado | §18 P-4 |
| ☑ | Las pruebas pasan | 324 passed |
| ☑ | Producción no fue modificada | verificado |
| ☑ | No hubo efectos externos | 0 |

**17 de 17.**

---

## Regla contra sobreimplementación (§24)

No hizo falta detenerse: **ninguna parte del alcance exigió** una tabla nueva,
una migración, integración Motor ↔ CRM, tocar `asistente.habilidades`, cambiar
PostgreSQL, permisos, autonomía, herramientas ni detectores.

Lo que **sí** se decidió no hacer, y queda documentado:

| Tentación | Por qué no |
|---|---|
| Hacer backfill de `conocimiento_version` en propuestas existentes | modificaría datos; producción tiene 0 propuestas y la réplica no es autoridad |
| Corregir el `conversation_id` del Motor | fuera de alcance por instrucción explícita — **P-4** |
| Refactorizar `supervisor.py` para que los detectores "lean" su ficha | invertiría D-1: el código es la fuente, no la ficha |
| Escribir los documentos de conocimiento | es **D-3** |
| Desbloquear H-05 inventando una definición de capacidad | es **D-4** |

---

## Control de cambios (§22)

```
archivos tocados por M09-K (find -newermt "-40 minutes"):
  django-crm/backend/operaciones/habilidades.py              [nuevo]
  django-crm/backend/operaciones/tests/test_m09k_habilidades.py  [nuevo]
  django-crm/backend/operaciones/supervisor.py               [1 línea + import]
  M09-K_HABILIDADES_OPERATIVAS.md                            [nuevo]
  M09-K_IMPLEMENTACION.md                                    [nuevo]

nucleo/         -> sin cambios
migraciones/    -> ninguna creada
```

`git diff --stat` muestra 31 archivos, **todos de pasos anteriores de esta
sesión**: `django-crm/backend/operaciones/` entero está sin versionar (`??`), por
eso los cambios de M09-K no aparecen ahí. Se verificó por marca de tiempo.

**No se hizo commit.** No estaba autorizado.
