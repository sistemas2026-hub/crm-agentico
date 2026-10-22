# Paso 10.11 — Segregación del operador y el runtime del kill switch

**Fecha:** 17/09/2026
**Producción:** intacta. Ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`,
**0 tablas** de las migraciones 3 y 4, **rol `autonomia_operador` no creado**.
No se aplicaron migraciones, no se cambió `DBUSER`, no se desplegó
`interruptor.py` ni `idempotencia.py`, no se implementó autonomía 0–4, y M02,
M03, M09 y M10 no se tocaron.

> **Todo lo que sigue está medido en réplica**, incluida la simulación de una
> sesión real del motor con un rol que sí puede iniciar sesión.

---

## A. Estado actual

Medido sobre una réplica limpia (B.6/B.7 + las 2 migraciones):

| | |
|---|---|
| Dueño de `asistente.interruptor_autonomia` | `postgres` · RLS **activa** · **FORCE** |
| ACL | `postgres=arwdDxtm`, **`app_backend=ar`** (INSERT + SELECT) |
| Políticas | una sola: `tenant_aislado` · `FOR ALL` · `TO app_backend` |
| Quién tiene algún privilegio | sólo `app_backend` y `postgres` |
| `app_backend` hereda de | **nadie** — revocar el GRANT es suficiente a nivel de privilegio |
| Funciones `SECURITY DEFINER` que escriban en la tabla | **ninguna** |

**El flujo de cambio de estado, auditado:**

```
cli/autonomia.py --detener/--reactivar
  → interruptor.detener()/reactivar()          (valida actor y motivo)
    → db.registrar_transicion_autonomia()
      → db.sesion(tenant)   ← "rol degradado a app_backend"
        → INSERT en asistente.interruptor_autonomia
```

| Pregunta | Respuesta medida |
|---|---|
| Quién puede crear el registro | `app_backend` (vía `sembrar()` en el alta) y la semilla de la migración |
| Quién puede `DETENIDO → ACTIVO` | `app_backend` y `postgres` |
| Quién puede `ACTIVO → DETENIDO` | los mismos |
| Rol PostgreSQL del CLI | **`app_backend`** — `db.sesion()` lo degrada |
| Rol de `app_backend` | el mismo. En producción `motor_user → app_backend` con `SET=True`, otorgado por `supabase_admin` |
| ACL/RLS que intervienen | `app_backend=ar` + la política `tenant_aislado` |
| Qué código puede invocar `registrar_transicion_autonomia()` | `interruptor.detener()` y `reactivar()`, y sólo `cli/autonomia.py` los llama |
| Camino alternativo para insertar `ACTIVO` | **sí: un `INSERT` directo como `app_backend`.** Medido en el paso 10.10 |

## B. Problema encontrado

**La base no puede distinguir al operador del runtime: los dos son
`app_backend`.** La separación existe sólo en el código — ninguna herramienta
del catálogo expone `detener`/`reactivar` — y eso no es una barrera de
privilegio.

Consecuencia concreta: el proceso del motor, con el rol que usa para operar,
puede insertar `'activo'` y reactivar la autonomía sin pasar por
`cli/autonomia.py` ni dejar la validación de actor y motivo.

## C. Modelo de roles propuesto

**Dos roles, y ninguna credencial nueva.**

| | **RUNTIME** | **OPERADOR** |
|---|---|---|
| Rol | `app_backend` (ya existe) | **`autonomia_operador`** (nuevo, `NOLOGIN`) |
| Cómo se alcanza | `motor_user` → `SET ROLE app_backend` | `postgres` → `SET ROLE autonomia_operador` |
| Sobre el interruptor | **SELECT** + `EXECUTE` de la parada | **SELECT + INSERT** |
| Puede activar | **no** | **sí** |
| Puede detener | **sí**, sólo por la función | sí |

`NOLOGIN` es deliberado: no hay contraseña que guardar en Dokploy ni rotar. Se
alcanza por `SET ROLE` desde la credencial que ya existe, que es exactamente lo
que hoy hace `db.sesion()` con `app_backend`.

> **El operador no es un rol de uso normal del runtime**: no tiene login, no es
> miembro de nada, y ningún proceso de servicio puede alcanzarlo — sólo
> `postgres` y `supabase_admin` tienen el privilegio de `SET ROLE` sobre él.

## D. Matriz de permisos

| Rol | SELECT | INSERT | UPDATE | DELETE | `EXECUTE` de `autonomia_detener` | `SET ROLE autonomia_operador` |
|---|---|---|---|---|---|---|
| `app_backend` | **sí** | **no** | no | no | **sí** | **no** |
| `autonomia_operador` | sí | **sí** | no | no | sí | — |
| `motor_user` | no | no | no | no | no | **no** |
| `crm_user` | no | no | no | no | no | **no** |
| `job_executor`, `scheduler_coordinator`, `monitor_ro` | no | no | no | no | no | **no** |
| `asistente_owner`, `service_role` | no | no | no | no | no | **no** |
| `postgres` | sí | sí | sí | sí | sí | **sí** |

**Nadie tiene `UPDATE` ni `DELETE`.** El interruptor es de solo agregar: el
estado vigente es la fila más reciente, y el historial no se reescribe ni se
borra.

> **`postgres` queda fuera del modelo, y no puede ser de otra manera:** tiene
> `BYPASSRLS` y `CREATEROLE`, así que puede otorgarse cualquier cosa. Es la
> credencial de emergencia. La segregación separa **el runtime del motor** del
> operador, no `postgres` del operador.

## E. SQL necesario

```sql
-- 1) el rol de operador -- NOLOGIN: no es una credencial nueva
create role autonomia_operador nologin;
grant autonomia_operador to postgres with inherit false, set true;

-- 2) el runtime pierde la escritura directa (conserva SELECT)
revoke insert on asistente.interruptor_autonomia from app_backend;

-- 3) el operador es el unico con escritura directa
grant usage on schema asistente to autonomia_operador;
grant select, insert on asistente.interruptor_autonomia to autonomia_operador;

--    con FORCE RLS, un rol sin politica no ve ni escribe nada
create policy tenant_aislado_operador on asistente.interruptor_autonomia
  for all to autonomia_operador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

-- 4) la parada de emergencia del runtime
create or replace function asistente.autonomia_detener(
        p_org uuid, p_actor text, p_motivo text)
returns asistente.interruptor_autonomia
language plpgsql security definer set search_path = pg_catalog
as $$
declare v_anterior text; v_fila asistente.interruptor_autonomia;
begin
  if coalesce(btrim(p_actor),  '') = '' then
    raise exception 'hay que decir QUIEN detiene la autonomia'; end if;
  if coalesce(btrim(p_motivo), '') = '' then
    raise exception 'hay que decir POR QUE se detiene la autonomia'; end if;
  if not exists (select 1 from public.organization o where o.id = p_org) then
    raise exception 'la organizacion % no existe', p_org; end if;

  select i.estado into v_anterior from asistente.interruptor_autonomia i
   where i.organization_id = p_org order by i.creado_en desc, i.id desc limit 1;

  insert into asistente.interruptor_autonomia
         (organization_id, estado, estado_anterior, actor, motivo)
  values (p_org, 'detenido', v_anterior, btrim(p_actor), btrim(p_motivo))
  returning * into v_fila;
  return v_fila;
end $$;

revoke all on function asistente.autonomia_detener(uuid,text,text) from public;
grant execute on function asistente.autonomia_detener(uuid,text,text)
  to app_backend, autonomia_operador;
```

**No se creó como archivo de migración**, para no alterar el conjunto de cuatro
pendientes que el paso 10.8 dejó separado. Queda pendiente de autorización.

## F. Funciones que cambiarían

Sólo una, y **no se modificó**: `nucleo/persistencia/db.py`.

`registrar_transicion_autonomia()` usa `sesion(tenant)`, que degrada a
`app_backend`. Con el `INSERT` revocado, dejaría de funcionar. Haría falta una
variante que degrade a `autonomia_operador` — por ejemplo un parámetro
`rol="app_backend"` en `sesion()`, usado sólo por esa función.

`interruptor.sembrar(cur, …)` recibe el cursor de quien la llama
(`cli/cargar_config.py`), así que hereda el rol de esa sesión: el alta de un
tenant tendría que usar la misma variante.

**No se tocó `db.py`** porque para probarlo no hacía falta: la prueba de réplica
usa `SET ROLE autonomia_operador` directamente, que es exactamente lo que ese
cambio haría.

## G. Riesgos

1. **Hasta que `db.py` cambie, el CLI queda roto** si se aplica el `REVOKE`:
   `cli/autonomia.py` corre como `app_backend` y perdería el `INSERT`. **El SQL
   de §E y el cambio de §F tienen que ir juntos.**
2. **`postgres` sigue pudiendo todo.** Y hoy el tráfico del CRM circula como
   `postgres` (`DBUSER`), así que esa credencial puede alcanzar el rol de
   operador. Se cierra con el paso 15 (`DBUSER → crm_user`): `crm_user` no es
   miembro ni tiene `CREATEROLE`.
3. **La asimetría es deliberada, no accidental** — ver §«Sobre detener».
4. **La función es `SECURITY DEFINER` y su dueño es `postgres`**, que tiene
   `BYPASSRLS`. Su alcance está contenido por el `search_path = pg_catalog` y
   por tener el estado escrito en el cuerpo, pero es poder real: cualquier
   cambio a esa función hay que revisarlo como código de seguridad.
5. **`autonomia_operador` no viaja en el artefacto de entorno**, sino en el de
   roles. Es correcto, pero significa que una restauración sin ese artefacto
   deja el modelo a medias.
6. **`motor_user` tiene `BYPASSRLS`** (medido en producción). No le sirve para
   escribir —no tiene privilegio sobre la tabla— pero sí para **leer** filas de
   cualquier organización si alguna vez se le concediera `SELECT`.

## Sobre detener — la asimetría, documentada

**`app_backend` puede detener. No puede activar.**

| | |
|---|---|
| **Por qué puede** | Parar es seguro y arrancar no. El costo de una parada indebida es que el agente deja de actuar solo, y se revierte con una reactivación auditada. El costo de una activación indebida es una escritura contra un tercero que nadie autorizó. |
| **Mediante qué función** | `asistente.autonomia_detener(p_org, p_actor, p_motivo)`, `SECURITY DEFINER`, `search_path = pg_catalog` |
| **Qué estados puede escribir** | **uno solo: `'detenido'`** |
| **Cómo queda auditado** | la función calcula `estado_anterior` leyendo la fila vigente, y exige `actor` y `motivo` no vacíos — levanta excepción si faltan |
| **Sólo `DETENIDO ← ACTIVO`** | escribe `'detenido'` cualquiera sea el estado previo, que queda anotado en `estado_anterior`. No hay transición que pueda producir `'activo'` |
| **Qué impide activar por esa vía** | **el estado no es un parámetro: está escrito en el cuerpo.** Probado: `autonomia_detener(org,'motor','x','activo')` → *«function … does not exist»* — ese parámetro no existe |

## H-I. Pruebas realizadas y su resultado

### Los 8 casos

| # | Caso | Esperado | Resultado |
|---|---|---|---|
| 1 | `app_backend` INSERT con `activo` | DENEGADO | **`InsufficientPrivilege`** · estado sin cambio |
| 2 | `app_backend` cambia `DETENIDO → ACTIVO` | DENEGADO | **`InsufficientPrivilege`** · sigue `detenido` |
| 3 | `app_backend` lee el estado | PERMITIDO | **lee** `detenido` |
| 4 | Operador `DETENIDO → ACTIVO` | PERMITIDO + auditoría | **`activo`** · actor `mayra`, motivo y fecha |
| 5 | Operador `ACTIVO → DETENIDO` | PERMITIDO + auditoría | **`detenido`** · con actor y motivo |
| 6 | Rol no autorizado intenta activar | DENEGADO + sin cambio | **6 de 6 denegados** (`crm_user`, `motor_user`, `job_executor`, `scheduler_coordinator`, `monitor_ro`, `asistente_owner`) · estado sin cambio |
| 7 | Tenant nuevo | registro creado, `DETENIDO`, nunca `ACTIVO` | **creado** · `detenido` · **0 filas `activo`** |
| 8 | Saltarse el flujo | DENEGADO para runtime | `UPDATE`, `DELETE` y `TRUNCATE` **denegados** para `app_backend`; `UPDATE` **también denegado al operador** |

### Sesión real del motor

Con `sim_motor` —doble fiel: `LOGIN`, `BYPASSRLS`, miembro de `app_backend` con
`SET`, igual que `motor_user` en producción— **cinco vías de activación, todas
cerradas**:

```
set role autonomia_operador  -> ERROR: permission denied to set role "autonomia_operador"
INSERT 'activo'              -> ERROR: permission denied for table interruptor_autonomia
UPDATE  estado='activo'      -> ERROR: permission denied for table interruptor_autonomia
DELETE  del historial        -> ERROR: permission denied for table interruptor_autonomia
autonomia_detener(…,'activo')-> ERROR: function … does not exist
create function propia       -> ERROR: permission denied for schema asistente
estado final: detenido
```

Y la parada **sí** le funciona: `estado tras la parada: detenido`, código 0.

> Un detalle de la réplica que hay que nombrar: la primera corrida con
> `SET SESSION ROLE motor_user` **pareció** llegar al operador. No era cierto —
> `session_user` seguía siendo `postgres`, y `SET ROLE` se evalúa contra el
> *session_user*, no contra el rol actual. De ahí el doble con login.
>
> Y otro: la réplica no traía la membresía `motor_user → app_backend`, porque el
> `roles.sql` no puede recrear las líneas `GRANTED BY supabase_admin`. Se
> verificó contra producción (existe, con `SET=True`) y se añadió a mano antes
> de la prueba.

### Auditoría

Cada transición conserva: `organization_id`, `estado_anterior`, `estado`,
`actor`, `motivo`, `creado_en`. **No hay `origen/canal` como columna** — el
`actor` lo lleva por convención, y `asistente.audit_log` registra el hecho
aparte (`interruptor.anotar_bloqueo` y `registrar_auditoria`). El historial
completo se conservó: 8 transiciones tras la batería, ninguna borrada.

*(En el historial aparecen filas con `estado_anterior = None` porque mi prueba
insertó directamente con `null`; el flujo real lo calcula en
`interruptor._mover()` y la función de parada también.)*

### RLS, ownership y vías de evasión

| Comprobación | Resultado |
|---|---|
| `app_backend` hereda de algún rol con INSERT | **no hereda de nadie** |
| `app_backend` puede `CREATE` en `asistente` | **no** |
| `app_backend` puede `SET ROLE autonomia_operador` | **no** |
| `motor_user` / `crm_user` pueden | **no** |
| Quién sí puede | sólo `postgres` y `supabase_admin` |
| Atributos de ambos roles | `login=false bypassrls=false super=false createrole=false` |
| Otras funciones `SECURITY DEFINER` que escriban en la tabla | **sólo `autonomia_detener`** |
| `search_path` de la función | `pg_catalog` |
| Aislamiento entre organizaciones | **se mantiene también para el operador**: intentar escribir para otra organización dio `new row violates row-level security policy` |

### Batería completa (§8)

| Prueba | Resultado |
|---|---|
| Instalación limpia (B.6/B.7 + 2 migraciones) | `restaurar.sh` código 0 |
| Respaldo | 3 artefactos · el rol nuevo aparece 3 veces en `*_roles.sql` |
| Restauración desde cero | código 0 |
| Roles / ACL / RLS tras el ciclo | **todo sobrevive**: rol, membresía con `SET`, `app_backend=r` (sin INSERT), las 2 políticas, la función con `secdef=true` y su `EXECUTE` |
| Los 8 casos sobre la restaurada | **0 fallas** |
| Scheduler / motor | `job_claim → job_finalize` = **`succeeded`**, 0 fallas |
| Tabla ausente | **BLOQUEA** · `sin_instalar` |
| Base caída | **BLOQUEA** · `desconocido` |
| Activación / detención | casos 4 y 5, con auditoría |
| Tenant nuevo | `detenido` |
| Acceso directo | denegado por las 5 vías |

## J. Qué quedaría pendiente para producción

1. **El SQL de §E como migración nueva**, junto con —no antes de— el cambio de
   §F en `db.py`. Aplicar el `REVOKE` sin el cambio de código **rompe
   `cli/autonomia.py`**.
2. **El cambio en `nucleo/persistencia/db.py`**: una variante de `sesion()` que
   degrade a `autonomia_operador`, usada por `registrar_transicion_autonomia()`
   y por el alta de tenants.
3. **Decidir el dueño** de las dos tablas de las migraciones 3 y 4
   (`postgres` por omisión, frente a `asistente_owner` de las `job_*`).
4. **Aplicar las migraciones 3 y 4** — no hecho.
5. **Desplegar** `interruptor.py`, `idempotencia.py` y los cambios de
   `motor.py`, `reloj.py`, `api.py` y `coordinador.py` — no hecho, y **después**
   de las migraciones.
6. **El paso 15 (`DBUSER → crm_user`)**, que es lo que cierra el riesgo 2:
   mientras el CRM circule como `postgres`, esa credencial alcanza el rol de
   operador.
7. **Reactivar la autonomía** de Rapilink, que con la semilla corregida nacerá
   `detenida` — acto explícito y auditado, posterior a todo lo anterior.

## Autonomía 0–4: NO implementada

El control sigue siendo **binario**: `activo` / `detenido`, más tres estados de
control no disponible que bloquean (`sin_registro`, `desconocido`,
`sin_instalar`). Lo único que lo modula es
`es_accion_autonoma(herramienta, aprobada_por_humano)`. **Los niveles 0–4 no
existen en el código y este paso no los implementó ni amplió su alcance.**

---

## Regla de cierre

| Exigido | Demostrado |
|---|---|
| `app_backend` NO puede activar | **sí** — 5 vías cerradas, con sesión real de motor |
| Operador autorizado SÍ puede activar | **sí** — caso 4, con auditoría |
| Operador autorizado SÍ puede detener | **sí** — caso 5, con auditoría |
| `app_backend` ejecuta runtime sin privilegios administrativos | **sí** — lee el estado, ejecuta la parada, y el scheduler completa `succeeded` |
| Nuevo tenant nace DETENIDO | **sí** — caso 7, 0 filas `activo` |
| No existe camino alternativo para activar | **sí** — INSERT, UPDATE, DELETE, `SET ROLE`, función forjada y función propia, todos denegados |
| Todo queda auditado | **sí** — actor, motivo, estado anterior, fecha; historial íntegro |
| Backup/restore conserva el comportamiento | **sí** — los 8 casos con 0 fallas sobre la réplica restaurada |

**Con una condición que no es opcional:** el `REVOKE` de §E y el cambio de §F
van juntos. Aplicado solo el primero, `cli/autonomia.py` deja de poder mover el
interruptor — que es peor que el problema que se está arreglando.

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, **0
tablas** de las migraciones 3 y 4, **`autonomia_operador` no existe**. Réplicas
eliminadas. No se modificó `db.py` ni ningún archivo de `nucleo/` en esta etapa.
