# Corte legacy → persistent, deshabilitación y rollback

> **Estado: DISEÑO. Nada de este documento está implementado en P2.**
> El candidato `79b1f10` no contiene la tabla de propiedad, la función
> administrativa ni el modo sombra. Todo lo que sigue es **NO VERIFICADO**
> hasta que P5 lo implemente y lo mida.

## Por qué el plan anterior estaba mal

El plan de integración del informe anterior decía: encender el scheduler
persistente para un tenant y retirar `nucleo/reloj.py` "cuando lleve 24 h
estable". Durante esas 24 h **los dos caminos ejecutarían `importacion_tickets`
para el mismo tenant**.

Que la importación sea idempotente (UNIQUE sobre `cases_case`) no lo arregla:
el doble recorrido duplica las llamadas a WispHub y al CRM, duplica la carga,
y convierte cada error de uno de los dos caminos en ruido que no se puede
atribuir. Y `cerrar_vencidas` —que no es idempotente— haría imposible siquiera
plantearlo.

Tampoco alcanza con dos interruptores independientes (`RELOJ_HABILITADO` en el
entorno y `job_catalogo.habilitado` en la base): nada impide que los dos queden
encendidos a la vez. La exclusión tiene que salir de **un solo estado
compartido, leído bajo un lock por los dos caminos**.

---

## P7 · Propiedad única por `(job_code, organization_id)`

### El estado

```sql
create table asistente.job_propiedad (
  job_code        text not null references asistente.job_catalogo(code),
  organization_id uuid not null references public.organization(id),
  propietario     text not null check (propietario in ('legacy','persistent','disabled')),
  sombra          boolean not null default false,
  version         bigint not null default 0,
  cambiado_en     timestamptz not null default now(),
  primary key (job_code, organization_id)
);
```

Una fila por par. **Ausencia de fila = `legacy`** para el reloj viejo y
**= no es mío** para el scheduler persistente: el camino nuevo es fail-closed,
el viejo conserva el comportamiento de hoy.

### El mecanismo de exclusión

Dos locks, uno por cada frontera, y ninguno depende de que un proceso "se
acuerde" de mirar un flag:

| quién | qué lock toma | qué comprueba bajo ese lock |
|---|---|---|
| **reloj viejo**, antes de cada `(job, tenant)` | `pg_try_advisory_lock(NS, k)` de **sesión**, en una conexión dedicada que mantiene durante todo el barrido | `propietario = 'legacy'`. Si no, suelta y omite |
| **`job_claim`** (persistente) | `select … for update` sobre la fila de `job_schedule_state` (ya lo hace) | `propietario = 'persistent'`, releído dentro del lock |
| **transición `legacy → persistent`** | `pg_try_advisory_xact_lock(NS, k)` + `for update` de `job_propiedad` | si el advisory lock no se obtiene, hay un barrido viejo en curso: **se rechaza**, no se espera |
| **transición `persistent → legacy`** | `for update` de `job_schedule_state` (serializa con `job_claim`) + el mismo advisory lock | no hay intento con lease vivo **ni** vencido hace menos que el período de gracia |

`k` sale de `('x' || substr(md5(job_code || ':' || organization_id), 1, 8))::bit(32)::int`
y `NS` es una constante fija escrita a mano. **No** `hashtext`: no está
documentado como estable entre versiones.

Por qué con esto nunca hay dos propietarios activos:

- El reloj viejo no corre sin `k`, y relee `propietario` **después** de
  obtenerlo. La transición a `persistent` necesita `k`. Así que o el barrido
  viejo empezó antes (y la transición se rechaza) o empieza después (y ve
  `persistent` y omite).
- `job_claim` y la transición desde `persistent` bloquean la **misma fila** de
  estado. O el claim ocurre antes (y hay lease vivo: la transición se rechaza) o
  después (y el claim ve que ya no es `persistent`).
- El advisory lock de sesión del reloj viejo **se libera solo si el proceso
  muere**: una caída del reloj no deja el par bloqueado para siempre.

### El riesgo residual que el lock no cubre

Un ejecutor persistente cuyo lease venció pero que **sigue vivo** (congelado,
GC, red partida) ya no puede escribir en la base —el fencing lo rechaza— pero
**puede seguir haciendo llamadas al proveedor**. Si en ese instante se
transfiere a `legacy`, el reloj viejo podría correr al mismo tiempo que los
efectos laterales del zombi.

Mitigación, no eliminación: la transición `persistent → legacy` exige que el
último lease esté vencido hace más que un **período de gracia** (propuesta:
3 × `lease_duracion`), y los handlers largos miran `turno.lease_perdido` entre
partes. Queda escrito como riesgo, no como propiedad.

### Modo sombra

`sombra = true` con `propietario = 'legacy'`: el coordinador persistente
calcula `jobs_vencidos` para ese par y **registra lo que habría hecho** en una
tabla de observación (slot que calculó, cuándo), **sin reclamar**. Del lado
viejo se registra cuándo corrió de verdad.

Criterio para pasar a `persistent`: al menos 48 ciclos horarios sin
discrepancias no explicadas entre el slot calculado y la ejecución vieja
(desalineaciones esperables por la deriva conocida de +33,7 s/ciclo del reloj
viejo se clasifican, no se ignoran).

### El flujo

1. Desplegar el scheduler **inerte**: catálogo sin la fila del job, o con
   `habilitado = false`. Ninguna fila en `job_propiedad` → todo sigue `legacy`.
2. Activar `sombra = true` para **un** tenant.
3. Comparar durante el período del criterio.
4. `job_transferir_propiedad(job, tenant, 'persistent', motivo, version)`.
   Atómico. Si hay un barrido viejo en curso, se rechaza y se reintenta.
5. Desde ese instante el reloj viejo omite ese par — lo decide al releer bajo
   su lock, no porque alguien cambió una variable de entorno.
6. Observar un ciclo completo con `cli/salud_scheduler.py`.
7. Ampliar de a un tenant.
8. Rollback por tenant: `persistent → legacy` con la misma función.
9. En ningún punto del flujo hay dos propietarios activos para el mismo par.

Retirar el código de `nucleo/reloj.py` es un paso **posterior** y separado,
cuando ningún par quede en `legacy`.

### Qué cambia en código (P5, no P2)

- Migración nueva: `job_propiedad`, `job_propiedad_evento`, la función de
  transferencia, y `jobs_vencidos`/`job_claim` filtrando por
  `propietario = 'persistent'`. **El candidato `79b1f10` no se modifica**:
  estas funciones se reemplazan en una migración posterior.
- `nucleo/reloj.py`: el guard de advisory lock + relectura por `(job, tenant)`.
- Coordinador: modo sombra.

---

## P8 · Deshabilitación administrativa

`UPDATE asistente.job_catalogo SET habilitado = false` **no** es un
procedimiento: no queda registro de quién ni por qué, no es por tenant, y
requiere un usuario con DML sobre una tabla que ningún rol de runtime puede
tocar.

### La función

```sql
asistente.job_transferir_propiedad(
  p_job_code          text,
  p_organization_id   uuid,
  p_nuevo             text,     -- 'legacy' | 'persistent' | 'disabled'
  p_motivo            text,     -- obligatorio, no vacío
  p_version_esperada  bigint    -- concurrencia optimista
) returns table (propietario text, version bigint, resultado text)
```

| propiedad | cómo |
|---|---|
| **autenticada** | la sesión es de un login real con contraseña del gestor de secretos; nunca `motor` |
| **autorizada** | `SECURITY DEFINER` de `asistente_owner`; `EXECUTE` solo para un rol nuevo `scheduler_admin` (NOLOGIN), asumido por `admin_login` |
| **quién** | se registra `session_user`, **no** `current_user`: dentro de una función SECURITY DEFINER `current_user` es el dueño y no dice nada de quién la llamó |
| **transaccional** | una transacción: lock, verificación, cambio de fila, evento |
| **auditada** | `job_propiedad_evento` append-only: `de`, `a`, `motivo`, `session_user`, `ocurrido_en`, `version`. Sin GRANT de UPDATE/DELETE para nadie y un trigger que los rechaza |
| **idempotente** | si ya está en `p_nuevo`, devuelve `resultado = 'sin_cambio'` y **no** escribe evento |
| **tenant-scoped** | un par por llamada. No hay comodín. Una operación masiva es un bucle explícito en el comando, con un evento por par |
| **segura ante carreras** | si `version` no coincide con `p_version_esperada`, falla: otra persona cambió el estado mientras se decidía |

`persistent → disabled` es **siempre** permitido, con lease vivo o sin él: es
el freno. Su efecto es que no se reclaman turnos nuevos; el intento en curso
termina o vence su lease. `disabled → legacy` y `persistent → legacy` exigen las
condiciones de la sección P7.

El comando `cli/scheduler_admin.py` envuelve la función, exige `--motivo`
y muestra el estado antes y después. No acepta `--force`.

---

## Drenaje de un intento activo

La propiedad tiene tres estados (`legacy | persistent | disabled`). El drenaje
**no** es un cuarto estado: es la fase entre `persistent → disabled` y
`disabled → legacy`, y su final lo decide la base, no un reloj de pared.

1. `persistent → disabled`, siempre permitido. Desde esa transacción
   `jobs_vencidos` y `job_claim` dejan de devolver el par: ni turnos nuevos ni
   **reintentos**.
2. El intento en curso, si hay uno, **termina o vence**. No se lo mata: el
   ejecutor lo ve en su siguiente comprobación de lease (abajo).
3. `disabled → legacy` solo se acepta cuando, bajo el `for update` de
   `job_schedule_state`:
   - no hay intento con `outcome is null`; **o**
   - el último `lease_until` venció hace más que el período de gracia
     (3 × `lease_duracion`), y el intento abierto se cierra en esa misma
     transacción como `lease_lost`.
4. Un run que quedó en `retry_wait` al deshabilitar se cierra en esa transacción
   con el estado terminal nuevo **`cancelado_por_transferencia`** y su evento. Sin
   esto, el día que el par vuelva a `persistent` se reintentaría un turno viejo
   contra una grilla que ya siguió de largo.

Tiempo máximo de drenaje declarado: `lease_duracion` + período de gracia. Si se
excede —ejecutor colgado que sigue latiendo—, la función de transferencia
informa el intento que lo impide y **no** fuerza nada; la acción siguiente es
operativa y queda auditada.

## Efectos externos: comprobar antes, aceptar lo que no se puede deshacer

El ejecutor comprueba lease y fencing **antes de cada nuevo efecto externo**
(cada llamada a WispHub, al CRM o al canal):

```python
turno.antes_de_efecto("crear_caso")   # job_heartbeat; si devuelve NULL -> LeasePerdido
proveedor.crear_caso(..., idempotency_key=turno.clave_de_efecto("crear_caso", n))
```

- Si la comprobación falla, el handler no inicia ese efecto ni los siguientes.
- `turno.clave_de_efecto` deriva de `job_run.idempotency_key` + nombre del efecto +
  ordinal. Es estable entre intentos del mismo run.

**Límite declarado, no mitigable desde el scheduler:** una llamada ya enviada no
se puede cancelar. Entre la comprobación y la respuesta puede vencer el lease; el
efecto puede quedar hecho y el intento sin registrar, y el reintento lo repetirá.
Por eso:

- **Ningún handler se cablea sin idempotencia del destino documentada y probada.**
  `importacion_tickets`: `UNIQUE (org, provider, external_ticket_id)` en
  `cases_case` hace converger dos creaciones. `cerrar_vencidas`: no la tiene
  —el texto de cierre aparece dos veces en el ticket del proveedor— y sigue
  **bloqueado**.
- Si el destino no acepta clave de idempotencia, el handler consulta el estado
  del destino antes de escribir, y eso también se documenta como no atómico.

---

## Rollback

En este orden, y sin saltear pasos:

1. **Transferencia auditada** de cada par en `persistent`, con
   `job_transferir_propiedad`: a `disabled` si solo hay que frenar, o a `legacy`
   si el reloj viejo debe retomar. Queda registrado quién, cuándo y por qué.
2. **Drenaje**: esperar que no quede intento activo, o cerrar el vencido según la
   sección anterior. La transferencia a `legacy` no se acepta antes.
3. **Redeploy del digest de imagen anterior compatible.** Cada despliegue
   registra el digest (`sha256:…`) que corrió; volver atrás es desplegar ese
   digest, no reconstruir desde un `git revert` improvisado que produce una
   imagen que nunca se probó. *Compatible* quiere decir que las migraciones de P2
   y P5 son *expand-only*: el código anterior no conoce `job_*` ni
   `job_propiedad` y no las lee. **Nunca migrate-down automático**: el ledger no
   tiene "bajar".
4. **Conservar** tablas, runs, intentos, eventos, propiedad y ledger. Son la
   evidencia del incidente que motivó el rollback.

### Lo que NO es rollback

`DROP TABLE`, `DROP FUNCTION` y `DROP ROLE` sobre el scheduler son una
**desinstalación destructiva**. Es un procedimiento aparte que exige:

- autorización propia, distinta de la del rollback;
- respaldo verificado de `job_run`, `job_attempt`, `job_run_event`,
  `job_propiedad` y `job_propiedad_evento` antes de tocar nada;
- una política de retención escrita que diga cuánto tiempo se guarda ese
  respaldo y quién puede leerlo;
- no ejecutarse nunca como respuesta a un incidente.
