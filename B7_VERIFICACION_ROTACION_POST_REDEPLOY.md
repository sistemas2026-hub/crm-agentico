# B-7 — VERIFICACIÓN DE LA ROTACIÓN POST-REDEPLOY

Fecha: 2026-09-19 · **NO PASS**

Solo lectura. Ningún secreto impreso. Sin commit, sin `git stash`, sin tocar
producción, sin eliminar el GUC, sin revocar `CREATE`, sin cambiar `DBUSER`, sin
activar Autonomía 2, sin levantar el kill switch.

---

# EL RESULTADO, PRIMERO

**Los contenedores del stack de Supabase no se recrearon.** Siguen siendo los
mismos procesos de hace 51 horas — mismos PID — así que están corriendo con la
configuración que cargaron entonces, **anterior a la rotación**.

No declaro PASS. La instrucción es explícita: *«Si el secreto anterior NO puede
demostrarse inválido, NO declarar PASS»*, y aquí no solo no puede demostrarse:
la evidencia apunta en sentido contrario.

---

# 1. CONFIGURACIÓN ACTUAL

| Qué | Resultado |
|---|---|
| `JWT_SECRET` presente en los servicios | **NO VERIFICABLE** |
| `ANON_KEY` presente | **NO VERIFICABLE** |
| `SERVICE_ROLE_KEY` presente | **NO VERIFICABLE** |
| Los contenedores en ejecución tienen configuración posterior al redeploy | **NO** — medido |

**Por qué NO VERIFICABLE en los tres primeros:** no tengo acceso a Dokploy (sin
variables `DOKPLOY_*`, sin CLI, sin `~/.dokploy`, sin token). Lo que hay en sus
formularios no lo puedo leer desde aquí, y no lo invento.

**Por qué NO en el cuarto, que sí es medible:**

```
usuario                  pid      app                            conectado hace
supabase_admin           192389   pg_net 0.20.3                  51h 10m
supabase_admin           192390   pg_cron scheduler              51h 10m
authenticator            192396   PostgREST 14.12                51h 10m
supabase_storage_admin   192406                                  51h 10m
supabase_admin           192492   supabase_mt_realtime           51h 10m
supabase_admin           192493   supabase_mt_realtime           51h 10m
supabase_admin           192494   supabase_mt_realtime           51h 10m
supabase_admin           192495   supabase_mt_realtime           51h 10m
supabase_admin           192496   supabase_mt_realtime           51h 10m
supabase_admin           192497   cluster_node_realtime@127.0.0. 51h 10m
supabase_admin           192498   cluster_node_realtime@127.0.0. 51h 10m
pgbouncer                422694   Supavisor (auth_query)         0h  3m
```

Once procesos, **51 h 10 m** todos, y son **exactamente los mismos PID** que medí
una hora antes (192389, 192390, 192396, 192406, 192492–192498): un minuto más
viejos, ni uno reemplazado.

Un contenedor recreado mata su proceso y abre conexiones nuevas. Estos no
murieron. Por tanto **no se recrearon**, y su entorno es el de hace 51 horas.

El único joven es `pgbouncer` (Supavisor, 3 min), y ese recicla conexiones
permanentemente por diseño: no es evidencia de nada.

---

# 2. INVALIDACIÓN DEL SECRETO ANTERIOR

## `SECRETO_ANTERIOR_INVALIDO = NO_VERIFICADO`

Y hay que decir más que eso: **la evidencia apunta a que sigue vigente**, porque
los procesos que lo usan no se reiniciaron.

## Qué falta, exactamente

Tres cosas, y ninguna la puedo resolver yo:

1. **Los contenedores no se recrearon** (§1). Aunque tuviera material para
   comparar, los servicios seguirían validando con el secreto que cargaron hace
   51 horas. Esto es lo bloqueante.
2. **El token anterior ya no está.** `SUPABASE_SERVICE_ROLE_KEY` se quitó del
   `.env` (el archivo cambió hace minutos). Era la muestra contra la cual
   comprobar que el secreto viejo ya no firma un token válido.
3. **El archivo del generador se borró.** `C:\Users\Usuario\rotacion_jwt_*.txt`
   no existe. Con él podía comparar —sin exponer nada, solo un booleano— si el
   `JWT_SECRET` nuevo difiere del que guarda el GUC.

Los puntos 2 y 3 son buena higiene y no los critico: es lo que le indiqué hacer.
Lo que hacen es quitar las dos únicas vías de comprobación *offline* que me
quedaban, así que la prueba pasa a depender enteramente del punto 1.

## Cómo se prueba cuando los contenedores sí se recreen

Sin exponer nada y sin presentar ningún token a ningún servicio:

- **Señal necesaria y medible ahora mismo:** las conexiones de `PostgREST`,
  `supabase_mt_realtime` y `supabase_storage_admin` tienen que pasar de **51 h a
  minutos**. Mientras sigan viejas, el secreto viejo sigue cargado en memoria.
- **Prueba directa, si se conserva una copia del token anterior** (en un archivo
  fuera del repositorio, no en un chat): comparo por HMAC-SHA256 si el secreto
  del GUC todavía firma su firma, y si el nuevo `JWT_SECRET` difiere del GUC.
  Informo solo `SÍ`/`NO`.

**No invento un PASS.**

---

# 3. FUNCIONAMIENTO ACTUAL

## `SERVICIOS_OPERATIVOS = PASS`

```
conexiones vivas de los servicios de Supabase : 11
PostgREST 14.12                                : conectado, idle
supabase_mt_realtime (×5) + cluster_node (×2)  : conectados, idle
supabase_storage_admin                         : conectado, idle
pg_cron scheduler                              : corriendo
pg_net 0.20.3                                  : conectado
la base responde y acepta consultas            : sí
```

Todos operativos. Con el matiz que importa: **están operativos porque nada
cambió**, no porque hayan tomado bien una configuración nueva. Este PASS no
respalda la rotación; solo dice que no hay nada caído.

Solo *health checks* y lecturas. Ninguna operación destructiva, ningún dato de
negocio modificado.

---

# 4. CAMINO `SERVICE_ROLE`

## `CAMINO_SERVICE_ROLE_ANTERIOR = ABIERTO`

Medido ahora:

```
service_role     bypassrls=True   login=False
authenticator    bypassrls=False  login=True
anon             bypassrls=False  login=False
authenticator -> SET ROLE service_role : True
crm_user puede leer pg_db_role_setting : True
```

Los tres eslabones siguen exactamente como estaban:

1. el secreto de firma sigue en un GUC **legible por `crm_user`**;
2. `service_role` conserva **`BYPASSRLS`**;
3. `authenticator` —el rol con el que entra PostgREST— puede **`SET ROLE
   service_role`**.

Y los servicios que validarían ese token siguen corriendo con la configuración
anterior. Nada de esto se cerró.

---

# 5. GUC

## `GUC_PRESENTE = SÍ`

```
app.settings.jwt_secret : existe, 32 caracteres
```

Sigue en **32 caracteres**, el mismo largo que antes de la rotación. El
generador que le entregué produce **64**, así que si el GUC hubiera sido
reescrito con el valor nuevo mediría 64.

**Esto NO es un fallo de la rotación**, como dice la instrucción: Dokploy no toca
el GUC — es una copia aparte, dentro de la base. Su eliminación es la Fase 2 del
cierre de B-7, y **no la ejecuté**.

---

# 6. AUTONOMÍA Y PRODUCCIÓN

| Qué | Valor | |
|---|---|---|
| tablas en `public` | **135** | ok |
| roles | **41** | ok |
| `django_migrations` | **192** | ok |
| tablas con FORCE RLS | **66** | ok |
| `asistente.nivel_autonomia` | no existe | ok |
| `asistente.autorizacion_herramienta` | no existe | ok |
| `asistente.ejecucion_autonoma` | no existe | ok |
| kill switch | **detenido** | ok |
| `DBUSER` efectivo | **postgres** | ok |
| `AUTONOMIA_2_ACTIVA` | ausente del `.env` = apagada | ok |
| `case` | **214** (antes 213) | **investigado — ver abajo** |

## El único movimiento: `case` 213 → 214

La instrucción manda detener y reportar exactamente qué cambió. Lo investigué
antes de reportarlo, porque `case` es una **tabla viva**:

```
nombre : "No Tiene Internet"
creado : 2026-09-19 15:05:53
provider: 'wisphub'   external_ticket_id: '93274'   is_sample: false
```

Y su rastro en `activity`: `CREATE Case` a las 15:05:53.38, `ASSIGN Case` a las
15:05:53.51. Es el **importador de tickets de WispHub** trayendo un ticket real,
seguido del enrutamiento automático. Actividad de negocio, no de este trabajo.

Comprobado además que **nada de Autonomía 2 tocó producción**:

```
tags creados hoy                     : 0
actividades de operaciones (M02/M09) : 0
casos con 'smoke'  en el nombre      : 0
casos con 'piloto' en el nombre      : 0
```

> **Un susto y una corrección de método.** Mi primera consulta reportó «4 casos
> con B7/smoke/piloto/etiqueta». Los miré uno por uno antes de alarmar: los
> cuatro coinciden por `b7` **dentro de un identificador hexadecimal**
> (`#11dab7b8`, `#6c8b4b79`, `#b78a1f0e`, `#9d2a7b7c`), son de agosto y del 8 de
> septiembre, y están cerrados. El patrón `%B7%` era demasiado laxo. Cero
> coincidencias reales.

> **Y una corrección a mi propio baseline.** Tenía `case = 213` en la lista de
> valores fijos. Está mal: `case` crece con el uso real del CRM, igual que
> `activity` — la misma lección que ya quedó anotada cuando `activity` pasó de
> 610 a 612. Sale de la lista de contadores fijos; el indicador válido es el
> filtro por `entity_type` de operaciones, que sigue en **0**.

**Ningún cambio atribuible a este trabajo.** No detengo el bloque por esto: el
único movimiento tiene causa identificada y ajena.

---

# CRITERIO DE PASS

| # | Criterio | Resultado |
|---|---|---|
| 1 | la nueva configuración está presente | **NO** — los contenedores no se recrearon |
| 2 | los servicios siguen operativos | **PASS** |
| 3 | el secreto anterior demostrado inválido | **NO_VERIFICADO** |
| 4 | el camino `service_role` cerrado, o se explica qué falta | **ABIERTO**, con lo que falta detallado en §2 |
| 5 | no se expone ningún secreto | **PASS** — ni valores, ni fragmentos, ni firmas, ni hashes reversibles |
| 6 | Autonomía 2 apagada | **PASS** |
| 7 | kill switch detenido | **PASS** |
| 8 | `DBUSER` = `postgres` | **PASS** |
| 9 | no se modifica producción | **PASS** — solo lectura, con `transaction_read_only=on` verificado |

## **VEREDICTO: NO PASS**

Fallan los criterios 1, 3 y 4, y los tres tienen la misma causa única: **el stack
de Supabase no se recreó**.

---

# QUÉ HACER

En Dokploy, proyecto **`automatizacion-rp-supabase-dgimpk`** — el de Supabase,
**no** `crm-agentico-*`:

1. Confirmar que las tres variables tienen los valores nuevos.
2. Usar **Redeploy / Recreate**, no *Save*. `DESPLIEGUE.md` lo advierte dos
   veces: *«Dokploy escribe… al recrear los contenedores, no al guardar el
   formulario»*. Es el paso que más veces se olvida, y es exactamente el que
   falta.
3. Si al guardar apareció **`UNAUTHORIZED` en rojo**, la sesión de Dokploy había
   caducado y el cambio **no se guardó**: recargar, volver a entrar y repetir.

**Y antes de redesplegar, guardar en un archivo fuera del repositorio:**

- el `SERVICE_ROLE_KEY` **anterior** (si todavía está en algún lado), y
- el `JWT_SECRET` **nuevo**.

Con esos dos puedo demostrar la invalidación sin presentar ningún token a ningún
servicio y sin publicar nada: informo solo `SÍ`/`NO`. Sin ellos, lo único que
podré decir es que los contenedores se recrearon — necesario, pero no
suficiente.

## La señal que no depende de ninguna interfaz

Cuando el redeploy sea real, esto cambia solo:

```
PostgREST, supabase_mt_realtime, supabase_storage_admin
    51 h  ->  minutos
```

Avisame y vuelvo a medir. **No continúo con el cierre de B-7.**

---

**No se hizo commit. No se tocó producción. No se eliminó el GUC. No se revocó
`CREATE`. No se cambió `DBUSER`. No se activó Autonomía 2. No se levantó el kill
switch. No se ejecutó `crear_tag_crm`. No se usó `git stash`. No se imprimió
ningún secreto.**
