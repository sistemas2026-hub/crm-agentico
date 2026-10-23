# Gate G6 — el DDL de mensajes sobre una tabla poblada

```
BASE       fa9a0cd
VEREDICTO  G6 VERDE en lo medible sin producción. Falta el preflight del día.
FECHA      20/09/2026
ALCANCE    medición sobre base de prueba. Producción no se tocó ni se consultó.
```

## Qué pide G6

> Volumen medido; sesiones `idle in transaction` = 0 y locks problemáticos = 0
> sobre `conversations`, `messages` y `acciones_propuestas` **inmediatamente
> antes de aplicar**; estrategia de backfill aprobada por el área de
> producción. Con sesiones retenidas **no se aplica**, y subir `lock_timeout`
> no es la primera respuesta.

Dos cosas distintas: una se puede medir hoy (cuánto cuesta el DDL), la otra
sólo el día del despliegue (cómo está la base en ese momento).

## Qué es «la migración de mensajes»

`supabase/202609161600_origen_de_mensajes.sql`, el paso 1 de §11.5:

```sql
alter table asistente.messages
  add column origen text (+ check), autor_usuario_id uuid,
             autor_nombre text, clave_idempotencia text;

create unique index messages_clave_idempotencia_uq
  on messages (organization_id, conversation_id, clave_idempotencia)
  where clave_idempotencia is not null;
```

Cuatro columnas **nullable y sin default**, y un índice único **parcial**.

## Volumen

```
producción (A8, medido antes)   2 584 mensajes · 298 conversaciones · 1,3 MB
escenario real                  2 584 mensajes                        1,1 MB
escenario de estrés             499 995 mensajes                      192 MB
```

El de estrés es **193 veces** el volumen real. No es un pronóstico: es para
saber a qué distancia está el punto en que esto dejaría de ser trivial.

La distribución imita la medida: ~9 mensajes por conversación. Un reparto plano
daría un índice de otra forma.

## Tiempos

| | `ADD COLUMN` ×4 | `CREATE INDEX` | total |
|---|---|---|---|
| 2 584 filas, corrida 1 | 3,2 ms | 7,1 ms | **10,3 ms** |
| 2 584 filas, corrida 2 | 2,5 ms | 5,9 ms | **8,4 ms** |
| 499 995 filas, corrida 1 | 72,1 ms | 51,4 ms | **123,6 ms** |
| 499 995 filas, corrida 2 | 65,2 ms | 48,9 ms | **114,1 ms** |

Reproducible: dos corridas por escenario, cada una desde el estado sin migrar.

**La tabla no se reescribe**: 192 MB antes y 192 MB después. Es lo esperado —
`ADD COLUMN` nullable sin default es un cambio de catálogo desde PostgreSQL 11,
no una reescritura— pero medido, no supuesto.

**El índice nace vacío**: 8 192 bytes, el mínimo. `clave_idempotencia` es NULL
en todo el legado y el índice es parcial, así que no indexa nada.

## Locks

`ADD COLUMN` pide **ACCESS EXCLUSIVE**; `CREATE INDEX` sin CONCURRENTLY toma
**SHARE**: no bloquea lecturas, sí escrituras mientras construye.

Con el volumen real esa ventana son **7 ms**. Con 500 000 filas, **51 ms**. Una
escritura lanzada justo después del índice entró en 4,8 ms y 5,6 ms
respectivamente — sin espera apreciable.

**El riesgo real no es el tiempo del DDL. Es esperar el lock.** Si hay una
transacción abierta sobre `messages`, el ALTER se queda detrás de ella, y todo
lo demás se queda detrás del ALTER. Un cambio de milisegundos se convierte en
una caída, y ya se midió en este despliegue (sesiones `idle in transaction`
detrás del pooler).

Por eso el preflight se ejecuta con `lock_timeout` puesto: si no consigue el
lock en 3 s, falla en vez de bloquear a la fila de espera. **Subir
`lock_timeout` haría que el ALTER espere más, no menos.**

## ¿Hace falta `CONCURRENTLY`?

**No.** Con 51 ms de construcción sobre 193× el volumen real, `CONCURRENTLY`
sólo agregaría complicación: no se puede usar dentro de una transacción, deja
índices `INVALID` si falla, y necesita una pasada más. La migración se aplica
tal como está.

Esto vale **mientras el índice nazca vacío**, que es lo que pasa si se respeta
el orden de §11.5: DDL primero, escritura en paralelo después, backfill al
final. Invertirlo —poblar `clave_idempotencia` antes de crear el índice— cambia
el cálculo.

## El orden del despliegue no es una formalidad

Lo anterior vale **porque el índice nace vacío**. Se midió también el escenario
que ocurriría si alguien invirtiera el orden —poblar `clave_idempotencia`
antes de crear el índice— sobre 300 000 filas:

```
backfill de clave_idempotencia      5 490,1 ms    reescribe las 300k filas
create unique index (POBLADO)         345,2 ms    frente a 51 ms vacío
tamaño del índice                        27 MB    frente a 8 KB vacío
```

El índice pasa de **8 KB a 27 MB** y de 51 ms a 345 ms; el backfill en una sola
sentencia cuesta 5,5 s y reescribe todas las filas. Sigue sin ser catastrófico a
este volumen, pero es **otra escala**, y es exactamente por lo que §11.5 pide el
backfill en lotes cortos y **fuera** de la migración.

En el plan real esto no pasa: `clave_idempotencia` no se backfillea —es para
filas nuevas— así que el índice nace y se queda vacío sobre el legado. El dato
está acá para que, si alguien propone reordenar los pasos, el costo esté medido
y no haya que discutirlo de memoria.

## La herramienta

`cli/preflight_g6.py`. Dos modos, y la diferencia importa:

```
sin --medir   SOLO LECTURA. Volumen, sesiones con transacción abierta, locks
              sobre las tres tablas. Sale con código 1 si NO se puede aplicar.
              Es lo que G6 exige correr inmediatamente antes, también en
              producción.

con --medir   ESCRIBE. Se niega si el nombre de la base contiene 'prod',
              'produccion', 'postgres' o 'supabase'.
```

**Probado que muerde**: con una transacción retenida abierta a propósito, el
preflight la detecta y responde `NO SE APLICA TODAVIA`. Sin ella, código 0.

## G6: VERDE en lo medible — falta el preflight del día

```
medido          el DDL cuesta 10 ms al volumen real y 124 ms a 193 veces ese
                volumen; no reescribe la tabla; el índice nace vacío; no hace
                falta CONCURRENTLY
falta           correr cli/preflight_g6.py contra producción inmediatamente
                antes de aplicar, y que el área apruebe la estrategia
```

## Riesgos

1. **La versión no es la misma.** La medición corrió en PostgreSQL 16.14
   (contenedor de pruebas). Producción corre otra versión, que no se consultó.
   El comportamiento de `ADD COLUMN` nullable y de `CREATE INDEX` es el mismo
   desde PG 11, así que los números deberían sostenerse — pero es una
   inferencia, no una medición.
2. **El hardware no es el mismo.** Un contenedor local no predice el VPS. Lo que
   sí se sostiene es el orden de magnitud y, sobre todo, que la tabla no se
   reescribe: eso no depende del disco.
3. **El preflight del día no se puede adelantar.** Que hoy no haya sesiones
   retenidas no dice nada de cómo estará producción en ese momento. Es
   justamente por eso que el contrato lo pide «inmediatamente antes».
4. **Sólo se midió la migración de mensajes.** Las otras tres de §11.5
   (conversaciones + `relevo_eventos`, `sincronizaciones_externas`, acciones)
   no se midieron acá. Las tres crean tablas nuevas o agregan columnas
   nullable, así que el análisis es el mismo, pero no está medido.
