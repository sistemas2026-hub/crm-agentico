# DEXTER — BASELINES

Lo que da verde HOY, para distinguir una regresión de una deuda conocida.
Cada fila dice CUÁNDO se midió. Una baseline sin fecha no sirve.

Reportar resultados así, nunca pegando stdout completo:

```
comando · exit code · passed/failed/skipped · sólo el traceback de los fallos
```

---

## BACKEND — medido 19/09/2026 tras 1.4C-D3, CONTRA POSTGRESQL REAL

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

## FRONTEND — del checkpoint de Fase 1, NO re-medido

```
pnpm check    2 errores históricos · 25 warnings · 0 errores en conversaciones/
vitest        27 archivos: 17 failed / 10 passed
              378 tests:   63 failed / 315 passed
```

Verdes por gate, todos pasando en su última corrida:

```
guarda 0B.0 (ordenamiento)   20/20
D29 (grabación)              17/17
D30 (origen en el hilo)      18/18
formato (autorDe)            17/17
```

> Estas cifras vienen del checkpoint y **no fueron re-medidas** en la sesión del
> 19/09. Antes de usarlas como referencia de una regresión, volver a correrlas.

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
