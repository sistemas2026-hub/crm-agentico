# Generar el manifiesto para el entorno objetivo real

> **No se ejecutó.** Es el procedimiento para cuando exista autorización y un
> entorno que coincida con el objetivo. La huella sigue **fail-closed**: este
> documento no la relaja ni ofrece forma de hacerlo.

## Por qué hace falta

El manifiesto versionado hoy fue generado contra una referencia efímera con
**PostgreSQL 16** (`server_version_num` 160014) y estas extensiones:

| extensión | versión | schema |
|---|---|---|
| `pg_trgm` | 1.6 | `public` |
| `pgcrypto` | 1.3 | `ext` |
| `vector` | 0.8.6 | `public` |

`adoptar` compara esa huella con la del servidor **antes** de verificar y antes
de crear el ledger. Si la base objetivo es PostgreSQL 15, o tiene otra versión
de alguna de esas extensiones, o las tiene en otro schema (Supabase suele usar
`extensions`), la adopción termina con **exit 7 sin escribir nada**. Es lo
correcto: `pg_get_*def` puede cambiar entre versiones mayores, y comparar
definiciones entre servidores distintos no es confiable.

**P2 y `pgcrypto` (actualizado el 15/09/2026):** la inspección de solo lectura
midió producción con `pgcrypto` 1.3 en el schema **`extensions`** y sin schema
`ext`. P2 se adaptó antes de aplicarse en ningún entorno real: ahora exige
`extensions.digest` y `extensions.gen_random_bytes` y le otorga a
`asistente_owner` `USAGE` y `EXECUTE` explícitos, comprobados. La huella de la
tabla de arriba (`pgcrypto` en `ext`) es la del manifiesto PG16 vigente y se
reemplaza al regenerarlo contra la referencia PG17.

## Procedimiento

1. **Tomar la huella del objetivo — solo lectura, con autorización.**
   ```sql
   show server_version_num;
   select e.extname, e.extversion, n.nspname
     from pg_extension e join pg_namespace n on n.oid = e.extnamespace
    where e.extname <> 'plpgsql' order by 1;
   ```
   Guardar el resultado tal cual. Nada más se consulta en este paso.

2. **Determinar qué migraciones tiene aplicadas el objetivo.** Es un conjunto de
   nombres de archivo, y es una decisión humana documentada: el objetivo no
   tiene ledger, así que no lo dice solo. El manifiesto tiene que generarse con
   **exactamente** ese conjunto. Si incluye archivos que el objetivo no tiene,
   o viceversa, los esperados no corresponden.

3. **Levantar una referencia con la MISMA huella.**
   - misma versión mayor de PostgreSQL (para Supabase, la imagen `supabase/postgres`
     de esa mayor);
   - cada extensión de la huella en **su versión exacta** y **su schema**:
     `create extension <nombre> with schema <schema> version '<version>';`
   - si alguna versión no está disponible en esa imagen, **se detiene aquí**. No
     se sustituye por otra.

4. **Migraciones de Django** del mismo commit que el objetivo, sobre esa base
   vacía.

5. **Ledger** con una carpeta que contenga solo los archivos del paso 2:
   `py -3.13 cli/migrar_asistente.py --aplicar` → exit 0 y N aplicadas.

6. **Generar:**
   `py -3.13 cli/manifiesto_adopcion.py --generar --salida <ruta> --descripcion "<entorno, fecha, quién>"`.
   El generador se niega si la referencia tiene pendientes, hashes distintos,
   filas adoptadas o anotadas de más.

7. **Comparar la huella generada con la del paso 1**, campo por campo. Deben ser
   idénticas en versión mayor y en versión y schema de cada extensión de la
   referencia. Si difieren, el manifiesto no sirve para ese objetivo y se descarta.

8. **Recién entonces**, con autorización y sobre el objetivo:
   `py -3.13 cli/migrar_asistente.py --adoptar` en **solo lectura**. Revisar
   automáticas, no equivalentes y pendientes de decisión. La escritura
   (`--escribir-baseline`, `--aceptar` con `--autorizado-por`) es un paso aparte,
   autorizado aparte. Cada fila escrita guarda como evidencia el manifiesto y la
   huella medida en ese momento (`EVIDENCIA_DE_ADOPCION.md`).

## Lo que no se hace

- Relajar `comparar_huella` para aceptar otra versión mayor o extensiones
  distintas.
- Generar el manifiesto contra la base que se quiere adoptar: sería verificarla
  contra sí misma.
- Editar a mano la huella o los esperados de un manifiesto.
