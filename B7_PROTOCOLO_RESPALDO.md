# B.7 — Protocolo de respaldo y restauración

**Creado el 17/09/2026 (paso 10.3).** Hasta ahora B.7 no tenía documento: su
procedimiento vivía dentro de `B6_PLAN_CAMBIO_CONTROLADO.md` §B, que es lo que
lo dejó incompleto sin que se notara. Este archivo es la fuente de verdad del
respaldo; B.6 §B remite aquí.

> **Lo que costó escribir esto.** Entre B.7, el simulacro del paso 9 y el paso
> 10 se restauró el respaldo **cuatro veces** con `pg_restore` en 0, y las
> cuatro dejaron **un scheduler roto**. Nadie lo vio porque todas las
> verificaciones comprobaban que los objetos existieran. Ver `PASO10.2` y
> `PASO10.3`.

---

## 1. Qué esquemas se respaldan

`public`, `asistente` y `asistente_ledger`. Los tres, siempre.

`asistente_ledger` parece prescindible y no lo es: `asistente.migraciones_aplicadas`
tiene disparadores que llaman a `asistente_ledger.solo_agregar()`, y sin ese
esquema la restauración aborta.

**No se respalda la base completa.** Un volcado sin `--schema` lleva las 7
extensiones y los 12 esquemas, pero **no se restaura en un PostgreSQL normal**:
`ERROR: extension "pg_net" is not available`. `pg_net`, `supabase_vault` y
compañía son binarios de la plataforma.

## 2. Qué roles se respaldan

Todos, con `pg_dumpall --roles-only`: 25 `CREATE ROLE`, 43 `ALTER ROLE` y
**33 `GRANT` de membresía**.

De esos 25, nueve son del proyecto y el resto es plataforma de Supabase:

```
crm_user  crm_owner  crm_migrator  motor_user  app_backend
asistente_owner  job_executor  scheduler_coordinator  monitor_ro
```

> El archivo contiene los **hashes SCRAM de las contraseñas**. Se guarda con el
> mismo cuidado que una credencial.

En un destino que no sea Supabase, ~29 `GRANT … GRANTED BY supabase_admin`
fallan con `permission denied to grant privileges as role "supabase_admin"`.
**Es esperado y no rompe nada**: son membresías entre roles de plataforma. Las
que importan —`crm_migrator → crm_owner`, otorgada por `postgres`— sí se
aplican, y el verificador lo comprueba.

## 3. Qué ACL de esquemas deben incluirse

Las de los esquemas **fuera** de los tres volcados, restringidas a los nueve
roles del proyecto. Hoy eso es exactamente una línea:

```sql
grant usage on schema extensions to asistente_owner;
```

Sin ella, `job_claim()` falla con `permission denied for schema extensions`.

Se restringe a nuestros roles a propósito: las concesiones a `anon`,
`authenticated`, `service_role` o `dashboard_user` son de la plantilla de
Supabase — en un destino Supabase ya están, y en un PostgreSQL desnudo no
significan nada.

## 4. Qué ACL de objetos deben incluirse

Las de los tres esquemas volcados viajan **dentro** del `.dump`: 231 entradas
`ACL` medidas, que incluyen los 927 `GRANT` a `crm_user` y el `nspacl` de
`public` (`crm_user=UC`, `crm_owner=UC`).

Para que viajen hay una condición: **nunca usar `--no-owner` ni
`--no-privileges`**. Con `--no-owner` la restauración produjo 0 `GRANT` frente a
los 903 de producción (medido en B.7) — el CRM habría quedado sin permisos.

## 5. Cómo se transportan

Tres artefactos. Los tres son obligatorios.

| Artefacto | Cómo se genera | Qué lleva |
|---|---|---|
| `<sello>_datos.dump` | `pg_dump --format=custom` de los 3 esquemas | datos, estructura, dueños y ACL de objetos |
| `<sello>_roles.sql` | `pg_dumpall --roles-only` | roles, atributos y membresías |
| `<sello>_entorno.sql` | **leyendo el catálogo** (`respaldar.py`) | extensiones + su esquema, ACL de esquemas ajenos, `pg_db_role_setting` de nuestros roles |

El tercero existe porque lo que le falta a los dos primeros **no se puede
obtener ampliando el volcado**. Se probó `--schema=extensions`: trae los event
triggers internos de Supabase (`grant_pg_cron_access`, `pgrst_ddl_watch`,
`grant_pg_net_access`) y **no trae la extensión** — `pg_dump` no vuelca
extensiones cuando se le pasa `--schema`.

```bash
py -3.13 despliegue/respaldo/respaldar.py --destino "$CARPETA" \
        [--imagen pgvector/pgvector:pg17]
```

`--imagen` es para máquinas sin las herramientas cliente instaladas. La
**versión mayor debe coincidir** con la del servidor (producción es 17.6).

> **Secretos.** `pg_db_role_setting` incluye ajustes de ámbito «toda la base»
> con el secreto JWT del proyecto. El artefacto 3 los **excluye por diseño**:
> sólo emite ajustes de los nueve roles del proyecto.

## 6-7. Cómo y dónde se instala pgcrypto

En el esquema **`extensions`**. No en `ext`, no en `public`.

```sql
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
```

**La justificación es de producción, no de gusto:** las 10 funciones del
scheduler corren con `search_path = pg_catalog` —un endurecimiento
deliberado—, así que no hay resolución por búsqueda y el nombre calificado
tiene que existir tal cual. Los cuerpos, que PostgreSQL guarda literales,
llaman a `extensions.digest` y `extensions.gen_random_bytes`. En producción
`pgcrypto` está en `extensions` y **el esquema `ext` no existe**.

`pg_trgm` y `vector` van en `public`, que es donde están en producción y donde
los usan los índices del volcado.

## 8. Qué permisos necesita `asistente_owner`

`USAGE` sobre el esquema `extensions`. Nada más.

No hace falta tocar los permisos de las funciones de pgcrypto: su ACL es
`=X/supabase_admin`, o sea que **`PUBLIC` ya puede ejecutarlas**. Lo que falta
nunca es el `EXECUTE` de la función — es el `USAGE` del esquema.

## 9. Orden exacto de restauración

Lo implementa `restaurar.sh`; no hay pasos fuera de él.

```bash
sh despliegue/respaldo/restaurar.sh "$CARPETA" "$SELLO" "$BASE" -U "$USUARIO"
```

1. **Roles.** Primero, o cada `OWNER TO` y cada `GRANT` del volcado falla.
2. **Entorno.** Después de los roles (concede a `asistente_owner`) y **antes**
   del volcado (sus índices usan `pg_trgm` y `vector`).
3. **Datos.** Con el índice filtrado: se quita **sólo** la entrada que *crea*
   el esquema `public`, que ya existe en cualquier base nueva. Su `ACL` no se
   filtra — lleva `crm_user=UC` y `crm_owner=UC`, y sin ellos el migrador no
   puede crear tablas después. El anclaje con espacio final evita cazar
   `COMMENT - SCHEMA public` y `ACL - SCHEMA public`.

## 10. Cómo no depender de privilegios accidentales de quien restaura

- **El artefacto 3 no asume privilegios**: cada extensión va dentro de un
  `DO` con guarda de disponibilidad, que avisa por `NOTICE` en vez de abortar
  la restauración entera si el servidor destino no tiene el binario.
- **Las concesiones son explícitas** (`grant usage on schema extensions to
  asistente_owner`), no heredadas de que quien restaura sea superusuario.
- **La verificación no se hace como superusuario por conveniencia**: la prueba
  funcional ejercita las funciones `SECURITY DEFINER`, que corren como
  `asistente_owner` — si a ese rol le falta un permiso, falla, aunque quien
  llame sea superusuario. Es exactamente así como se detectó el `USAGE`
  faltante.
- **Los errores esperados están acotados y documentados** (los `GRANTED BY
  supabase_admin` del punto 2), en vez de silenciados en bloque.

## 11. Qué NO transporta automáticamente el respaldo

| Elemento | ¿Viaja? | Dónde está resuelto |
|---|---|---|
| Roles y membresías | **sí**, `*_roles.sql` | — |
| ACL de tablas, secuencias y funciones de los 3 esquemas | **sí**, `.dump` (231 entradas) | — |
| `nspacl` de `public` | **sí**, `.dump` | el filtro del índice no lo quita |
| Extensiones | **NO** — 0 entradas `EXTENSION` | artefacto 3 |
| Esquema de cada extensión | **NO** | artefacto 3 |
| ACL de esquemas ajenos a los 3 | **NO** | artefacto 3 |
| `pg_db_role_setting` (`SET role`, timeouts) | **NO** — 0 `IN DATABASE` en el volcado de roles | artefacto 3 |
| Ajustes de ámbito «toda la base» (secreto JWT) | **NO**, y **a propósito** | fuera de alcance |

## 12. Qué verificar explícitamente después de restaurar

```bash
py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto "$PUERTO"
```

**25 comprobaciones estructurales** contra producción: tablas, secuencias,
índices (y ninguno inválido), constraints, políticas, RLS, FORCE RLS, dueños,
tablas y políticas de `asistente`, las 10 funciones `job*` con su
`search_path`, el **md5 conjunto de sus cuerpos**, los `GRANT` a `crm_user`, la
ACL de `job_claim`, los 9 roles, la membresía `crm_migrator → crm_owner`, su
`SET role`, el esquema de `pgcrypto`, la existencia de `extensions`, que
`digest` y `gen_random_bytes` resuelvan, el `USAGE` de `asistente_owner`, y
`pg_trgm`/`vector` en `public`.

**Y la prueba que de verdad decide** — el flujo real del scheduler:

```
job_claim → job_contexto → job_heartbeat → job_finalize  ==>  succeeded
```

comprobando además que la `capability` tenga 64 hex, que el `config_hash` del
contexto coincida con el del claim, y que queden los eventos esperados.

> **`job_salud()` y `jobs_vencidos()` NO valen como prueba del scheduler.**
> Responden igual de bien con el scheduler roto, porque no llaman a `digest`.
> Quedan como controles secundarios.

---

## Criterio de aceptación de un respaldo

Un respaldo **no está validado** hasta que una restauración desde cero, hecha
sólo con `restaurar.sh`, pase `verificar_restauracion.py` con **0 fallas** —
estructurales y funcionales. Un `pg_restore` en 0 no es evidencia: se midió que
también da 0 con el scheduler roto.
