# Paso 10.1 — Procedencia de las 2 migraciones de Fase 1

**Fecha:** 17/09/2026
**Alcance:** diagnóstico. **Producción no se modificó**, el ledger no se tocó,
no se aplicó ninguna migración, no se concedió ningún permiso.
**Veredicto:** el contenido exacto **no es recuperable**. Pero la divergencia
**sí quedó identificada**, y es funcional, no cosmética.

> **El hallazgo:** lo que se ejecutó el 15/09 usaba `extensions.digest` y
> `extensions.gen_random_bytes`. El repositorio dice `ext.`. En producción el
> esquema `ext` **no existe**. Se midió leyendo los cuerpos de las funciones,
> que PostgreSQL guarda literalmente.

---

## 1. Estado inicial

Sin cambios respecto al cierre del paso 10: 135 tablas en `public`, 132
políticas, 192 filas en `django_migrations`, `case` 185 / `activity` 562. El
ledger tiene 45 filas. Las 2 migraciones de Fase 1 siguen pendientes y sin
aplicar.

Todas las consultas de esta etapa se abrieron con `read_only = True`: el propio
PostgreSQL rechaza cualquier escritura en esas sesiones.

---

## 2. Las dos filas exactas del ledger

`asistente.migraciones_aplicadas`, tabla de solo-agregar con disparadores que
impiden `UPDATE`, `DELETE` y `TRUNCATE`.

| Columna | `202609141200_scheduler_persistente.sql` | `202609141300_scheduler_funciones.sql` |
|---|---|---|
| `archivo` (clave primaria) | `202609141200_scheduler_persistente.sql` | `202609141300_scheduler_funciones.sql` |
| `sha256` | `897cb5d3da222e85913f288aace4b6fe02fb34eb2b9254d47212a6be47d8fc0e` | `f325bd442baad0f70168deedd92175f5ffb15cecc79055f9cbfdd4c2165e77f1` |
| `algoritmo` | `sha256-utf8-lf-v1` | `sha256-utf8-lf-v1` |
| `aplicada_en` | **2026-09-15 19:32:03.648710+00** | **2026-09-15 19:40:13.622699+00** |
| `duro_ms` | **338** | **289** |
| `origen` | **`aplicada`** | **`aplicada`** |
| `por_usuario` | `postgres` | `postgres` |
| `nota` | `NULL` | `NULL` |
| `evidencia` | `NULL` | `NULL` |

Dos detalles que importan:

- Son las **únicas dos filas con `origen='aplicada'`** de todo el ledger. Las
  otras 43 son `baseline` (36) y `baseline_humano` (7), todas del 15/09 entre
  las 18:36 y las 18:37 UTC, y todas con `duro_ms = 0`.
- `duro_ms` 338 y 289: **ejecutaron SQL de verdad**, no fueron adopciones.
- `evidencia` es `NULL` porque la restricción `ma_evidencia_adopcion` sólo la
  exige cuando `origen <> 'aplicada'`. No hay metadato adicional que recuperar.

---

## 3. Algoritmo de checksum, reproducido

Está escrito en `cli/migrar_asistente.py` (contrato en las líneas 30-40,
implementación en `bytes_canonicos`, líneas 167-187):

1. Leer los **bytes** del archivo, sin decodificar.
2. Si empieza con `EF BB BF` (BOM UTF-8) → **rechazo**.
3. Decodificar UTF-8 estricto; si falla → **rechazo**.
4. Reemplazar cada `CR LF` (`0D 0A`) por `LF` (`0A`).
5. Si queda algún `CR` suelto → **rechazo**.
6. `SHA-256` de esos bytes canónicos, hex minúscula.

El nombre del archivo **no** entra al hash. Lo que se ejecuta es exactamente el
texto canónico que se hashea.

**Validación de mi reproducción** — antes de usarla para concluir nada: la
apliqué a los 42 archivos presentes que el ledger anota y dio **40
coincidencias + 2 divergencias**, más 3 anotadas sin archivo: exactamente el
veredicto que imprime el CLI (`--estado`). El algoritmo reproducido es el
correcto.

---

## 4. Evidencia en Git

| Búsqueda | Resultado |
|---|---|
| Ramas locales | 2 (`fix/integracion-wisphub` en `108935f`, `fix/agendamiento-automatico-y-tuteo`) |
| Ramas remotas | 5, incluidas `origin/ledger/cierre-auditoria` y `origin/ledger/evidencia` (ambas del 14/09) |
| Tags | ninguno |
| Stash | 2 entradas, ninguna con estos archivos |
| Worktrees | 1 (el propio repo) |
| Reflog | 1.019 entradas revisadas |
| `git fsck --dangling --unreachable` | 75 objetos inalcanzables |
| Commits del 15/09 | 11, **el último a las 11:20:57 -0500 = 16:20:57 UTC** |
| Commits posteriores a la aplicación | **ninguno** |

**Búsqueda exhaustiva.** No me limité al historial alcanzable: enumeré **los
3.808 blobs de la base de objetos** —alcanzables, colgantes e inalcanzables—,
canonicé cada uno y calculé su SHA-256.

> **Ninguno de los 3.808 blobs produce ninguno de los dos checksums.**

La cronología lo explica: el último commit es de las **16:20 UTC** y las
migraciones se aplicaron a las **19:32 y 19:40 UTC**, tres horas después. El
contenido ejecutado vivía en el árbol de trabajo, nunca se commiteó, y después
el árbol volvió al contenido commiteado (hoy `git status` da los dos archivos
limpios).

---

## 5. Artefactos, despliegues y copias locales

| Fuente | Resultado |
|---|---|
| CI/CD (`.github/workflows`, `.gitlab-ci.yml`, `.circleci`) | **no existe ninguno** en el repositorio |
| Imágenes Docker locales | la más reciente del motor es del **21/08**, anterior a los archivos; y su Dockerfile no incluye `supabase/` |
| Copias del repositorio en disco | `C:\Users\Usuario\django-crm` (otro proyecto) |
| Búsqueda de los `.sql` fuera del repo | `find` bajo `C:\Users\Usuario` (6 niveles): **0 copias** |
| Transcripciones de Claude Code | 3 sesiones. Sólo una menciona los archivos: la actual |
| **La sesión actual el 15/09** | 3.042 entradas ese día, repartidas así por hora UTC: 12h=220, 13h=313, 14h=381, 15h=347, 16h=64, **17h–20h = 0**, 21h=73, 22h=1086, 23h=501 |

> **La sesión no tiene ni una entrada entre las 16:00 y las 21:00 UTC del
> 15/09.** Las migraciones se aplicaron a las 19:32 y 19:40, dentro de ese
> hueco. **No se aplicaron desde esta sesión.**

Los 9 fragmentos de SQL del scheduler que sí aparecen en el registro son del 16
y 17/09 —material de estos mismos informes— y ninguno reproduce los checksums.

---

## 6. Versiones candidatas

| # | Origen | Versiones |
|---|---|---|
| 1 | Árbol de trabajo actual | 1 por archivo |
| 2 | Historial de git del archivo | 3 (`persistente`) y 5 (`funciones`) |
| 3 | Todos los blobs del ODB | 3.808 |
| 4 | Transformaciones sobre 1 y 2 | 6 variantes (`ext.`→`extensions.` en distintos alcances, y la inversa) |

Total evaluado: **3.808 blobs + 60 combinaciones** (versión × transformación).

---

## 7. Checksum de cada candidata

**`202609141200_scheduler_persistente.sql`** — objetivo `897cb5d3…`

| Versión | Checksum |
|---|---|
| árbol actual | `d77a31b201ab6111…` |
| `9971905` (14/09) | `d77a31b201ab6111…` |
| `c869510` (14/09) | `46db64583c23f0b4…` |
| `000c1a9` (14/09) | `6d43a5c378d315fd…` |
| + 6 transformaciones sobre cada una | ninguna coincide |

**`202609141300_scheduler_funciones.sql`** — objetivo `f325bd44…`

| Versión | Checksum |
|---|---|
| árbol actual | `63bc3f14ffa5f384…` |
| `79b1f10` (14/09) | `63bc3f14ffa5f384…` |
| `532b742` (14/09) | `ee379c67fdd9c651…` |
| `9971905` (14/09) | `df4c965f16dde928…` |
| `d84a222` (14/09) | `dcaf578fbffb0dc3…` |
| `c869510` (14/09) | `270dc5cc47083388…` |
| + 6 transformaciones sobre cada una | ninguna coincide |

---

## 8. Comparación con el checksum histórico

Ninguna candidata coincide. **Pero la comparación decisiva no es contra git,
sino contra el catálogo**: PostgreSQL guarda el cuerpo de cada función
(`pg_proc.prosrc`) **literalmente, tal como se ejecutó**. Comparando las 10
funciones del archivo actual contra las 10 de producción:

| Resultado | Funciones |
|---|---|
| **Idénticas byte a byte** | 6 — `job_cerrar_turno`, `job_finalize`, `job_heartbeat`, `job_salud`, `job_slot`, `jobs_vencidos` |
| **Distintas** | 4 — `job_claim`, `job_contexto`, `job_intento_vigente`, `job_intento_vigente_por_capability` |

Y las 4 divergencias son **todas del mismo tipo, una sola sustitución**:

```
archivo:      encode(ext.digest(v_cfg::text, 'sha256'), 'hex')
produccion:   encode(extensions.digest(v_cfg::text, 'sha256'), 'hex')

archivo:      v_cap := encode(ext.gen_random_bytes(32), 'hex');
produccion:   v_cap := encode(extensions.gen_random_bytes(32), 'hex');
```

Medido en producción:

| Comprobación | Resultado |
|---|---|
| `pgcrypto` | esquema **`extensions`**, v1.3 |
| ¿Existe el esquema `ext`? | **NO EXISTE** |
| `extensions.digest(text,text)` | **resuelve** |
| `ext.digest(text,text)` | **NO EXISTE** |
| `extensions.gen_random_bytes(integer)` | **resuelve** |
| `ext.gen_random_bytes(integer)` | **NO EXISTE** |
| `search_path` de las funciones | `pg_catalog` — obliga a nombres calificados |

Esto reconstruye la historia sin especular: el 15/09 se editó el árbol de
trabajo cambiando `ext.` por `extensions.` para que las migraciones
**funcionaran contra la instalación real de Supabase**, se aplicaron así, y
después el árbol volvió al contenido commiteado. La edición nunca se commiteó.

Las transformaciones automáticas no reproducen el checksum porque la edición
real no fue una sustitución global limpia sobre ninguna de las versiones
commiteadas: hay al menos una diferencia más que no deja rastro en el catálogo
(comentarios, espacios, o el texto del `hint` de la guarda).

---

## 9. Objetos de `asistente` que dejaron esas migraciones

Todos existen y están vivos en producción.

**5 tablas**, todas de `asistente_owner`, con RLS activa y **sin** `FORCE`:

| Tabla | Columnas |
|---|---|
| `job_attempt` | 13 |
| `job_catalogo` | 10 |
| `job_run` | 13 |
| `job_run_event` | 7 |
| `job_schedule_state` | 14 |

**21 índices** · **48 restricciones** (`ja_cap_len`, `ja_cap_unica`,
`jr_superclave_org`, `js_lease_par`, …) · **5 políticas RLS**
(`tenant_aislado` ×4 y `catalogo_legible`) · **0 triggers de usuario**.

**10 funciones**, todas de `asistente_owner`, 9 de ellas `SECURITY DEFINER`:
`job_cerrar_turno`, `job_claim`, `job_contexto`, `job_finalize`,
`job_heartbeat`, `job_intento_vigente`, `job_intento_vigente_por_capability`,
`job_salud`, `job_slot`, `jobs_vencidos`.

Las dos migraciones **sí dejaron sus cambios físicos**, y el subsistema está
operativo: `asistente_owner` posee todo, coherente con el resto del dominio del
motor.

---

## 10. Conclusión sobre la procedencia

**Categoría B — recuperada parcialmente.** Con una precisión importante:

- **El contenido exacto: NO recuperable.** Ni en los 3.808 objetos de git, ni
  en imágenes, ni en CI, ni en copias en disco, ni en los registros de sesión.
  No hay forma de reproducir los bytes que generan `897cb5d3…` y `f325bd44…`.
- **El efecto ejecutado: recuperado por completo.** Las 10 funciones se leen
  literales del catálogo, y el inventario de tablas, índices, restricciones y
  políticas está completo (§9).
- **La divergencia: identificada y acotada.** No es cosmética: el repositorio
  llama a `ext.digest`/`ext.gen_random_bytes` y producción ejecuta
  `extensions.…`. Seis de las diez funciones son idénticas; las otras cuatro
  difieren sólo en eso.

---

## 11. Riesgos

1. **El repositorio no describe lo que corre en producción.** Es el riesgo de
   fondo: 4 de 10 funciones del scheduler difieren del repo en el esquema de
   `pgcrypto`. Cualquiera que lea `supabase/202609141300_scheduler_funciones.sql`
   creyendo que es lo desplegado, se equivoca.

2. **Re-aplicar el archivo actual en producción abortaría.** Su guarda de
   pre-vuelo comprueba `ext.digest` y `ext.gen_random_bytes`, y **ninguna de las
   dos existe** en producción. Falla en seco, sin tocar nada — la guarda hace su
   trabajo — pero significa que el archivo del repo no es aplicable tal cual.

3. **El procedimiento de restauración de B.6 produce un scheduler roto.**
   Medido, no deducido: el volcado lleva `extensions.digest` en los cuerpos de
   las funciones, trae **sólo 3 esquemas** (`public`, `asistente`,
   `asistente_ledger`) y **0 entradas `EXTENSION`**; y B.6 §B manda
   `create extension pgcrypto with schema ext`. En la copia restaurada,
   `extensions.digest` no existe y **cualquier llamada a `job_claim` falla**.
   No se detectó antes porque ninguna de las restauraciones de B.7, del
   simulacro del paso 9 ni del paso 10 llegó a ejercitar el scheduler.
   **B.6 necesita corrección**, en una etapa autorizada aparte.

4. **El ledger seguirá bloqueando toda migración de Fase 1** mientras las dos
   filas divergentes sigan así. `--aplicar` es todo-o-nada.

5. **No hay registro de quién ni cómo.** `por_usuario='postgres'`,
   `evidencia=NULL`, ninguna sesión de Claude Code en esa ventana. La aplicación
   del 15/09 a las 19:32/19:40 UTC no tiene trazabilidad más allá de estas dos
   filas.

---

## 12. Opciones de resolución — ninguna ejecutada

**Para el ledger** (todas respetan el carácter de solo-agregar; ninguna borra,
actualiza ni fuerza un checksum):

- **A · Alinear el repositorio con producción.** Editar los dos archivos para
  que digan `extensions.` —lo que de verdad corre—, commitearlo, y anotar la
  divergencia por la vía que el CLI ya tenga prevista para reconocerla. Ventaja:
  el repositorio pasa a describir la realidad. Inconveniente: el nuevo checksum
  tampoco será el del ledger, así que hace falta igualmente una decisión sobre
  esas dos filas.
- **B · Alinear producción con el repositorio.** Crear el esquema `ext`, instalar
  ahí `pgcrypto` y recrear las 4 funciones. Es una migración nueva sobre el
  dominio del motor: mucho más invasiva, y hoy no hay nada roto que lo justifique.
- **C · Reconocer la divergencia sin tocar ninguna de las dos.** Añadir al CLI
  una forma explícita y auditada de anotar «esta fila quedó divergente, aquí está
  la evidencia de por qué», con la comparación de §8 como evidencia. Es la que
  menos supone y la que deja mejor registro.

**Para el riesgo 3 (restauración)**, con independencia de lo anterior: corregir
B.6 §B para instalar `pgcrypto` en el esquema **`extensions`**, que es donde
está en producción, y añadir a la verificación de restauración una llamada real
a `asistente.job_claim` — una prueba que ejercite el mecanismo, no que compruebe
que existe.

**Recomendación:** resolver primero el riesgo 3, que es el único con
consecuencia operativa inmediata (un respaldo que no restaura del todo), y
después decidir entre A y C para el ledger.
