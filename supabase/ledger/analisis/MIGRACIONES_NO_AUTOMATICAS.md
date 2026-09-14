# Migraciones que el manifiesto no puede adoptar solo

> **Ninguna está decidida. Ninguna consulta se ejecutó contra producción.**
> Este documento reúne, por archivo, lo que hace falta para una decisión humana
> individual. El análisis de `202609070900_bandeja_sin_inflar.sql` está aparte, en
> `202609070900_bandeja_sin_inflar.md`.

Criterio común a todos:

- Las partes de **catálogo** (columnas, comentarios, índices, RLS, grants,
  políticas) las verifica el manifiesto automáticamente, y la aceptación humana
  (`--aceptar`) **exige** que coincidan.
- Lo que queda para decidir es el efecto sobre **datos** o el **SQL dinámico**.
  Una consulta agregada puede ser **compatible** con que ese efecto ocurrió; casi
  nunca lo **prueba**.
- Todas las consultas de abajo son de solo lectura, agregadas y sin PII.
- "Repetir" significa volver a ejecutar el archivo entero. En el ledger eso solo
  podría pasar forzando `--aplicar` sobre un hueco, que hoy se niega.

---

## 1. `202608211448_diagnostico_recuperacion.sql`

**Efectos.**
- *Catálogo:* columna `unanswered_queries.chunks_elegibles integer` y su comentario.
- *Datos:*
  ```sql
  update asistente.document_chunks set modelo_embeddings = 'text-embedding-3-large'
   where modelo_embeddings is null or modelo_embeddings = 'bge-m3';
  ```

**Invariante del código actual.** El único escritor de `modelo_embeddings` es la
carga de documentos (`nucleo/canales/api.py:5007`), que sella
`config.rag.modelo_embeddings`. En `tenants/rapilink.config.yaml` ese valor es
`text-embedding-3-large`. Lo que produce la base de producción no está verificado:
la config vigente vive en `asistente.tenant_config`.

**Consulta.**
```sql
select coalesce(modelo_embeddings, '<null>') as modelo, count(*) as fragmentos
  from asistente.document_chunks group by 1 order by 2 desc;
```

**Qué prueba / qué no.** Cero filas con `null` o `bge-m3` es compatible con que el
`UPDATE` corrió, pero también con que nunca las hubo. Si hay filas `bge-m3`, puede
ser que no corrió **o** que algún tenant hoy vectoriza con `bge-m3` legítimamente.

**Riesgo de aceptar sin re-ejecutar:** fragmentos viejos quedan con un modelo
nulo o incorrecto; afecta el diagnóstico de recuperación, no la seguridad.
**Riesgo de repetir:** re-etiqueta como `text-embedding-3-large` fragmentos que
un tenant vectorizó con `bge-m3` a propósito. Si la recuperación compara o
filtra por ese campo (no verificado aquí), mezclaría espacios de embeddings
distintos sin avisar. No se registra qué filas cambió.

---

## 2. `202609061400_bloqueos_en_traza.sql`

**Efectos.**
- *Catálogo:* columna `tool_calls.es_bloqueo boolean not null default false`, su
  comentario y el índice parcial `tool_calls_bloqueo_idx`.
- *Datos:* marca `es_bloqueo = true` donde `codigo_error` está en
  `IDENTIDAD_NO_VERIFICADA`, `PRECONDICION_NO_CUMPLIDA`,
  `FALTA_HABLAR_CON_EL_CLIENTE`, `IDENTIDAD_NO_RESUELTA`,
  `HERRAMIENTA_DESCONOCIDA` o `LIMITE_DE_CONVERSACION`.

**Invariante del código actual.** `nucleo/modelo/motor.py:85`
(`CODIGOS_DE_BLOQUEO`) contiene **exactamente** esos seis códigos, y
`db.py:1947-1953` escribe `es_bloqueo` con esa regla. Toda fila escrita por el
código actual cumple la invariante.

**Consulta.**
```sql
select count(*) filter (where not es_bloqueo and codigo_error in
         ('IDENTIDAD_NO_VERIFICADA','PRECONDICION_NO_CUMPLIDA','FALTA_HABLAR_CON_EL_CLIENTE',
          'IDENTIDAD_NO_RESUELTA','HERRAMIENTA_DESCONOCIDA','LIMITE_DE_CONVERSACION'))
         as bloqueos_sin_marcar,
       count(*) filter (where es_bloqueo) as marcadas
  from asistente.tool_calls;
```

**Qué prueba / qué no.** `bloqueos_sin_marcar = 0` es compatible con que corrió y
con que no hubo filas previas en esa situación. Si es mayor que 0, casi seguro
no corrió: el código actual no produce esas filas.

**Riesgo de aceptar:** si hay bloqueos viejos sin marcar, los reportes de "fallos"
los cuentan como errores. **Riesgo de repetir:** bajo en lo semántico (aplica la
misma regla que el código), pero es un `UPDATE` con barrido completo de
`tool_calls`, que puede ser grande: carga y bloqueos de fila durante la ejecución.

---

## 3. `202609061700_cola_priorizada.sql`

**Efectos.**
- *Catálogo:* columnas `conversations.escalada_en`, `escalada_no_comprobado` y
  `escalada_siguiente_paso`, sus comentarios, y el índice `conversations_espera_idx`.
- *Datos:*
  ```sql
  update asistente.conversations set escalada_en = actualizado_en
   where escalada_a_humano and escalada_en is null;
  ```

**Invariante del código actual.** El único escritor de `escalada_a_humano = true`
es `db.marcar_escalada` (`db.py:706`), y en la misma sentencia sella
`escalada_en = coalesce(escalada_en, now())`. Toda escalada posterior a este
archivo tiene `escalada_en`.

**Consulta.**
```sql
select count(*) filter (where escalada_a_humano and escalada_en is null) as escaladas_sin_fecha,
       count(*) filter (where escalada_a_humano) as escaladas
  from asistente.conversations;
```

**Qué prueba / qué no.** Cero es compatible con que corrió, o con que no había
escaladas antes. Mayor que 0 indica que no corrió, o que alguien escaló por fuera
de `marcar_escalada`.

**Riesgo de aceptar:** escaladas viejas sin fecha quedan al final (o fuera) de la
cola ordenada por espera. **Riesgo de repetir:** bajo; solo rellena filas que
violan la invariante. Pero rellena con una **aproximación** (`actualizado_en`) que
el comentario de la columna atribuye solo a las anteriores al 06/09/2026: una fila
rellenada hoy quedaría con una fecha falsa sin marca que la distinga.

---

## 4. `202609071900_tomar_caso.sql`

**Efectos.**
- *Catálogo:* columnas `conversations.tomada_por` y `tomada_en`, sus comentarios, y
  el índice `conversations_tomada_idx`.
- *Datos:*
  ```sql
  update asistente.conversations
     set tomada_por = atendida_por, tomada_en = actualizado_en, atendida_manual = false
   where atendida_manual and atendida_por is not null and estado <> 'cerrada'
     and actualizado_en::date = date '2026-09-07';
  ```

**Invariante del código actual.** No hay una: el `UPDATE` es una corrección
puntual acotada a un día. Los escritores relevantes:
- `db.py:1128` (respuesta desde el ticket) pone `atendida_manual = true` **y** mueve
  `actualizado_en`;
- `db.py:1759` (`marcar_atendida`) pone `atendida_manual = true` **sin** mover
  `actualizado_en`;
- `db.py:1733` (tomar) pone `tomada_por`/`tomada_en = now()`;
- `db.py:1790` (resolver) cierra.

**Dos defectos que hacen peligroso repetirlo:**
1. **Depende de la zona horaria de la sesión.** `actualizado_en::date` sobre un
   `timestamptz` usa el `TimeZone` de quien lo ejecuta. Corrido en UTC o en
   `America/Bogota` selecciona filas distintas.
2. **Alcanza estados posteriores.** Una conversación con `actualizado_en` del
   07/09 marcada atendida **después** por `marcar_atendida` —que no mueve
   `actualizado_en`— vuelve a cumplir la condición. Repetirlo le quitaría
   `atendida_manual` y **pisaría** un `tomada_por`/`tomada_en` real.

**Consultas.**
```sql
-- Exposicion: cuantas filas cambiaria una re-ejecucion, en cada zona horaria.
select count(*) filter (where (actualizado_en at time zone 'UTC')::date = date '2026-09-07') as si_utc,
       count(*) filter (where (actualizado_en at time zone 'America/Bogota')::date = date '2026-09-07') as si_bogota
  from asistente.conversations
 where atendida_manual and atendida_por is not null and estado <> 'cerrada';

-- Rastro debil de la ejecucion original.
select count(*) as tomadas_ese_dia
  from asistente.conversations
 where tomada_por is not null
   and (tomada_en at time zone 'America/Bogota')::date = date '2026-09-07';
```

**Qué prueba / qué no.** La primera mide el daño de repetir, no si corrió. La
segunda es compatible con la ejecución original, pero también con personas que
usaron "tomar" desde la pantalla ese mismo día: no las distingue.

**Riesgo de aceptar:** si no corrió, algunos casos del 07/09 siguen "atendidos"
cuando solo estaban tomados; es acotado y envejece. **Riesgo de repetir: alto.**
Revierte decisiones humanas posteriores sin registro ni reversión, y el resultado
depende de la zona horaria de la sesión.

---

## 5. `202609080802_historial_de_config.sql`

**Efectos.**
- *Catálogo:* tabla `tenant_config_historial`, su comentario, RLS habilitada y
  forzada, `grant select, insert` a `app_backend`, y la política `tenant_aislado`.
- *Datos:*
  ```sql
  insert into asistente.tenant_config_historial (organization_id, config_version, config, creado_en)
  select organization_id, config_version, config, coalesce(actualizado_en, creado_en, now())
    from asistente.tenant_config where config is not null
      on conflict (organization_id, config_version) do nothing;
  ```

**Invariante del código actual.** `nucleo/config/editor.py:340` inserta una fila de
historial en cada guardado de config; `cli/activar_importacion.py` declara lo mismo.
La versión vigente de cada tenant debería tener su fila.

**Consulta.**
```sql
select count(*) filter (where h.organization_id is null) as vigentes_sin_historial,
       count(*) as tenants
  from asistente.tenant_config tc
  left join asistente.tenant_config_historial h
    on h.organization_id = tc.organization_id and h.config_version = tc.config_version;
```

**Qué prueba / qué no.** Cero es compatible con que corrió **o** con que todo
tenant guardó su config por el editor después del 08/09. Mayor que 0 indica que no
corrió, o que alguien cambió `tenant_config` por fuera del editor.

**Riesgo de aceptar:** una versión vigente sin fila de historial. Con P2
integrado, `job_claim` no puede congelar esa versión y **no arranca el turno**
(falla ruidosa, no silenciosa). **Riesgo de repetir:** bajo; `on conflict do nothing`
no pisa filas. El único caso delicado es una versión cuyo contenido se cambió sin
subir `config_version`: la re-ejecución la registraría como si ese contenido fuera
el original de esa versión.

---

## 6. `202608042055_schema.sql`

**Por qué no es automática.** Tiene tres bloques `DO`. Sus efectos son **de
catálogo**, así que se pueden verificar con consultas escritas a mano; el
clasificador no puede leer SQL dinámico.

**Efectos de los `DO`.**
1. Crea el rol `app_backend` (NOLOGIN) si no existe y hace
   `grant app_backend to current_user`, es decir, a **quien lo ejecuta**.
2. Sobre 12 tablas (`tenant_config`, `tenant_users`, `documents`,
   `document_chunks`, `conversations`, `messages`, `tool_calls`,
   `unanswered_queries`, `evaluation_sets`, `evaluation_runs`, `usage_daily`,
   `audit_log`): habilita **y fuerza** RLS, otorga
   `select, insert, update, delete` a `app_backend` y hace
   `drop policy if exists tenant_aislado`.
3. Crea `tenant_aislado` (`for all to app_backend`, `using`/`with check`
   `organization_id = asistente.org_actual()`) en esas tablas salvo
   `tenant_config`, que tiene su propia sentencia estática.

**El resto** (extensiones `vector` y `pg_trgm`, schema, tablas, índices, funciones
`org_actual`, `gasto_del_mes`, `match_chunks`, `match_chunks_hibrido`, y el comodín
`grant execute on all functions in schema asistente to app_backend`) son sentencias
estáticas que el manifiesto verifica, contra el estado final.

**Consultas de catálogo (sin datos).**
```sql
-- DO 1
select rolname, rolcanlogin from pg_roles where rolname = 'app_backend';
select m.rolname as miembro
  from pg_auth_members a join pg_roles m on m.oid = a.member join pg_roles g on g.oid = a.roleid
 where g.rolname = 'app_backend';

-- DO 2 y DO 3, por tabla
select c.relname, c.relrowsecurity, c.relforcerowsecurity,
       has_table_privilege('app_backend', c.oid, 'select') as sel,
       has_table_privilege('app_backend', c.oid, 'insert') as ins,
       has_table_privilege('app_backend', c.oid, 'update') as upd,
       has_table_privilege('app_backend', c.oid, 'delete') as del,
       (select count(*) from pg_policies p where p.schemaname = 'asistente'
          and p.tablename = c.relname and p.policyname = 'tenant_aislado') as tenant_aislado
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'asistente'
   and c.relname = any (array['tenant_config','tenant_users','documents','document_chunks',
       'conversations','messages','tool_calls','unanswered_queries','evaluation_sets',
       'evaluation_runs','usage_daily','audit_log'])
 order by 1;

-- La funcion que la re-ejecucion reintroduciria
select pg_get_function_identity_arguments(p.oid)
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'asistente' and p.proname = 'match_chunks';
```

**Qué prueban / qué no.** Si las 12 filas muestran RLS habilitada y forzada, los
cuatro privilegios y `tenant_aislado = 1`, **los efectos de los tres `DO` están
presentes**. No prueban que los haya dejado este archivo y no otra ejecución
manual. Y la membresía de `app_backend` depende de quién lo corrió, que el
catálogo no dice.

**Riesgo de aceptar:** bajo si las consultas coinciden, porque los efectos son
todos observables en el catálogo.

**Riesgo de repetir: alto**, por cuatro vías:
1. **`match_chunks` sin filtro de rol.** `202608111433_documentos_roles.sql` la
   redefine con `p_rol` y `and p_rol = any(d.roles_permitidos)`. Re-ejecutar
   `schema.sql` vuelve a crear la definición del 04/08. Con la firma de 5
   argumentos queda como **otra sobrecarga sin el filtro**, y según cómo se resuelva
   una llamada, un rol podría recuperar documentos que no le corresponden. Qué
   sobrecarga resolvería cada llamada no está verificado aquí; que exista la
   redefinición, sí.
2. **El comodín de `EXECUTE`** vuelve a dar a `app_backend` las funciones de
   todo el schema, incluidas las del scheduler de P2 si ya están instaladas.
3. **`grant app_backend to current_user`** agrega una membresía a quien lo ejecute.
4. Borra y recrea `tenant_aislado` en 11 tablas. Hoy la definición es la misma
   (no se encontraron cambios posteriores sobre esas políticas); si alguna vez
   cambia, re-ejecutar la revertiría.
