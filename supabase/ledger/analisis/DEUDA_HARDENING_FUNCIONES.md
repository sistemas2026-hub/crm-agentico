# Deuda de hardening: funciones de recuperación y `EXECUTE`

> **Deuda registrada, no corregida.** Es independiente de la adopción histórica
> y **no se mezcla con ella**. La adopción responde "¿qué estado heredamos?";
> esto, "¿qué queremos mejorar desde ahora?". Se resuelve con una migración
> nueva, posterior al conjunto del manifiesto.
>
> Medido en una base efímera construida desde cero por el ledger
> (PostgreSQL 16.14). **La base objetivo no está medida**: sus roles y grants
> salen de la sección 4 de `inspeccion_solo_lectura.sql`.

## Qué hay hoy (referencia)

| función | argumentos | SECURITY | `EXECUTE` para | filtro por rol del documento |
|---|---|---|---|---|
| `match_chunks` | `p_org, p_query_embedding, p_match_count, p_umbral, p_filtros` (5) | INVOKER | PUBLIC, `app_backend`, owner | **no** |
| `match_chunks` | los mismos + `p_rol` (6) | INVOKER | PUBLIC, `app_backend`, owner | sí |
| `match_chunks_hibrido` | `p_org, p_query_embedding, p_query_texto, p_match_count, p_filtros, p_k` | INVOKER | PUBLIC, `app_backend`, owner | **no** |
| `org_actual`, `gasto_del_mes` | — | INVOKER | PUBLIC, `app_backend`, owner | no aplica |

- **PUBLIC** tiene `EXECUTE` porque es el default de PostgreSQL para toda función
  nueva: nadie lo revocó.
- **`app_backend`** lo tiene por `grant execute on all functions in schema
  asistente to app_backend` (`schema.sql`).
- **Las funciones del scheduler (P2)** no están en esta situación: tienen
  `EXECUTE` solo para sus roles específicos. P2 revocó lo que el comodín le daba
  a `app_backend`.

## Qué alcanza realmente cada rol (medido)

| quién llama a `match_chunks_hibrido` | resultado |
|---|---|
| un rol que solo tiene lo de PUBLIC | `permission denied for schema asistente`: sin `USAGE` en el schema, el `EXECUTE` de PUBLIC no alcanza |
| ese rol, con `USAGE` en `asistente` pero sin grants de tabla | `permission denied for table document_chunks`: al ser INVOKER, rigen los permisos de quien llama |
| `app_backend`, con una organización que no es la suya | 0 filas, sin error. **En la referencia no hay datos**, así que esto muestra que no hay error de permisos, no que el filtro por organización funcione con datos reales |

`USAGE` sobre `asistente` en la referencia:
- `app_backend`;
- el owner;
- `asistente_owner`;
- los tres roles de P2: `job_executor`, `monitor_ro`, `scheduler_coordinator`.

Esos tres no tienen `SELECT` sobre `document_chunks`.

## Por qué sigue siendo deuda aunque hoy no se alcance

1. **PUBLIC queda a un grant de distancia.** Cualquier rol que reciba `USAGE` en
   `asistente` y `SELECT` sobre las tablas de documentos pasa a poder ejecutar
   las tres, sin que nadie se lo haya dado a propósito. Los roles de P2 ya
   tienen `USAGE`.
2. **La base objetivo puede tener otros roles.** Supabase trae `anon`,
   `authenticated` y `service_role`, y sus grants no están medidos.
3. **Falta el filtro por rol, y la RLS no lo suple.** La RLS
   (`tenant_aislado`) separa **organizaciones**, no roles de documento.
   `match_chunks_hibrido` y la sobrecarga de 5 argumentos dejan que quien ya
   puede llamarlas, dentro de su propia organización, recupere documentos
   restringidos a otro rol.
   - Hoy la de 5 argumentos es inalcanzable por ambigüedad: con 2 o 5
     argumentos da `AmbiguousFunction`.
   - Hoy `match_chunks_hibrido` no tiene llamadores.
   - El único llamador de código, `nucleo/recuperacion/busqueda.py:140`, usa la
     de 6 con `p_rol =>`.
4. **Un comodín se reaplica.** Si `schema.sql` se re-ejecutara (no se propone),
   `grant execute on all functions in schema asistente` alcanzaría a todas las
   funciones presentes en ese momento.

## Propuesta para la migración independiente (no escrita, no ejecutada)

1. `revoke execute … from public` en `match_chunks` (las dos), `match_chunks_hibrido`,
   `org_actual` y `gasto_del_mes`.
2. `drop function` de la sobrecarga de `match_chunks` de 5 argumentos. Antes,
   confirmar que ningún llamador la usa: hoy solo `busqueda.py:140` llama, con `p_rol`.
3. `match_chunks_hibrido`: **decidir** entre agregarle `p_rol` con el mismo
   filtro que la de 6 argumentos, o eliminarla porque no tiene llamadores.
4. Reemplazar el comodín por grants explícitos de `EXECUTE` a `app_backend`,
   solo en las funciones que usa.
5. Revisar `pg_default_acl` de `asistente` en la base objetivo; la sección 4 de
   la inspección lo lista.

**Pruebas que tendría que traer:**
- `busqueda.py` sigue resolviendo;
- un rol de documento no recupera fragmentos de otro rol, **con datos**;
- un rol sin grants no ejecuta ninguna de las tres;
- las funciones de P2 no ganan ni pierden grants.

**Orden respecto de la adopción:** es un archivo posterior al último del
manifiesto. La adopción lo tolera como posterior, y `--aplicar` lo ejecuta
recién cuando la adopción de las anteriores está completa.

## Decisiones que requiere

- Si se abre esta migración, y cuándo.
- `match_chunks_hibrido`: agregar el filtro por rol o eliminarla.
- Qué roles de la base objetivo deben poder ejecutar las funciones de
  recuperación, a la vista de la inspección.
