# DEXTER — BASELINES

Lo que da verde HOY, para distinguir una regresión de una deuda conocida.
Cada fila dice CUÁNDO se midió. Una baseline sin fecha no sirve.

Reportar resultados así, nunca pegando stdout completo:

```
comando · exit code · passed/failed/skipped · sólo el traceback de los fallos
```

---

## BACKEND — medido 19/09/2026 al cerrar la Fase 1, CONTRA POSTGRESQL REAL

Base: PostgreSQL 16.14, contenedor `pg-motor` :55435, base `t6_d3` construida
desde cero por el ledger. Ninguna parte quedó `[saltado]`.

```
DBHOST=localhost DBPORT=55435 DBNAME=t6_d3 DBUSER=motor DBPASSWORD=motor

test_t6_devolucion              OK   37 ok   (nuevo: 20 sin base + 17 con base)
test_entrega_registrada         OK   42 ok
test_chat_canal                 OK   47 ok
test_relevo_transiciones_base   OK  129 ok
test_relevo_efectos             OK   28 ok
test_relevo_esquema_base        OK   27 ok
test_pausa_escalada             OK   17 ok
test_registro_sin_pii           OK
test_nucleo_sin_tenants         OK
test_relevo_eventos_lectura     OK   23 ok   (1.6–1.8)
test_anti_rebote_persistente    OK
test_timeouts_modelo            OK   (19/09, sin base)
test_editor_config              OK   (19/09, sin base)
```

Reconstruir la base: `DBPASSWORD=motor py -3.13 cli/base_desde_cero.py --base <nombre>`

Las dos `[saltado]` sólo corren la parte estática. La parte real necesita base
construida por el ledger:

```
DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \
  DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_entrega_registrada.py
```

El fallo de `test_entrega_registrada:156` (3 consumidores esperados, 6 encontrados)
quedó **resuelto** en 1.4C.0-D2 separando ③a/③c, sin tocar el test.
Historia: `SPEC/auditorias/1.4C-D1c.md`.

## SINTAXIS E IMPORTS — 19/09/2026, tras 1.4C.0-D1b

```
parse    db.py · api.py · transiciones.py          OK
import   nucleo.persistencia.db                    OK
import   nucleo.relevo.transiciones                OK
import   nucleo.canales.api                        OK (avisa MOTOR_SERVICE_TOKEN
                                                   ausente: config local, no fallo)
```

## GUARDAS DEL REPO

```
py -3.13 tests/test_nucleo_sin_tenants.py     arquitectura núcleo/tenant
py -3.13 tests/test_editor_config.py          editor de agentes, sin base
py -3.13 tests/test_timeouts_modelo.py        ninguna llamada al modelo se cuelga
py -3.13 cli/evaluar.py rapilink --humo --base    8 casos críticos, ~3 min
py -3.13 cli/diferencias_config.py rapilink       repo vs desplegado
```
No re-ejecutadas en esta sesión.

## FRONTEND — medido 19/09/2026 al cerrar la Fase 1

```
cd django-crm/frontend

npx svelte-check     2 errores · 25 warnings · 0 errores en conversaciones/
npx vitest run       32 archivos: 17 failed / 15 passed
                     483 tests:   63 failed / 420 passed
```

Los 63 fallos y 17 archivos son **históricos**, preexistentes a la Fase 1 y
ajenos a `conversaciones/`. Se identifican por conteo estable: cualquier cambio
en ese número es una regresión hasta demostrar lo contrario.

Guardas de `conversaciones/`, 159/159:

```
ordenamiento (0B.0)     20
grabación (D29)         17
formato (1.3B)          17
devolución (1.4C)       13
cableado T6 (1.4C)      22
contexto (1.5–1.9)      47
red (1.8)               11
actividad (1.6)         12
D30, backend            18   se reporta aparte, no suma a vitest
```

### Warnings nominales conocidos en conversaciones/

```
.marca            +layout.svelte:353
.marca::before    +layout.svelte:362
.adjunto-otro     [id]/+page.svelte:1601     preexistente en d0d6be9
```

Un cuarto es regresión. El checkpoint anterior listaba sólo dos y decía «26» sin
fecha; la lista estaba incompleta y el número no se pudo reconciliar. Por eso
estas cifras llevan fecha.

### No medido

```
QA visual multi-viewport   NO EJECUTABLE con los medios disponibles
```

No es que falte hacerla: **falta una forma de hacerla**. El dev server levanta,
pero `hooks.server.js:373` redirige a `/login` antes de montar el layout, así que
ni siquiera se ve el estado de error dentro de `.mesa.bandeja` — la alternativa
que el checkpoint de 1.1 proponía. Entrar exige un JWT del backend de producción,
y una ruta de prueba con datos falsos está prohibida por contrato.

Lo que hay es auditoría estática de CSS, y encontró cosas reales (ver
`auditorias/1.9-CIERRE-VISUAL.md`). Ningún píxel de 1.4C a 1.9 se vio.

## DEUDAS CONOCIDAS — no son regresiones

```
.marca / .marca::before    warnings de CSS muerto, alcance de un solo archivo
test_rutas_sql             cuenta bases globales; falla si otra suite crea bases
                           en paralelo. Correrla sola hasta arreglarla.
pnpm check ciego a:        (a) CSS muerto en archivos con una clase interpolada
                           (b) constantes/imports JS huérfanos
                           (c) clases usadas sin regla (sólo avisa al revés)
vitest sin plugin Svelte   no compila .svelte; la lógica testeable se extrae a .js
```
