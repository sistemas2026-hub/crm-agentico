# M03-F-B — Cuadrillas ad-hoc por OT · implementación y cierre

**Fecha:** 2026-09-18
**Veredicto:** **M03-F-B = CERRADO / GO**

---

## 1. Estado final

```
Pruebas propias F-B ......  38 passed / 0 failed / 0 skipped
Regresion completa .......  4328 passed / 1 failed / 16 skipped
  el unico fallo ......... CATEGORIA C (entorno), probado: pasa bajo su
                           propia configuracion declarada
Migraciones ..............  0        makemigrations --check: "No changes detected"
Modelos modificados ......  0
Efectos externos .........  0        (espia probado que dispara primero)
Produccion ...............  SIN CAMBIOS -- 16 claves, DIFERENCIAS: NINGUNA
Commit ...................  no
```

---

## 2. Archivos modificados

| Archivo | Cambio | Migración |
|---|---|:--:|
| `campo/services/despacho.py` | +4 operaciones, 2 excepciones, helpers; **lock añadido a `asignar()`** | no |
| `campo/serializers.py` | `rol` → `ChoiceField` (F-4); `AsignacionSerializer`; 4 serializers de entrada; `cuadrilla` en el detalle; **corrección UUID** | no |
| `campo/despacho_views.py` | 4 vistas nuevas + mapeo de errores común | no |
| `campo/urls.py` | 4 rutas | no |

**Creado:** `campo/tests/test_m03fb_cuadrilla.py` (992 líneas, 38 pruebas).

```
887 inserciones · 13 supresiones · 4 archivos de codigo · 1 de pruebas
campo/models.py NO se toco (sus cambios son del cierre de catalogo del 15/09)
```

**No se tocó:** M09 · `revisar_coherencia` · M03-E · M03-D · `AsignacionTrabajo`
(modelo) · `campo/permissions.py` · `operaciones/*`.

---

## 3. Funcionalidades implementadas

| Operación | Ruta | Estado |
|---|---|---|
| Asignar primera persona | `POST .../asignar/` | **existente**, ahora con lock y catálogo cerrado |
| Agregar integrante | `POST .../cuadrilla/agregar/` | **nueva** |
| Cambiar principal | `POST .../cuadrilla/principal/` | **nueva** |
| Retirar auxiliar | `POST .../cuadrilla/retirar/` | **nueva** |
| Retirar principal + sucesor | `POST .../cuadrilla/retirar/` (con `nuevo_principal_id`) | **nueva** |
| Desasignar | `POST .../cuadrilla/desasignar/` | **nueva** |
| Consultar composición | `GET .../trabajos/<id>/` → clave `cuadrilla` | **nueva** |

**Sin entidad `Cuadrilla`.** La composición es
`orden.asignaciones`, agrupada por `orden_id` — F-1 intacto.

### Cumplimiento del contrato

| | Regla | Cómo se cumple | Prueba |
|---|---|---|:--:|
| **F-1** | Ad-hoc por OT | `orden_id` agrupa; 0 modelos nuevos | 1, 4, 5 |
| **F-2** | 0 / 1 / 2+ válidos; primera asignación principal | `asignar()` fija `es_principal=True`; `agregar_integrante` exige ≥1 previo, así que **no hay camino a una individual sin principal** | 1, 3, 17 |
| **F-3** | `es_principal` es la verdad; `rol` descriptivo | **ninguna operación toca `rol` para ascender a nadie**; `cambiar_principal` deja los roles intactos | 7 |
| **F-4** | Solo `ROLES_CUADRILLA` | `ChoiceField` en las 2 puertas que aceptan `rol` | 14, 15 |
| **F-5** | Retiro del principal con sucesor en el mismo acto | Una transacción; `RequiereSucesor` (409) si falta | 9, 10, 20 |

---

## 4. Corrección UUID preexistente

**Defecto encontrado, confirmado preexistente y corregido.**

Cualquier `POST /api/campo/trabajos/<id>/asignar/` con cabecera
`Idempotency-Key` fallaba con:

```
TypeError: Object of type UUID is not JSON serializable
```

**Causa:** el cuerpo de la respuesta se guarda tal cual en
`MutacionIdempotente`, y `get_tecnico_principal` devolvía `{"id": <UUID>}`.

**Confirmado preexistente** antes de tocar nada: se probó el endpoint viejo,
sin código de F-B de por medio, y reventó igual. No se veía porque **ninguna
prueba enviaba esa cabecera a ese endpoint**.

**Corrección:** `str(tec.id)` en `get_tecnico_principal` (2 apariciones, lista
y detalle). **Sobre HTTP no cambia un byte** — el renderer de DRF ya lo
serializaba a texto; lo que cambia es que el cuerpo pasa a ser almacenable.
Sin esto, la idempotencia de F-B era inalcanzable.

---

## 5. Pruebas F-B

```
38 passed / 0 failed / 0 skipped
```

Las 30 exigidas más 8 de contrato (orden terminada, foto vieja, doble alta,
otra empresa, no-op de principal, retiro del último, `revision`, desasignar
como no-atajo).

**Dos obligatorias, ambas en verde:**

- **§19 atomicidad** — excepción forzada **después** de mover las dos
  asignaciones y **antes** del commit; estado leído con **conexión
  independiente del ORM**.
- **§20 falla silenciosa** — el estado que F-A.3 midió como legal e invisible
  (*principal retirado + sucesor que se quedó de auxiliar*) no se alcanza por
  ningún camino.

---

## 6. Regresión completa

```
4328 passed · 1 failed · 16 skipped        (18m 16s)
```

### El único fallo — categoría C (entorno), probado

`invoices/tests/test_portal_rls.py::test_resolution_reads_estimate_that_empty_context_hides`

**No es F-B**: el archivo no menciona `campo` ni una vez, y F-B solo modificó
`campo/*`. Su propio docstring declara la condición que necesita:

> *"These run only under a non-superuser Postgres role (`RLS_ENFORCE=1
> --ds=crm.test_settings_postgres`), because the whole point is the behaviour
> that a superuser dev DB hides"*

**Probado, no declarado:** se creó un rol `rlsuser` (`NOSUPERUSER`,
`NOBYPASSRLS`) y se ejecutó bajo `crm.test_settings_postgres` →
**2 passed**. Está además marcado `postgres_only`, que es lo que CI deselecciona.

### Cómo se llegó a 1 fallo — todo fue el entorno, ningún cambio de código

| Corrida | passed | failed | skipped | Qué cambió |
|---|---:|---:|---:|---|
| 1ª | 4322 | 2 | 21 | montaje incompleto |
| 2ª | 4324 | 2 | 19 | `+ /docs` montado |
| 3ª | **4328** | **1** | **16** | `+ .env.docker` y `+ docker-compose.yml` montados |

Los dos fallos que desaparecieron eran artefactos del contenedor:
`DOCS_API_DIR` y `REPO_ROOT` se calculan como `BASE_DIR.parent`, que dentro
del contenedor resolvía a `/` porque solo estaba montado `backend`. **Se
arreglaron montando las rutas, no relajando los tests** — mismo criterio que
en A-3.4.

**Clasificación: A (F-B) = 0 · B (preexistente) = 0 · C (entorno) = 1 · D
(test incorrecto) = 0.**

---

## 7. Concurrencia

Las cuatro operaciones bloquean **la OT y solo la OT**
(`transaction.atomic()` + `select_for_update()`), el mismo objeto que bloquea
`programar_orden`: **no se introduce un orden de locks nuevo**, y como ninguna
toca el plan, nunca se toma un segundo lock.

**`asignar()` no tomaba ningún lock** (lo que parecía uno en `despacho.py:46`
era un comentario). Se le añadió.

**`test_19` demuestra que el lock es necesario, desarmándolo.** Escenario: OT
con A principal, B y C auxiliares; una operación retira A nombrando sucesor a
B mientras otra retira B.

```
CON lock ..... invariante intacto
SIN lock ..... 1 integrante y 0 principales  <- el estado prohibido
```

**El entrelazado es determinista, no probabilístico**: se inyecta en el punto
exacto del hueco (entre validar al sucesor y escribir). La primera versión
dependía del planificador; una prueba de concurrencia que gana o pierde por
timing no demuestra nada, y se rehízo.

`test_18` (dos cambios de principal simultáneos) queda en verde, y **su
docstring dice que también quedaría coherente sin el lock** — los UPDATE de
fila ya serializan ese caso. Se deja dicho para que nadie lo tome como prueba
de que el lock sirve.

---

## 8. Atomicidad

`test_20_CRITICA_atomicidad_del_retiro_del_principal` — obligatoria, en verde:

```
A principal, B auxiliar
-> retirar A + nombrar B, con excepcion forzada antes del commit
-> leido con CONEXION INDEPENDIENTE del ORM:
     2 filas · A sigue principal · B sigue auxiliar · 0 eventos nuevos
```

Ningún estado parcial. La verificación no usa el cursor que ejecutó la
transacción, que podría estar viendo lo suyo.

---

## 9. Idempotencia

Mecanismo existente (`manejar_idempotencia`), **sin sistema nuevo**. Las cuatro
vistas lo llevan.

| Caso | Resultado |
|---|---|
| Replay exacto | **200**, 1 sola fila, **1 solo evento** |
| Misma clave, cuerpo distinto | **409** `IDEMPOTENCY_KEY_REUSED`, no se ejecuta |
| Concurrencia | `select_for_update` sobre `MutacionIdempotente` (ya existente) |

La corrección UUID **permanece** y es lo que hace esto posible.

**Limitación documentada, no rediseñada:** `manejar_idempotencia` trabaja en
**tres transacciones** (crear PROCESANDO / ejecutar / marcar COMPLETADA); un
fallo en la tercera deja el dato escrito y la mutación en PROCESANDO.
Preexistente, fuera del alcance de F-B.

---

## 10. Auditoría

`EventoTrabajo`, **sin tabla nueva**. Seis tipos, uno por operación:

```
asignacion / reasignacion  ·  integrante_agregado  ·  cambio_principal
integrante_retirado  ·  principal_retirado  ·  cuadrilla_desasignada
```

Cada evento lleva **`antes` y `despues`**: la composición completa
(`profile`, `rol`, `es_principal`), más actor, timestamp y motivo. La
transición se **reconstruye**, no solo se constata.

`cambio_principal` y `principal_retirado` usan **las mismas claves**
(`principal_anterior` / `principal_nuevo`), para que una sola consulta cubra
los dos tipos.

---

## 11. Seguridad

| Verificación | Resultado |
|---|---|
| Tenant A sobre OT de tenant B | **404** en las 4 rutas, nunca 403 |
| Usuario sin permiso (técnico) | **403** en las 4 rutas |
| Usuario autorizado | opera con normalidad |
| Persona de otra empresa como integrante | rechazada |

Se reutiliza `_exigir_gestion` y el 404 estricto del módulo.
`campo/permissions.py` **no se tocó**: ya concedía por pertenencia, que es lo
que una cuadrilla necesita.

**Dicho sin matices:** reutilizar `AsignacionTrabajo` **no** resuelve el
aislamiento en base de datos. Sigue sin RLS y sin `org_id` propio; toda la
separación vive en la capa de aplicación. Es deuda (§16), no se tocó aquí.

---

## 12. Programación intacta

Sobre una OT **ya programada** (plan, secuencia 5, zona sur, prioridad 2), tras
agregar 2 integrantes, cambiar principal, retirar auxiliar y retirar principal
con sucesor:

```
programada_para · estado · secuencia · dia · zona · prioridad · estado_linea
· updated_at de la linea · numero de lineas del plan
                         -> TODOS IDENTICOS
```

Se compara también `updated_at`: los valores podrían coincidir y aun así
haberse reescrito.

**Única escritura sobre la OT: `revision += 1`**, deliberada — es el contador
que sincroniza la app del técnico.

---

## 13. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

Instrumentado en `socket.socket.connect` alrededor de **las siete
operaciones**. El cero se leyó **después** de probar que el espía dispara:
una sonda deliberada a `example.invalid` fue capturada.

---

## 14. Producción

# SIN CAMBIOS

Solo `SELECT`, `read_only = True`. **16 claves → DIFERENCIAS: NINGUNA.**

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · teams 0 · Disponibilidad 0 · operaciones_externas 0
MutacionIdempotente 14   (la mas reciente: 2026-09-09, nueve dias atras)
kill switch detenido · tenant_config rapilink v146
```

Ni `migrate`, ni `seed`, ni `INSERT`/`UPDATE`/`DELETE`/`ALTER`.

**Nota de honestidad:** en la primera comprobación di `MutacionIdempotente`
como esperado 0 sin haberlo medido nunca antes. El valor real es 14, y sus
filas son del 8–9 de septiembre. El error fue mío al inventar la referencia,
no un cambio en producción.

---

## 15. Migraciones

```
makemigrations --check  ->  "No changes detected"

0 migraciones · 0 modelos · 0 constraints · 0 indices
```

F-B cumple el contrato entero **sin tocar el esquema**. `retirado_en` no se
creó: el retiro borra la fila y la historia vive en `EventoTrabajo`, que es
donde §12 la pedía.

---

## 16. Deudas NO bloqueantes

Solo documentadas. **Ninguna se resolvió en F-B**, por instrucción expresa.

| # | Deuda | Dónde se midió |
|:--:|---|---|
| 1 | **RLS de `campo_*`**: 7 tablas sin RLS, `campo_asignacion_trabajo` sin `org_id` propio | F-A.2 §M |
| 2 | **Bypass del admin**: el inline deja `es_principal`/`rol` editables y no escribe evento | F-A.1 M6 · F-A.3 §F.4 |
| 3 | **Punto ciego de H-05**: mira solo al principal; **crece con la adopción de cuadrillas** | F-A.2 §J |
| 4 | **`es_principal` default `False`** en el modelo, contradiciendo toda vía de escritura | F-A.2 §B.3 |
| 5 | **`EventoTrabajo.tipo` sin catálogo cerrado** — se le añadieron 4 tipos | F-A.3 §F.4 |
| 6 | **`CHECK` de catálogo en base** (endurecimiento más allá de F-4) | F-A.2 §D |
| 7 | **Trigger `DEFERRABLE`** para "exactamente un principal" en base | F-A.2 §D.2 |
| 8 | **Sin control de solape horario** de una persona entre OTs | F-A.2 §A.4 |
| 9 | **Idempotencia en tres transacciones** | §9 |
| 10 | **Zona y vehículo** | F-A.2 §K, §L |

---

## 17. GO / NO-GO

| # | Criterio | |
|:--:|---|:--:|
| 1 | Pruebas F-B verdes | **SÍ** — 38/38 |
| 2 | Regresión sin fallos atribuibles a F-B | **SÍ** — el único fallo es categoría C, probado |
| 3 | Atomicidad demostrada | **SÍ** — conexión independiente |
| 4 | Concurrencia demostrada | **SÍ** — determinista, con el lock desarmado |
| 5 | Idempotencia demostrada | **SÍ** — replay, clave reusada, concurrencia |
| 6 | Auditoría demostrada | **SÍ** — 6 tipos con antes/después |
| 7 | Composición visible | **SÍ** — clave `cuadrilla` en el detalle |
| 8 | Programación intacta | **SÍ** — 9 campos idénticos, `updated_at` incluido |
| 9 | Tenant isolation | **SÍ** — 404 en las 4 rutas |
| 10 | 0 efectos externos | **SÍ** — espía probado |
| 11 | 0 migraciones | **SÍ** |
| 12 | Producción intacta | **SÍ** — 16 claves |
| 13 | F-1 · F-2 · F-3 · F-4 · F-5 se mantienen | **SÍ** |
| 14 | Sin entidad `Cuadrilla` innecesaria | **SÍ** |
| 15 | M09 y `revisar_coherencia` sin tocar | **SÍ** |

# M03-F-B = CERRADO / GO

---

```
codigo ......... 4 archivos modificados     pruebas ... 1 archivo creado (38)
migraciones .... 0    modelos .... 0    constraints .... 0    entidades .... 0
M09 ............ sin tocar    revisar_coherencia ... sin tocar    M03-E ... sin tocar
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no
```
