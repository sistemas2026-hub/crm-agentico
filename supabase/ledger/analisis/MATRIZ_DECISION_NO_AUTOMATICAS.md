# Matriz de decisión — las siete migraciones no automáticas

> **Nada de esto se ejecutó ni se decidió.** Es una propuesta para la decisión
> del usuario. Ninguna consulta se corrió contra producción. Los hechos de cada
> archivo están en `MIGRACIONES_NO_AUTOMATICAS.md` y
> `202609070900_bandeja_sin_inflar.md`.

## Categorías

- **A · AUTOMATIZAR**: el manifiesto la adopta sin intervención.
- **B · ADOPTAR/VERIFICAR SIN EJECUTAR**: se anota como `baseline_humano` después
  de verificar su estado actual. **Nunca se ejecuta sobre una base existente.**
- **C · REESCRIBIR EN UNA MIGRACIÓN NUEVA Y SEGURA**: el efecto que falte, o el
  hardening que falte, va en un archivo nuevo, idempotente y revisado. El
  histórico se adopta por B.
- **D · REQUIERE DECISIÓN HUMANA**: con la evidencia disponible no hay una
  respuesta técnica; decide el usuario.

Una regla atraviesa las siete: **ninguna recibe A**. Convertirlas en
automáticas solo para que la adopción salga "100 % verde" sería exactamente el
atajo que el ledger existe para impedir. Y ninguna se re-ejecuta: en una base
existente, el histórico se adopta, no se corre.

## La matriz

| archivo | propuesta | condición para aplicar la propuesta | qué decide el usuario |
|---|---|---|---|
| `202608042055_schema.sql` | **B** (sus efectos) + **C** (hardening preexistente) | las consultas de catálogo de los tres `DO` coinciden; las partes estáticas ya las exige el manifiesto | si acepta la membresía de `app_backend` que encuentre, y si abre la migración C (abajo) |
| `202608211448_diagnostico_recuperacion.sql` | **D → B** | el censo por `modelo_embeddings` no muestra `null` ni `bge-m3` | si hay `bge-m3`: ¿algún tenant lo usa a propósito? Eso es de producto |
| `202609061400_bloqueos_en_traza.sql` | **B**, o **C** si falla | `bloqueos_sin_marcar = 0` | con 0, nada. Con más de 0, autorizar C: la misma regla que aplica hoy el código |
| `202609061700_cola_priorizada.sql` | **B**, o **D** si falla | `escaladas_sin_fecha = 0` | con más de 0: rellenar con una aproximación es de producto; si se hace, va en C marcando las filas como aproximadas |
| `202609070900_bandeja_sin_inflar.sql` | **D → B** | default = `false` y md5 del comentario coinciden | aceptar "DDL demostrado, efecto de datos asumido". Si `marcadas_fuera_de_regla > 0`, esas filas son una decisión de producto aparte |
| `202609071900_tomar_caso.sql` | **D → B**, **nunca re-ejecutar** | ver diseño abajo | aceptar que el efecto de datos **no es demostrable** |
| `202609080802_historial_de_config.sql` | **B**, o **C** si falla | `vigentes_sin_historial = 0` | con más de 0, autorizar C: insertar la versión vigente que falte, con `on conflict do nothing` |

### Por qué cada una

**`bloqueos_en_traza` (B/C).** El código actual aplica **exactamente** la misma
regla que el `UPDATE` (`CODIGOS_DE_BLOQUEO` son los seis códigos). Si la
invariante se cumple, el estado es el de una base construida desde cero y no hay
nada que correr. Si no se cumple, la corrección es la regla vigente del código,
no el histórico: va en una migración nueva, fechada hoy, que el ledger registra
como propia.

**`cola_priorizada` (B/D).** La invariante la mantiene `marcar_escalada`. Pero si
falla, el relleno no es neutral: escribe `actualizado_en` como si fuera el
momento de la escalada. Aceptar ese dato aproximado es una decisión de producto.

**`historial_de_config` (B/C).** Con P2 integrado, una versión vigente sin
historial hace que `job_claim` **no arranque el turno**: falla ruidosa, no
silenciosa. Por eso completar lo que falte es seguro y se puede hacer en C;
`on conflict do nothing` no pisa filas.

**`diagnostico_recuperacion` (D→B).** El censo distingue "no hay nada que
corregir" de "hay datos que podrían ser legítimos". Solo lo segundo requiere
decisión, y es de producto: qué modelo usa cada tenant.

**`bandeja_sin_inflar` (D→B).** Se retiró la inferencia de atomicidad:
`cli/migraciones.py` nunca habría ejecutado ese archivo, porque no le veía
objetos. Sin evidencia externa de cómo se aplicó, lo máximo afirmable es "DDL
demostrado, efecto de datos asumido".

## `tomar_caso` — cómo adoptarla sin re-ejecutarla

**No re-ejecutar, nunca.** El `UPDATE` depende de la zona horaria de la sesión
(`actualizado_en::date` sobre `timestamptz`), y además alcanza filas que una
persona marcó atendidas **después**, porque `marcar_atendida` no mueve
`actualizado_en`. Repetirlo pisaría decisiones humanas sin registro.

**Qué se puede demostrar y qué no.**

| pieza | cómo | tipo de evidencia |
|---|---|---|
| columnas, comentarios e índice | el manifiesto (partes estáticas) | **demostración**: la aceptación humana ya las exige |
| que el `UPDATE` original corrió | ninguna consulta lo distingue: después de correr, `actualizado_en` siguió moviéndose, y "tomar" desde la pantalla deja rastros idénticos | **no demostrable** |
| cuánto daño haría repetirlo | exposición en UTC y en `America/Bogota` (consultas del análisis) | **medición**, útil para justificar no repetir |
| impacto de que NO haya corrido | casos del 07/09 que quedarían "atendidos" en vez de "tomados": acotado a un día y cada vez menos relevante | **acotación** |

**Procedimiento propuesto para marcarla adoptada:**

1. Con autorización, ejecutar en la base objetivo las dos consultas del análisis
   (exposición por zona horaria y rastro débil del 07/09). Solo lectura.
2. `migrar_asistente.py --adoptar --aceptar 202609071900_tomar_caso.sql` en solo
   lectura: confirma que sus partes estáticas coinciden.
3. **Si el usuario acepta** que el efecto de datos no es demostrable, la misma
   orden con `--escribir-baseline`, un `--motivo` que lo diga explícitamente e
   incluya los dos conteos, y `--autorizado-por` con la persona o el acta que lo
   autoriza. Queda `baseline_humano` con motivo, autorización declarada y la
   evidencia estructurada (manifiesto, servidor, comprobaciones): ver
   `EVIDENCIA_DE_ADOPCION.md`.
4. Si el usuario **no** acepta, la migración queda pendiente. Eso bloquea
   `--aplicar` por hueco, a propósito: no hay forma correcta de "completarla"
   automáticamente.

**No se escribe una migración C** que replique la corrección: era un ajuste
puntual de un día, y copiarlo hoy tendría los mismos dos defectos.

## `schema.sql` — separado por efecto

Adoptar `schema.sql` **no revierte ningún hardening**, porque adoptar no ejecuta
nada. Lo que revertiría hardening es **ejecutarlo**, y eso no se propone.

| efecto | estado actual (medido en base efímera construida desde cero) | propuesta |
|---|---|---|
| extensiones, schema, 12 tablas, índices, `tenant_config` y su política estática | verificado por el manifiesto contra la referencia | **B** (automático dentro de la aceptación) |
| `org_actual`, `gasto_del_mes` | ídem; no redefinidas después | **B** |
| `match_chunks` de 5 argumentos (sin filtro de rol) | **existe hoy junto a la de 6**, pero es **inalcanzable**: llamadas con 2 o 5 argumentos dan `AmbiguousFunction`; con `p_rol` resuelve la filtrada; el único llamador usa `p_rol =>` | **B** para adoptar; **C** para quitarla (latente: vuelve a ser alcanzable si se borra la de 6) |
| `match_chunks_hibrido` | existe, **no filtra por rol**, ejecutable por `app_backend`; ningún código la llama | **C**: agregarle el filtro de rol o eliminarla — decisión |
| `grant execute on all functions in schema asistente to app_backend` | presente; P2 revoca explícitamente sus funciones después | **B** para adoptar; **C** para reemplazar el comodín por grants por función |
| `DO` 1: rol `app_backend` + `grant app_backend to current_user` | verificable por catálogo; **quién** quedó miembro depende de quién lo corrió | **B** con consulta de membresías; el usuario confirma que los miembros son los esperados |
| `DO` 2: RLS habilitada y forzada + 4 privilegios en 12 tablas | verificable por catálogo | **B** |
| `DO` 3: `tenant_aislado` en 11 tablas | verificable por catálogo (definición igual a la de `tenant_config`) | **B** |

**Migración C propuesta (no escrita, no ejecutada), si el usuario la autoriza:**
un archivo nuevo que haga `drop function asistente.match_chunks(uuid, vector,
integer, real, jsonb)` —la de 5 argumentos—, decida `match_chunks_hibrido`
(filtro de rol o `drop`), y cambie el comodín de `EXECUTE` por grants explícitos
de las funciones que `app_backend` usa. Va **después** en la cadena, con su
propia prueba de que `busqueda.py` sigue resolviendo y de que un rol no recupera
documentos ajenos.

**Mecanismo propuesto para que B sea reproducible (no implementado):**
verificaciones de catálogo escritas por una persona, versionadas por archivo
(p. ej. `supabase/ledger/verificaciones_humanas/<archivo>.sql` con consulta y
resultado esperado), que `--aceptar` ejecute y cite en la nota. Así la
aceptación humana de los `DO` deja de depender de que alguien corra consultas a
mano.

## Decisiones que quedan en manos del usuario

1. Para cada una: autorizar las consultas de solo lectura en la base objetivo.
2. `bandeja_sin_inflar` y `tomar_caso`: aceptar "efecto de datos no demostrable"
   o dejarlas pendientes, sabiendo que eso bloquea `--aplicar`.
3. `diagnostico_recuperacion`: si aparece `bge-m3`, qué modelo es el correcto
   por tenant.
4. `cola_priorizada`: si falla la invariante, si se acepta una fecha aproximada.
5. `schema.sql`: si las membresías de `app_backend` encontradas son las esperadas,
   y si se abre la migración C de hardening (`match_chunks` de 5 argumentos,
   `match_chunks_hibrido`, comodín de `EXECUTE`).
