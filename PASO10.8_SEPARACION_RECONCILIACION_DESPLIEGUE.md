# Paso 10.8 — Separación de reconciliación y despliegue

**Fecha:** 17/09/2026
**Alcance:** análisis + prueba en réplica. **Producción no se modificó** (ledger
45 filas, md5 `58ff01f220787396657af7832f6c48c8`), **el repositorio tampoco**:
la estrategia se probó sobre una copia en el scratchpad. No se crearon *event
triggers* en producción.

> **Respuesta corta a las dos preguntas del criterio de éxito:**
> se reconcilia sin desplegar **sacando los archivos 3 y 4 del nivel superior de
> `supabase/`** — es el único mecanismo que el CLI soporta. Y los archivos 3 y 4
> son **despliegue de dos funcionalidades de seguridad del motor** cuyo código
> **no está desplegado**, así que pueden esperar.

---

## 1. Inventario de los archivos 3 y 4

### `202609151710_interruptor_autonomia.sql`

```
checksum : e0d6b8dcb7d29f0b6323281859079e13c1cfde5bba30f41020caffeef91495e3
tamaño   : 7.954 bytes · 144 líneas
```

| | |
|---|---|
| Tablas | 1 — `asistente.interruptor_autonomia` (7 columnas) |
| Índices | 1 — `interruptor_autonomia_vigente_idx`, más el `pkey` implícito |
| Políticas | 1 — `tenant_aislado` (con `drop policy if exists` previo) |
| `ALTER TABLE` | 2 — `enable` y **`force`** row level security |
| Constraints | 3 — `pkey`, dos `check` sobre `estado`/`estado_anterior`, y la FK |
| **Claves foráneas** | **→ `public.organization(id)`** `on delete cascade` |
| `GRANT` | `select, insert` a `app_backend` — **sin UPDATE ni DELETE**: así es como la tabla queda de solo-agregar |
| `INSERT` | 1 — fila semilla por cada organización con `tenant_config`, en estado `activo` |
| Comentarios | 2 |
| Funciones / triggers | **0** |
| Referencias a `job_*` | **0** |
| Referencias a `tenant_config` | 3 (las lee el `INSERT` semilla) |

### `202609151715_operaciones_externas.sql`

```
checksum : 9c2f242d9319664aefa1d1a07ecbadf31b7af67c5c176cae056a4300118efb05
tamaño   : 6.558 bytes · 119 líneas
```

| | |
|---|---|
| Tablas | 1 — `asistente.operaciones_externas` (11 columnas, PK compuesta) |
| Índices | 1 — `operaciones_externas_ejecutando_idx`, más el `pkey` |
| Políticas | 1 — `tenant_aislado` |
| `ALTER TABLE` | 2 — `enable` y **`force`** RLS |
| Constraints | 3 — `pkey`, `check` sobre `estado`, y la FK |
| **Claves foráneas** | **→ `public.organization(id)`** `on delete cascade` |
| `GRANT` | `select, insert, update` a `app_backend` — **sin DELETE**: una operación que ya salió no se borra |
| `INSERT` | 0 |
| Comentarios | 3 |
| Funciones / triggers | **0** |
| Referencias a `job_*` / `tenant_config` | **0** / **0** |

## 2. Funcionalidad que habilitan

**`interruptor_autonomia`** — el *kill switch* de autonomía por empresa. Cuando
está en `detenido`, el motor no ejecuta ninguna acción autónoma de ese tenant.
La tabla es el historial y el estado a la vez: cada fila es una transición, y el
estado vigente es la más reciente. Lo lee `nucleo/seguridad/interruptor.py`.

**`operaciones_externas`** — la garantía de que una mutación contra un tercero
(reiniciar una ONT, activar CATV, registrar un pago) **se ejecuta una vez**. La
clave primaria `(organización, clave)` es el mecanismo de exclusión: quien
inserta, ejecuta. Lo usa `nucleo/seguridad/idempotencia.py`.

> **Ninguno de los dos módulos está desplegado.** `nucleo/seguridad/interruptor.py`
> y `nucleo/seguridad/idempotencia.py` siguen sin versionar (`??` en git). Hoy
> nada en producción lee esas tablas.

## 3. Dependencias

| | Archivo 3 | Archivo 4 |
|---|---|---|
| Con las 2 migraciones históricas del scheduler | **ninguna** (0 referencias a `job_*`) | **ninguna** |
| Con `public.organization` | FK `on delete cascade` | FK `on delete cascade` |
| Con `tenant_config` | la **lee** para sembrar (3 referencias) | ninguna |
| Con `tenant_config_historial` | ninguna | ninguna |
| Entre sí | ninguna |

**No hay razón técnica para ejecutarlos junto con la reconciliación.** La única
razón por la que irían juntos es que `--aplicar` no distingue.

## 4. Riesgos de desplegarlos

1. **Entran en el esquema del CRM.** Medido: la creación de la FK toma
   `ShareRowExclusiveLock` sobre `public.organization`, que **bloquea las
   escrituras** ahí (permite lecturas). La reconciliación sola nunca toca
   `public`.
2. **El archivo 3 escribe datos**: la fila semilla por organización. Es la única
   de las cuatro migraciones que inserta algo.
3. **`force row level security`**: ambas tablas nacen con FORCE, así que ni su
   dueño se salta la política. Correcto, pero conviene saberlo antes.
4. **Las tablas nacerían bajo `postgres`**, no bajo `asistente_owner` como las
   `job_*` — ninguno de los dos archivos lleva `ALTER TABLE … OWNER TO`. Es
   coherente con las otras 30 tablas de `asistente`, pero es una inconsistencia
   pendiente de decidir.
5. **Esquema por delante del código**: es la dirección segura, pero si el código
   se despliega antes que las tablas, `interruptor.py` **falla abierto** —
   permite y lo grita por consola— y la idempotencia no funcionaría. El orden
   correcto es tablas primero, código después.

## 5. Capacidad real del CLI para seleccionar migraciones

**No existe.** Los argumentos completos son:

```
--estado | --aplicar | --adoptar        (mutuamente excluyentes)
--escribir-baseline   --aceptar ARCHIVO   --motivo   --autorizado-por
--espera-lock
```

- `--aceptar ARCHIVO` **sí** selecciona un archivo, pero pertenece a
  `--adoptar`, no a `--aplicar`.
- `aplicar(con, espera, carpeta=None)` acepta una carpeta, pero **`main()` nunca
  se la pasa**: no es alcanzable desde la línea de comandos.
- No hay `--hasta`, ni `--solo`, ni rangos, ni listas. No se inventan.

**Lo que sí es el mecanismo de selección, por contrato:** el contenido del
directorio.

```python
def archivos(carpeta=None):
    """Los .sql de supabase/, en orden determinista. 'ledger/' queda afuera."""
    return [Path(p) for p in sorted(glob.glob(str(base / "*.sql")))]
```

El glob **no es recursivo**. Medido: 44 `.sql` en el nivel superior frente a 48
recursivos — los 4 de `supabase/ledger/` quedan fuera y siempre han quedado
fuera. `cli/base_desde_cero.py` y `cli/manifiesto_adopcion.py` usan el mismo
criterio, así que un subdirectorio excluye de forma consistente en todas las
herramientas.

## 6. Estrategia de reconciliación aislada

Mover los archivos 3 y 4 a un subdirectorio de `supabase/` antes de ejecutar, y
devolverlos después.

```bash
mkdir -p supabase/pendientes_despliegue
git mv supabase/202609151710_interruptor_autonomia.sql \
       supabase/202609151715_operaciones_externas.sql \
       supabase/pendientes_despliegue/
# ... ejecutar la reconciliacion ...
git mv supabase/pendientes_despliegue/*.sql supabase/
rmdir supabase/pendientes_despliegue
```

Es preferible a sacarlos del repositorio: quedan visibles, versionados y con su
intención escrita en el nombre de la carpeta.

## 7. Estrategia para dejar 3 y 4 pendientes — y que sigan aplicables

Al devolverlos, deben **ordenar después del máximo anotado**, o el CLI los trata
como huecos (`SALIDA_HUECO`) y no aplica nada.

Tras la reconciliación, `max(anotadas)` pasa a ser
`202609151705_scheduler_funciones_reconciliado.sql`. Y
`202609151710…` > `202609151705…`, así que **no hay hueco**. Verificado en
réplica.

## 8. Estado esperado del ledger

| Momento | Filas | `origen='aplicada'` |
|---|---|---|
| Hoy | 45 | 2 (las históricas) |
| Tras la reconciliación aislada | **47** | **4** |
| Tras desplegar 3 y 4 (después, aparte) | 49 | 6 |

Las 45 históricas no cambian en ningún momento.

## 9. Prueba en réplica

Réplica desde el respaldo validado `20260917_104932` (`restaurar.sh` código 0,
ledger con el md5 exacto de producción). Copia del repositorio con los archivos
3 y 4 en `supabase/pendientes_despliegue/`.

```
--estado    archivos en supabase/ : 42
            pendientes            : 2
            con checksum distinto : 0
              202609151700_scheduler_persistente_reconciliado.sql
              202609151705_scheduler_funciones_reconciliado.sql

--aplicar   [ok] 202609151700_…persistente_reconciliado  (19 ms)
            [ok] 202609151705_…funciones_reconciliado    (62 ms)
            [migrar] 2 aplicada(s).       codigo: 0
```

**Estado resultante, medido:**

| | Obtenido | Esperado |
|---|---|---|
| Ledger / `aplicada` | **47 / 4** | 47 / 4 |
| Tablas en `asistente` / `job_*` | **35 / 5** | 35 / 5 |
| Políticas en `asistente` | **35** | 35 |
| md5 de los 10 cuerpos | **`614d3a167d73bac0ca16cf6fc002a19c`** | idéntico |
| `interruptor_autonomia` / `operaciones_externas` | **no existen** | no existen |
| Filas históricas | **intactas** (`897cb5d3…`, `f325bd44…`) | intactas |
| Scheduler | **`succeeded`, 0 fallas** | funcional |

**Y al devolver los archivos 3 y 4:** 44 archivos, `checksum distinto: 0`,
**2 pendientes**, sin huecos.

## 10. Locks esperados — medidos, y distintos en cada bloque

**Reconciliación (archivos 1 y 2):**

| Archivo | Bloqueos |
|---|---|
| 1 · persistente | `AccessExclusive` sobre las 5 `job_*`; `ShareRowExclusive` sobre `job_run` y `job_schedule_state` (la FK que se recrea) |
| 2 · funciones | `AccessExclusive` sobre las 5 `job_*` **+ `asistente.tenant_config` y `tenant_config_historial`** |

**Cero bloqueos sobre `public`.** Las 5 `job_*` están vacías y sólo las leen
roles administrativos, así que el único impacto real es que el motor espera unos
**~60 ms** en `tenant_config(_historial)`.

**Despliegue (archivos 3 y 4):**

```
public.organization    ShareRowExclusiveLock    <- bloquea ESCRITURAS del CRM
```

Esa es la diferencia operativa que justifica separar: **la reconciliación no
sale de `asistente`; el despliegue sí.**

## 11. Rollback

**De la reconciliación aislada** — sin cambios respecto al paso 10.7:

- *Nivel 1* (falla antes del COMMIT de un archivo): automático; ese archivo se
  deshace entero y no queda anotado, el anterior sí.
- *Nivel 2* (hubo COMMIT): **no hay nada que revertir**. Los dos archivos dejan
  definiciones idénticas a las que ya había — medido: índices, constraints,
  políticas y cuerpos de función quedan iguales.

**De la maniobra de archivos** (separación): es un `git mv` en dos direcciones,
totalmente reversible y sin efecto en la base. Si se interrumpe a mitad, basta
con dejar el directorio como estaba antes de ejecutar nada.

**Del despliegue de 3 y 4**, si alguna vez se autoriza: `drop table` de las dos
tablas nuevas — no tienen dependientes ni datos de negocio (salvo las filas
semilla del interruptor). El ledger conserva sus filas; una reversión física se
documenta, no se borra del ledger.

## 12. Qué debe autorizarse después

Tres decisiones separadas, en este orden:

1. **La maniobra de separación** — `git mv` de los archivos 3 y 4 a
   `supabase/pendientes_despliegue/`. No toca la base.
2. **La reconciliación aislada en producción** — `--aplicar` con sólo dos
   pendientes, siguiendo el runbook del paso 10.7 (respaldo verificado,
   pre-flight en verde, `lock_timeout=10s` por sesión, credencial `postgres`).
   Ventana: sólo hace falta que el motor no esté leyendo `tenant_config`.
3. **El despliegue de los archivos 3 y 4** — decisión aparte, que además
   arrastra dos cosas por decidir: el **dueño** de esas dos tablas
   (`postgres` por omisión, frente a `asistente_owner` de las `job_*`) y el
   **orden respecto al despliegue del código** que las consume.

### Observabilidad para la ejecución productiva

**No se crearán *event triggers* de auditoría en producción.** El mecanismo será
el log del servidor, la salida del CLI, el ledger y las verificaciones del
runbook.

*Opción documentada y no ejecutada:* los *event triggers* sobre
`ddl_command_end` y `sql_drop` que se usaron en el paso 10.6 dan el inventario
exacto de DDL (113 operaciones), pero **son DDL en producción** y crean objetos
propios. Si alguna vez se quisieran, tendrían que autorizarse como cambio
independiente, con su propia limpieza posterior.

---

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, 35
tablas en `asistente`. **`--aplicar` no ejecutado, `--adoptar` no ejecutado, el
ledger sin tocar.** Repositorio: sin cambios respecto al cierre del paso 10.5 —
los archivos 3 y 4 siguen en el nivel superior de `supabase/`. Réplica `pg-108`
eliminada.
