# Paso 10.3 — Corrección definitiva y prueba del procedimiento B.6 / B.7

**Fecha:** 17/09/2026
**Producción:** sólo lectura. No se modificó nada, no se tocó el ledger, no se
aplicaron las 2 migraciones de Fase 1, no se concedió ningún permiso.
**Resultado:** procedimiento corregido, convertido en tres scripts ejecutables
y **probado dos veces desde cero**: 25/25 estructurales contra producción y el
flujo funcional del scheduler hasta `succeeded`, ambas veces.

---

## 1. Cambios realizados en B.6

`B6_PLAN_CAMBIO_CONTROLADO.md`:

- **Nota de cabecera**: añadida la entrada de 10.2/10.3 explicando que §B
  producía un scheduler roto.
- **§B, «El procedimiento de respaldo»**: reescrito entero. Ya no se escribe a
  mano — remite a los tres scripts. Incluye la tabla medida de qué transporta
  cada artefacto, las cuatro cosas que no transporta ninguno, y por qué
  `--schema=extensions` **no** es la solución.
- **§K Riesgos**: fila nueva — *«Verificación que sólo comprueba existencia»*,
  con la razón de fondo (PostgreSQL no registra dependencia del cuerpo de una
  función plpgsql) y la advertencia de que `job_salud`/`jobs_vencidos` no valen
  como prueba.

## 2. Cambios realizados en B.7

**B.7 no tenía documento.** Su procedimiento vivía dentro de B.6 §B, y eso es
parte de por qué quedó incompleto sin que se notara. Se creó
`B7_PROTOCOLO_RESPALDO.md` como fuente de verdad del respaldo, con los doce
puntos pedidos: esquemas, roles, ACL de esquemas, ACL de objetos, cómo se
transportan, cómo y dónde se instala `pgcrypto`, qué necesita
`asistente_owner`, el orden exacto, cómo no depender de privilegios
accidentales, qué no viaja, y qué verificar.

Y tres archivos ejecutables nuevos en `despliegue/respaldo/`:

| Archivo | Qué hace |
|---|---|
| `respaldar.py` | Genera los **tres** artefactos. `--imagen` para máquinas sin herramientas cliente |
| `restaurar.sh` | La restauración completa en un comando, sin pasos manuales fuera de él |
| `verificar_restauracion.py` | 25 comprobaciones estructurales contra producción **+** el flujo funcional del scheduler |

## 3. Inventario de elementos respaldados

Medido sobre los artefactos reales, no supuesto por el nombre del comando.

**`20260917_103359_datos.dump`** — 8.897.369 bytes:

```
328 TABLE   616 INDEX   265 CONSTRAINT   463 FK   231 ACL
155 POLICY  102 SEQUENCE  93 ROW  48 COMMENT  15 FUNCTION
 9 DEFAULT   4 TRIGGER    3 SCHEMA          0 EXTENSION
```

**`20260917_103359_roles.sql`** — 9.936 bytes:

```
25 CREATE ROLE   43 ALTER ROLE   33 GRANT de membresia
 0 "IN DATABASE ... SET"   0 GRANT sobre esquemas   0 CREATE EXTENSION
```

**`20260917_103359_entorno.sql`** — 4.525 bytes, generado del catálogo:
7 extensiones con su esquema (cada una con guarda de disponibilidad),
1 concesión de esquema, 3 ajustes de `pg_db_role_setting`.

## 4. Inventario de ACL transportadas

| ACL | Dónde viaja |
|---|---|
| Tablas, secuencias y funciones de los 3 esquemas (927 `GRANT` a `crm_user`, entre otros) | dentro del `.dump`, 231 entradas `ACL` |
| `nspacl` de `public` (`crm_user=UC`, `crm_owner=UC`) | dentro del `.dump`; el filtro del índice **no** lo quita |
| `EXECUTE` de las funciones del scheduler (`asistente_owner=X`, `scheduler_coordinator=X`) | dentro del `.dump` |
| **`grant usage on schema extensions to asistente_owner`** | **artefacto 3** — no viaja en ningún volcado |
| Concesiones a `anon`, `authenticated`, `service_role`, `dashboard_user` sobre `extensions` | **no se transportan a propósito**: son plantilla de Supabase |

## 5. Orden de restauración

1. **Roles** — o cada `OWNER TO` y cada `GRANT` del volcado falla.
2. **Entorno** — después de roles (concede a `asistente_owner`), antes del
   volcado (sus índices usan `pg_trgm` y `vector`).
3. **Datos** — con el índice filtrado sólo en la entrada que *crea* `public`.

## 6. Resultado del primer restore

Réplica **nueva y virgen** (`pg-103a`, puerto 15460): 0 tablas, 0 roles `crm*`.
Un solo comando, sin un arreglo manual:

```
sh /procedimiento/restaurar.sh /r 20260917_103359 postgres -U postgres
  1/3 roles...      (29 errores 'GRANTED BY supabase_admin' -- esperados)
  2/3 entorno...    (NOTICE: pg_net y supabase_vault no disponibles -- esperados)
  3/3 datos...
>>> codigo de salida: 0
```

Los 29 errores son membresías entre roles de plataforma de Supabase que un
PostgreSQL desnudo no puede otorgar. Las que importan sí se aplicaron — el
verificador lo comprueba (`membresia crm_migrator->crm_owner = 1`).

## 7. Resultado de la validación estructural

**25 de 25 idénticos** contra producción:

| | |
|---|---|
| tablas / secuencias / índices en `public` | 135 / 51 / 829 |
| índices inválidos | 0 |
| constraints | 727 |
| políticas / RLS / FORCE RLS | 132 / 66 / 66 |
| dueño de las tablas | `crm_owner` (único) |
| tablas y políticas en `asistente` | 35 / 35 |
| funciones `job*` y con `search_path=pg_catalog` | 10 / 10 |
| **md5 de los 10 cuerpos** | `614d3a167d73bac0ca16cf6fc002a19c` |
| `GRANT` a `crm_user` | 927 |
| ACL de `job_claim` | `asistente_owner=X, scheduler_coordinator=X` |
| roles del proyecto | 9 |
| membresía `crm_migrator → crm_owner` / su `SET role` | 1 / 1 |
| esquema de `pgcrypto` | **`extensions`** |
| `extensions.digest` / `gen_random_bytes` resuelven | true / true |
| `asistente_owner` con `USAGE` en `extensions` | **true** |
| `pg_trgm` y `vector` | `pg_trgm@public, vector@public` |

## 8. Resultado de la validación funcional

```
job_claim()      run_id=397d402a…  intento #1
                 capability de 64 hex      -> gen_random_bytes(32) resolvio
                 config_hash de 64 hex     -> digest sha256 resolvio
job_contexto()   turno completo; config_hash adf6952df87766c2 == el del claim
job_heartbeat()  lease renovado
job_finalize()   desenlace = succeeded
job_run          estado final = succeeded
job_attempt      outcome = succeeded, con completed_at
job_run_event    3 eventos registrados
controles        job_salud() 1 fila, jobs_vencidos() 0 filas

>>> 0 falla(s)
```

Sin errores de permisos y sin errores de resolución de funciones.

## 9. Resultado del segundo restore

Réplica eliminada y **procedimiento repetido entero** sobre otra virgen
(`pg-103b`, puerto 15461): 0 tablas al empezar, `restaurar.sh` código 0, los
mismos 29 errores esperados, y después:

```
25 de 25 identicos
job_claim OK · capability 64 hex · config_hash coincide
job_finalize -> succeeded · job_run succeeded · job_attempt succeeded
0 falla(s)
```

**Resultado idéntico.** No fue un accidente de la primera réplica.

## 10. Diferencias producción ↔ réplica

Ninguna en las 25 comprobaciones. Las únicas diferencias son las filas que crea
la propia prueba funcional en la réplica (`job_catalogo` 1, `job_run` 1,
`job_attempt` 1, `job_schedule_state` 1, `job_run_event` 3, frente a 0 en
producción), y los ~29 `GRANT` de membresía entre roles de plataforma de
Supabase que un PostgreSQL desnudo no puede otorgar.

## 11. Riesgos residuales

1. **El repositorio sigue diciendo `ext.`** en los dos archivos de Fase 1. Esto
   arregla la **restauración**, no la divergencia del paso 10.1: si se
   re-aplicaran esos archivos tal cual, su guarda de pre-vuelo abortaría. Son
   dos problemas con una causa común y decisiones separadas.
2. **Sólo se probó el camino feliz del scheduler.** Reclamar, latir, finalizar
   con éxito. No se ejercitaron el rescate de leases vencidos, el backoff ni
   `job_cerrar_turno`. Ninguno llama a `digest`, así que no cambian el veredicto
   sobre `pgcrypto`, pero no están cubiertos.
3. **Se validó contra PostgreSQL desnudo.** En una restauración sobre un
   proyecto Supabase nuevo, `extensions` ya existirá con sus concesiones de
   plantilla; lo que faltará igual es el `USAGE` para `asistente_owner`, porque
   es un rol nuestro. Los `if not exists` hacen el resto inocuo.
4. **Otras dependencias fuera de los 3 esquemas siguen sin auditar.** Se buscó
   `extensions.` exhaustivamente (8 referencias, todas del scheduler). No se
   auditó qué podría depender de `auth`, `storage`, `vault` o
   `supabase_functions`.
5. **`--imagen` fija la versión de las herramientas.** Si producción sube de
   mayor, hay que subir la imagen o `pg_dump` se niega. Está dicho en B.7.
6. **El artefacto 3 excluye los ajustes de ámbito «toda la base»** —ahí vive el
   secreto JWT—. Si alguna vez un ajuste de ese ámbito fuera necesario para
   restaurar, habría que transportarlo por otra vía, no por este artefacto.

## 12. Procedimiento final recomendado

```bash
# --- RESPALDO ---------------------------------------------------------------
py -3.13 despliegue/respaldo/respaldar.py --destino "$CARPETA" \
        [--imagen pgvector/pgvector:pg17]

# --- RESTAURACION -----------------------------------------------------------
sh despliegue/respaldo/restaurar.sh "$CARPETA" "$SELLO" "$BASE" -U "$USUARIO"

# --- VERIFICACION (obligatoria) ---------------------------------------------
py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto "$PUERTO"
```

**Un respaldo no está validado hasta que el verificador sale con 0 fallas.**
`pg_restore` en 0 no es evidencia: está medido que también da 0 con el
scheduler roto.

---

## Estado al cerrar

Producción intacta y verificada: ledger 45 filas, `job_catalogo` 0, `job_run` 0,
135 tablas en `public`, 132 políticas, 192 filas en `django_migrations`, 8
extensiones, ACL de `extensions` sin cambios. Réplicas `pg-103a` y `pg-103b`
eliminadas. Todas las consultas contra producción se abrieron con
`read_only = True`.
