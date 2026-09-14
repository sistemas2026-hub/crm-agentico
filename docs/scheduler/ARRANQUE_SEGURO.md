# Arranque seguro de los procesos del scheduler

> **Estado: DISEÑO para P5. Obligatorio antes de cualquier activación.
> No implementado. NO VERIFICADO.**

## Por qué no alcanza con la documentación

Medido en `tests/test_roles_de_conexion.py`:

- Conectado como `motor` (`rolsuper = true`, `rolbypassrls = true`), después de
  `set role scheduler_coordinator` basta `reset role` para leer
  `asistente.job_run`. Las ACL no protegen a un proceso que puede salir de su rol.
- `puerta.sesion` hoy **no** comprueba con qué usuario se conectó: usa
  `conexion.dsn()`, el mismo DSN que el motor.

Un despliegue que olvide cambiar una variable de entorno arrancaría el scheduler
como `motor` y todo seguiría "funcionando", sin separación. Por eso la
comprobación va **dentro de cada proceso**, y un incumplimiento impide arrancar.

## La comprobación

Cada proceso declara en código el login y el rol que le corresponden:

| proceso | login esperado | rol esperado |
|---|---|---|
| coordinador | `scheduler_login` | `scheduler_coordinator` |
| ejecutor | `executor_login` | `job_executor` |
| monitor | `monitor_login` | `monitor_ro` |

Al arrancar, **antes de reclamar, ejecutar o leer nada**, con la primera conexión:

```sql
select session_user, current_user, r.rolsuper, r.rolbypassrls, r.rolinherit,
       coalesce(json_agg(json_build_object(
         'rol', g.rolname, 'set', a.set_option,
         'inherit', a.inherit_option, 'admin', a.admin_option))
         filter (where g.rolname is not null), '[]') as membresias
  from pg_roles r
  left join pg_auth_members a on a.member = r.oid
  left join pg_roles g on g.oid = a.roleid
 where r.rolname = session_user
 group by 1, 2, 3, 4, 5;
```

Condiciones, **todas** obligatorias:

1. `session_user` = login esperado.
2. `rolsuper = false`.
3. `rolbypassrls = false`.
4. `rolinherit = false`.
5. Membresías: **exactamente una**, al rol esperado, con `set = true`,
   `inherit = false`, `admin = false`.
6. El rol de acceso tampoco es miembro de nada ni evade RLS
   (`pg_auth_members` con `member` = ese rol: cero filas).
7. Tras `set role <rol esperado>`: `current_user` = rol esperado y `session_user`
   sigue siendo el login.
8. `pg_has_role(session_user, 'asistente_owner', 'MEMBER') = false` y lo mismo
   para `app_backend`.

Además, **en cada sesión** que abra `puerta.sesion` (una consulta barata): se
reconfirman 1 y 7. Un pool que recicle una conexión ajena no pasa.

## Ante cualquier incumplimiento

- El proceso **no arranca**: excepción `IdentidadInsegura`, salida distinta de 0,
  antes del primer claim.
- El error nombra la condición que falló y el valor observado (sin contraseñas).
- **Sin fallback.** El paquete `nucleo/programador` deja de usar
  `conexion.dsn()`: cada proceso lee **su** DSN de variables propias
  (`SCHEDULER_COORDINADOR_DSN_*`, `SCHEDULER_EJECUTOR_DSN_*`,
  `SCHEDULER_MONITOR_DSN_*`). Si faltan, no hay valor por defecto y no se prueba
  con `DBUSER`.
- No se ejecuta ningún turno, ni en seco.

## Fin del tick en un solo proceso

`coordinador.un_tick` reclama y ejecuta en el mismo proceso con el mismo DSN.
Medido (`test_roles_de_conexion.py`, sección 5): con un login de una sola
membresía, el claim funciona, la ejecución muere con
`permission denied to set role "job_executor"`, y el turno se atrasa un lease
entero. **Es incompatible con las condiciones de arriba.**

Para producción:

1. **Dos entrypoints**, dos procesos, dos logins:
   - `python -m nucleo.programador.proceso_coordinador`
   - `python -m nucleo.programador.proceso_ejecutor`
2. **Entrega por stdin.** El coordinador lanza al ejecutor y le escribe **una**
   línea JSON `{"run_id": ..., "capability": ...}` por stdin, que el ejecutor lee
   y cierra. Nunca por argv (visible en `ps`), variable de entorno (visible en
   `/proc/<pid>/environ`), archivo, cola persistente ni log.
3. **`un_tick` sale de `nucleo/`.** Se muda a `tests/soporte/tick_hermetico.py`
   como helper de pruebas. Queda técnicamente inaccesible desde producción porque:
   - ningún módulo de `nucleo/` lo importa (lo verifica una prueba estática sobre
     el AST);
   - `.dockerignore` excluye `tests/`, así que la imagen productiva no contiene
     el archivo (se verifica listando la imagen construida);
   - ningún `CMD`, `command:` de compose ni `__main__` productivo lo referencia
     (prueba estática sobre `Dockerfile`, `docker-compose*.yml` y los módulos
     con `if __name__ == "__main__"`).

## Pruebas exigidas en P5

| escenario | resultado |
|---|---|
| arrancar como `motor` | no arranca; nombra `rolsuper`/`rolbypassrls` |
| login con dos membresías funcionales | no arranca |
| login correcto de otro proceso (ejecutor con `scheduler_login`) | no arranca |
| membresía con `inherit = true` | no arranca |
| variables de DSN ausentes | no arranca; no intenta `DBUSER` |
| login correcto | arranca; `session_user`/`current_user` esperados en cada sesión |
| capability en argv, entorno o logs del ejecutor | no aparece (búsqueda del valor y de cualquier cadena de 64 hex) |
| importar `un_tick` desde un entrypoint productivo | imposible: no existe en la imagen |
