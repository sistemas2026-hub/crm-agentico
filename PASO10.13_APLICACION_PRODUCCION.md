# Paso 10.13 — Aplicación en producción de las migraciones 3 y 4

**Fecha:** 17/09/2026
**Resultado: DETENIDO ANTES DE EJECUTAR**, por el punto 8 del propio encargo.
**Producción intacta**: ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`,
0 tablas de las migraciones 3 y 4, rol `autonomia_operador` inexistente.

> ## El punto 8 dice: «Si el mecanismo ejecuta otras migraciones por dependencia, detenerse y reportarlo **antes** de ejecutar.»
>
> No es una dependencia de SQL, pero es una consecuencia del mecanismo que
> cambia lo que queda posible después, y es irreversible:
>
> **Aplicar sólo las migraciones 3 y 4 deja las dos de reconciliación
> permanentemente inaplicables con `--aplicar`.** Medido en réplica, no deducido.

---

## A. Backup

Tomado **antes** de cualquier otra cosa, con el procedimiento B.6/B.7.

| | |
|---|---|
| Sello | **`20260917_141238`** |
| Ubicación | `C:\Users\Usuario\respaldo_p1013\` |
| Fecha/hora | 2026-09-17 14:12:38 – 14:13:38 |

| Artefacto | Tamaño | SHA-256 |
|---|---|---|
| `20260917_141238_datos.dump` | 8.900.683 B | `0ab7ebf513f74928ec3b7d89f17288cf4eca857a5f024d51…` |
| `20260917_141238_roles.sql` | 9.936 B | `94e9b39656e319d0b30236a24dd3e00d5151c1b3a65feebd…` |
| `20260917_141238_entorno.sql` | 4.525 B | `97d31850275ac70ff98b43ff877a7b0d84f6ff43ce1fb85e…` |

**Verificación — restaurado, no sólo generado:** réplica limpia,
`restaurar.sh` código **0**, **25 de 25** comprobaciones estructurales idénticas
a producción, y el scheduler funcional (`job_claim → job_finalize` =
`succeeded`), **0 fallas**.

**El respaldo se conserva** hasta cerrar la operación.

## B. Preflight — **0 en rojo**

| Comprobación | Valor | |
|---|---|---|
| `session_user` / `current_user` | `postgres` / `postgres` | ok |
| Servidor | PostgreSQL 17.6 | ok |
| Ledger: filas / md5 | 45 / `58ff01f2…` | ok |
| Bloqueos `ACCESS EXCLUSIVE` en `asistente` | 0 | ok |
| Bloqueos sobre `public.organization` | 0 | ok |
| Transacciones abiertas | 0 | ok |
| `job_catalogo` (scheduler sin trabajos) | 0 | ok |
| Tablas en `asistente` | 35 | ok |
| Funciones `job*` / md5 | 10 / `614d3a16…` | ok |
| `public`: tablas / dueño | 135 / `crm_owner` | ok |

**Lo que no debe existir todavía — confirmado ausente:**

| | |
|---|---|
| `asistente.interruptor_autonomia` | **0** |
| `asistente.operaciones_externas` | **0** |
| Rol `autonomia_operador` | **0** |
| Función `asistente.autonomia_detener` | **0** |

## C. Commit

```
HEAD  = 108935f8f8ee1b67eaa65ca84bf08d50a39ed5e0
        108935f  2026-09-15 11:20:57 -0500
        "El evaluador clasificaba cada turno y la clasificacion se tiraba si no escalaba"
rama  = fix/integracion-wisphub
```

## D. Migraciones — **ninguna aplicada**

Estado del CLI contra producción: **4 pendientes, 0 con checksum distinto.**

| Archivo | Checksum | Qué es |
|---|---|---|
| `202609151700_scheduler_persistente_reconciliado.sql` | `e7a70f0556d29022…` | reconciliación (paso 10.5), **sin aplicar** |
| `202609151705_scheduler_funciones_reconciliado.sql` | `ca0bf08137214414…` | reconciliación (paso 10.5), **sin aplicar** |
| `202609151710_interruptor_autonomia.sql` | `9c8df21b002826e1…` | **migración 3** — objeto de este paso |
| `202609151715_operaciones_externas.sql` | `9c2f242d9319664a…` | **migración 4** — objeto de este paso |

### El hallazgo que detuvo la ejecución

Reproducido sobre la réplica del respaldo de §A, con la selección validada en el
paso 10.8 (mover archivos fuera del nivel superior de `supabase/`):

```
a) con SOLO 3 y 4 en el directorio
     pendientes: 2
       202609151710_interruptor_autonomia.sql
       202609151715_operaciones_externas.sql

b) --aplicar
     [ok] 202609151710_interruptor_autonomia.sql  (16 ms)
     [ok] 202609151715_operaciones_externas.sql   (10 ms)
     2 aplicada(s).

c) se devuelven 1 y 2 y se pide aplicarlas
     [migrar] HAY MIGRACIONES PENDIENTES ANTERIORES A OTRAS YA ANOTADAS.
              No se aplica nada.
       202609151700_scheduler_persistente_reconciliado.sql
       202609151705_scheduler_funciones_reconciliado.sql
     ultima anotada: 202609151715_operaciones_externas.sql.
     Se resuelven con --adoptar, no con --aplicar.
```

**Por qué.** `mig.huecos()` declara hueco a toda migración pendiente cuyo nombre
ordene **antes** del máximo anotado en el ledger. Hoy el máximo es
`202609141300_scheduler_funciones.sql`, y las cuatro pendientes ordenan después.
Si se aplican 3 y 4, el máximo pasa a ser `202609151715…`, y entonces
`202609151700…` y `202609151705…` quedan por debajo — huecos.

**Y es irreversible**: el ledger es de solo agregar. Cerrar esas dos exigiría
entonces `--adoptar`, que hoy se niega porque el manifiesto es de PostgreSQL 16
y registra `pgcrypto` en el esquema `ext` (medido en el paso 10.4). Regenerarlo
es una tarea aparte.

## E-P. Ledger, objetos, roles, grants, RLS, semilla y pruebas

**No aplicable: nada se ejecutó.** El ledger está igual que al empezar —
45 filas, md5 `58ff01f220787396657af7832f6c48c8` — y no se creó ninguna tabla,
ningún rol, ninguna función, ninguna política ni ninguna fila semilla.

Lo que estas secciones dirían está medido y aprobado en los pasos previos, y se
reutilizará tal cual cuando se autorice la ejecución:

| Sección | Dónde está probado |
|---|---|
| F · Objetos creados | 10.9 y 10.10 — 2 tablas, 4 índices, 7 constraints, 2 políticas, RLS + FORCE |
| G · Roles | 10.11 — `autonomia_operador` `NOLOGIN`, sin `CREATE`, sin login |
| H · Grants | 10.11 §D — matriz completa, y 10.12 §SQL — las **dos** membresías del contexto administrativo |
| I · RLS | 10.11 — `tenant_aislado` + `tenant_aislado_operador`, aislamiento verificado también para el operador |
| J · Semilla | 10.10 — la migración siembra **`detenido`**; 10.11 caso 7 — tenant nuevo nace `detenido`, 0 filas `activo` |
| K · Pruebas negativas | 10.12 casos B, F, G, H, J — con `session_user` real |
| L · Pruebas positivas | 10.12 casos A, D, E, I — con el CLI real |
| M · Tenant isolation | 10.11 — escribir para otra organización dio `new row violates row-level security policy` |
| N · Scheduler | 10.2/10.3 y esta misma verificación de respaldo — `succeeded` |
| O · Restore | 10.12 §Restore — permisos y comportamiento idénticos |

## Q. Errores e incidentes

**Ninguno en producción**: no se ejecutó nada. Ninguna llamada a WispHub,
SmartOLT ni a ningún sistema externo.

Un incidente de método, en la réplica: la primera lectura del estado del
interruptor tras el restore del paso 10.12 usó
`pg_has_role(..., 'USAGE')` para medir la capacidad de `SET ROLE`, que es el
privilegio equivocado —`'SET'` es el correcto—. Corregido y documentado en el
informe 10.12; no afecta a este paso.

## R. Estado final

| | |
|---|---|
| Ledger | **45 filas**, md5 `58ff01f220787396657af7832f6c48c8` |
| Tablas en `asistente` | 35 |
| `interruptor_autonomia` / `operaciones_externas` | **no existen** |
| Rol `autonomia_operador` | **no existe** |
| `DBUSER` | sin cambios |
| Autonomía | **DETENIDA / NO OPERATIVA** — el código que la consulta no está desplegado y las tablas no existen |
| M02, M03, M09, WispHub, SmartOLT, scheduler, `WorkTypeVersion` | sin tocar |

## S. Rollback disponible

No hizo falta, y está listo:

- **Nivel 1** — fallo antes del COMMIT de un archivo: automático, esa migración
  se deshace entera y no queda anotada (medido en 10.7).
- **Nivel 2** — tras el COMMIT: `drop table asistente.interruptor_autonomia` /
  `operaciones_externas`; `drop role autonomia_operador`; `drop function
  asistente.autonomia_detener`. Sin dependientes; la única pérdida serían las
  filas semilla.
- **Nivel 3** — restauración completa desde el respaldo **`20260917_141238`**,
  verificado y conservado.

---

## Las tres salidas, para que la decisión sea suya

### Opción 1 · Aplicar las cuatro en una pasada

Es el comportamiento natural del CLI: `--aplicar` sin mover nada.

- **A favor:** no crea huecos; el ledger queda coherente (45 → 49); la
  reconciliación queda cerrada. Y está medido: el paso 10.6 demostró con
  *event triggers* que las dos de reconciliación **no crean, no duplican y no
  destruyen nada** — 0 `CREATE TABLE`, 0 `CREATE INDEX` sobre lo histórico, y el
  md5 de los 10 cuerpos de función sin moverse.
- **En contra:** este paso autoriza 3 y 4, no 1 y 2. Aplicar las cuatro excede
  lo pedido — **y por eso no lo hice.**
- **Bloqueos:** los de la reconciliación entran en `asistente.tenant_config(_historial)`
  ~60 ms (las lee el motor), además de los de 3 y 4 sobre `public.organization`.

### Opción 2 · Aplicar sólo 3 y 4

Lo que este paso pide al pie de la letra.

- **A favor:** alcance exacto.
- **En contra, medido:** las dos de reconciliación quedan **huecos permanentes**
  y sólo se podrían cerrar con `--adoptar`, que exige regenerar el manifiesto
  contra una referencia PostgreSQL 17 con `pgcrypto` en `extensions`.

### Opción 3 · Renombrar 1 y 2 para que ordenen después de 1715

Por ejemplo `202609151720…` y `202609151725…`.

- **A favor:** elimina el hueco y conserva el alcance de este paso.
- **En contra:** cambia sus checksums **otra vez** y deshace el criterio de
  nombres que fijó el paso 10.5, que se eligió justamente para conservar el
  orden relativo original.

**Recomendación técnica:** la opción 1. Es la única que no deja el ledger en un
estado que después haya que rescatar, y lo que añade sobre lo autorizado —las
dos de reconciliación— es precisamente lo que el paso 10.6 midió como
operación sin efecto físico. Pero amplía el alcance de este paso, así que no la
ejecuto sin que lo diga usted.

## Regla de cierre

**El paso no queda aprobado**: las migraciones 3 y 4 no se aplicaron. Todo lo
que sí se hizo —respaldo verificado, preflight en verde, identificación exacta
de los archivos y de los checksums— queda listo para ejecutar en el momento en
que se resuelva la decisión de alcance.

Producción intacta. Evidencia conservada. Ninguna corrección aplicada
directamente en producción.
