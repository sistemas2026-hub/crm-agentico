# Inventario de rutas capaces de ejecutar `supabase/*.sql`

> Rama `ledger/cierre-auditoria`. Verificado estáticamente por
> `tests/test_rutas_sql.py`, que falla si aparece un módulo nuevo que lea
> migraciones o si alguno que no sea `cli/migrar_asistente.py` pasa ese texto a
> `execute()`.

## Resumen

**Una sola ruta ejecuta migraciones:** `cli/migrar_asistente.py --aplicar`, con
ledger, checksum, lock y huecos. Todo lo demás lee, delega o se niega.

## Rutas en el código

| ruta | ¿escribe en la base? | cómo selecciona archivos | ledger | checksum | lock | huecos |
|---|---|---|---|---|---|---|
| `cli/migrar_asistente.py --aplicar` | **sí**: ejecuta cada archivo pendiente y anota su fila | `supabase/*.sql`, orden por nombre; `ledger/` queda afuera | sí | sí (`sha256-utf8-lf-v1`, antes de tocar nada) | sí, una sola sección para todo | sí (exit 5); además base existente sin ledger → exit 6 |
| `cli/migrar_asistente.py --adoptar --escribir-baseline` | **sí**: solo filas del ledger, **no** ejecuta SQL de migraciones | archivos del manifiesto, pendientes | sí | sí | sí: huella → esquema → plan → verificación → INSERT dentro del lock | no aplica (no ejecuta); sus faltantes quedan como hueco para `--aplicar` |
| `cli/migrar_asistente.py --adoptar --aceptar A --motivo M --escribir-baseline` | **sí**: una fila `baseline_humano` | un archivo | sí | sí | sí, re-verifica dentro | no aplica |
| `cli/migrar_asistente.py --estado` | no | igual que `--aplicar` | lee (no lo crea) | sí | no | informa |
| `cli/migrar_asistente.py --adoptar` (sin escribir) | no | archivos del manifiesto | lee (no lo crea) | sí | no | — |
| `cli/base_desde_cero.py` | **sí**, en una base **local**: crea/borra la base, pgcrypto y Django; el paso 3 **delega** en `migrar_asistente.aplicar` | lo que decida el migrador | sí (delegado) | sí (delegado) | sí (delegado) | sí (delegado) |
| `cli/migraciones.py` | **no**. Hasta `ef548b5`, `--aplicar` ejecutaba archivos enteros con `cur.execute(sql)` y `commit` **sin** ledger, checksum, lock ni huecos, eligiendo los que tenían "objetos faltantes". Ahora `--aplicar` termina con exit 2 **antes de conectarse** | informativo: todos los `.sql` | no | lee con el contrato canónico | no | no |
| `cli/manifiesto_adopcion.py --generar` | no en la base (solo lectura de la referencia); escribe el JSON | carpeta de la referencia | lee | sí | no | — |

## Rutas de prueba (no productivas)

| ruta | qué hace |
|---|---|
| `tests/test_ledger_migraciones.py`, `tests/test_ledger_carreras.py`, `tests/test_rutas_sql.py` | ejecutan migraciones **a través del migrador**, sobre copias del repo y bases efímeras |
| `tests/test_bloqueos_en_traza.py`, `test_guias_tv.py`, `test_habilidades.py`, `test_tomar_no_es_resolver.py`, `test_p2_compuertas.py`, `test_ledger_checksum.py` | leen el **texto** de archivos concretos para afirmar sobre su contenido; no ejecutan |
| `/c/tmp/rearmar_p2.py` (fuera del repo, no versionado) | reaplica los dos SQL de P2 directo sobre la base efímera `test_p2` para las suites de P2. Solo local; no es una ruta del producto |

## Superficies fuera del análisis AST — lista cerrada

`tests/test_rutas_sql.py` recorre por AST `cli/`, `nucleo/` y
`django-crm/backend/`. Lo que queda afuera, verificado por listado de archivos
versionados (`git ls-files`) y sus extensiones:

| superficie | qué contiene | por qué no puede ejecutar `supabase/*.sql` |
|---|---|---|
| `.githooks/` | `post-merge`, `post-checkout` (sh) | no ejecutan SQL. **Pero `post-merge` le indicaba al usuario aplicar migraciones con `docker exec … psql … < supabase/…sql`**, salteando el ledger. Corregido en esta rama para remitir a `cli/migrar_asistente.py`; la prueba ahora revisa los hooks y falla si vuelven a mandar a psql |
| `soporte_wisphub.py` (raíz) | script Python | importa `requests` y `ollama`; no importa ningún driver de base ni lee `supabase/` |
| `django-crm/frontend/` | 337 `.js`, 297 `.svelte`, 2 `.ts` | ninguna dependencia de base (`pg`, `postgres`, `@supabase`, ORM) en `package.json` ni import de drivers en `src/`; habla con el backend por HTTP. Sus menciones a "supabase" son texto de interfaz |
| `django-crm/docker/` | `init-rls-user.sql`, `entrypoint.sh` | revisados por la regla de infraestructura; ninguno toca `supabase/` |
| `django-crm/docs/` | 52 `.md`, 1 `.html` | documentación |
| `apps/` | app Flutter (dart, swift, kotlin, recursos) | cliente móvil; no contiene el repo de migraciones ni driver de base |
| `.claude/` | 3 `.md`, 1 `.yaml` | configuración de skills; nada ejecutable |
| `evaluacion/`, `tenants/`, `conectores/` | `.yaml`, `.json` | datos de configuración y casos |
| `corpus/`, `directivas/`, `documentos/`, `PROMPTS/`, `SPEC/` | `.md`, `.csv`, `.docx` | documentos |
| `.github/` (raíz) | solo `CODEOWNERS` | sin workflows |
| `tests/` | suites | excluidas del AST a propósito; las que ejecutan migraciones lo hacen **por el migrador** sobre bases efímeras (ver arriba) |

No se amplió el análisis a otras carpetas: no hay nada ejecutable en ellas que
pueda leer `supabase/`.

## Rutas fuera del código

| ruta | estado |
|---|---|
| `.githooks/post-merge` | **instruía** aplicar migraciones con `psql` a mano. Ya no: remite a `migrar_asistente.py --estado` / `--aplicar` |
| `docker-compose.yml` → `docker-entrypoint-initdb.d` | monta `django-crm/docker/postgres/init-rls-user.sql`, **no** `supabase/*.sql`; corre solo al inicializar un volumen vacío del Postgres de desarrollo |
| `docker-compose.prod.yml`, `Dockerfile`, `django-crm/Dockerfile`, entrypoints | ninguna referencia a `supabase/*.sql` |
| `django-crm/.github/workflows/tests.yml` | `psql -c` sobre la base de CI de Django; no toca `supabase/` |
| migraciones de Django (`manage.py migrate`) | no ejecutan `supabase/*.sql` (sin `RunSQL` que lo lea) |
| **Aplicación manual** (editor SQL de Supabase, `psql` de una persona) | el docstring histórico de `cli/migraciones.py` decía que las migraciones "se aplican A MANO". **El código no puede impedirlo.** Controles disponibles: el ledger no registra ejecuciones manuales, así que `--estado` las mostraría como pendientes y `--aplicar` las volvería a correr; en una base sin ledger, `--aplicar` se niega (exit 6) y hay que adoptarla, lo que las verifica semánticamente. El riesgo residual es de **proceso**: una persona con credenciales de dueño puede ejecutar SQL fuera de cualquier herramienta |
