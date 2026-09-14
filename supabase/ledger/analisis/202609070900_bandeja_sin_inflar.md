# `202609070900_bandeja_sin_inflar.sql` — análisis para decisión humana

> **Estado en el manifiesto: `migracion_de_datos_no_repetible`. NO VERIFICADA.**
> Este documento no decide. Presenta los hechos, cómo verificarlos sin
> escribir y las dos alternativas con sus riesgos.

- Hash canónico (`sha256-utf8-lf-v1`): `6040ebd5f6931c48f748313900b3c2b508d17697aaf1ed11148248ef29126d35`
- Commit de origen: `008e6f4` (2026-09-06), "La bandeja decia 155 esperando y eran 31"
- 66 líneas; 48 de comentario, 3 sentencias.

## Objetivo

La cabecera de la bandeja contaba 155 conversaciones "esperando a una persona"
y eran 31. Causa: la columna `necesita_atencion_humana` nació con
`DEFAULT TRUE`, así que toda conversación quedaba marcada aunque el asistente la
resolviera solo. La migración corrige el default y apaga la marca en las filas
que la tienen solo por ese default.

## Contenido completo (sentencias ejecutables)

```sql
alter table asistente.conversations
  alter column necesita_atencion_humana set default false;

comment on column asistente.conversations.necesita_atencion_humana is
  'Alguien del equipo tiene que entrar a esta conversacion. La pone el motor '
  'al escalar (donde distingue "escalo pero puede esperar" de "hace falta '
  'alguien ya") y el camino de NO_DETERMINADO, cuando el evaluador se cayo y '
  'no se pudo decidir si correspondia escalar. Nacio con DEFAULT TRUE por '
  'error y eso inflaba la bandeja cinco veces: desde el 07/09/2026 el default '
  'es false y la marca solo esta puesta cuando alguien la puso.';

update asistente.conversations
   set necesita_atencion_humana = false
 where necesita_atencion_humana
   and not escalada_a_humano
   and coalesce(estado_escalada, '') <> 'NO_DETERMINADO';
```

El archivo completo, con sus 48 líneas de comentario, está en
`supabase/202609070900_bandeja_sin_inflar.sql` y no se modifica.

## Qué afecta

| efecto | objeto | tipo |
|---|---|---|
| 1 | `asistente.conversations.necesita_atencion_humana` — default `true` → `false` | catálogo (DDL) |
| 2 | comentario de esa columna | catálogo |
| 3 | filas de `asistente.conversations` con la marca puesta, sin escalar y sin `NO_DETERMINADO` → marca en `false` | **datos** |

No crea ni cambia funciones, políticas RLS, grants, triggers ni índices.

## ¿Es idempotente?

- **Efectos 1 y 2: sí.** Repetirlos deja el mismo catálogo.
- **Efecto 3: no ocasiona error al repetirse, pero no es neutral.** Repetirlo hoy
  apaga toda marca `true` que no cumpla la condición de exclusión, **se haya
  puesto cuando se haya puesto**.

Quién pone la marca en `true` en el código actual (`f60beda`):

| escritor | cómo | ¿lo excluye el `UPDATE`? |
|---|---|---|
| `db.marcar_escalada` (`nucleo/persistencia/db.py:676`) | pone también `escalada_a_humano = true` | sí |
| `db.registrar_estado_escalada(..., necesita_atencion=True)` (`db.py:1673`) | sin tocar `escalada_a_humano`; llamada solo desde `api.py:358` cuando `estado == NO_DETERMINADO` y desde `api.py:1058` con `NO_DETERMINADO` literal | sí, **mientras `estado_escalada` siga en `NO_DETERMINADO`** |

El caso que **no** queda excluido, visible en el código y **no medido en
datos**: una conversación marcada por `NO_DETERMINADO` cuyo `estado_escalada` es
sobrescrito en un turno posterior por la otra rama de `registrar_estado_escalada`
(`necesita_atencion=False`), que actualiza `estado_escalada` y **no** toca la
marca. Queda con marca `true`, sin escalar y con otro estado. Una segunda
ejecución la apagaría y esa conversación desaparecería de "Sin atender".

El `UPDATE` no escribe `actualizado_en` ni ninguna otra huella: **no queda
registro de qué filas cambió**, ni la primera vez ni una segunda.

## Cómo saber si ya fue aplicada — solo lectura, sin PII

```sql
-- Efecto 1: el default. Esperado: 'false'.
select column_default
  from information_schema.columns
 where table_schema = 'asistente' and table_name = 'conversations'
   and column_name = 'necesita_atencion_humana';

-- Efecto 2: el comentario. Esperado (md5 del texto de la referencia):
-- de6e587325b1a623f37a96f98f689911
select md5(col_description('asistente.conversations'::regclass, a.attnum))
  from pg_attribute a
 where a.attrelid = 'asistente.conversations'::regclass
   and a.attname = 'necesita_atencion_humana';

-- Efecto 3: agregados, sin identificar ninguna conversacion.
select count(*) filter (where necesita_atencion_humana
                          and not escalada_a_humano
                          and coalesce(estado_escalada, '') <> 'NO_DETERMINADO')
         as marcadas_fuera_de_regla,
       count(*) filter (where necesita_atencion_humana) as marcadas,
       count(*) as total
  from asistente.conversations;
```

Cómo leerlo:

- **1 y 2 coinciden** → la parte DDL del archivo corrió. Es evidencia fuerte:
  ningún otro archivo de `supabase/` pone ese default ni ese comentario.
- **3 = 0** → compatible con que el `UPDATE` corrió, **pero no lo prueba**: también
  daría 0 si nunca hubo filas fuera de regla.
- **3 > 0** → puede ser que el `UPDATE` no corrió **o** el caso legítimo descrito
  arriba. El catálogo no permite distinguirlos.

Estas consultas no se ejecutaron contra producción: requieren autorización.
El manifiesto ya verifica automáticamente los efectos 1 y 2 como partes
estáticas de esta migración; el efecto 3 queda sin comprobación.

## Riesgos

**De marcarla como baseline sin demostrarla**

- Si en producción el archivo nunca corrió, el default seguiría en `true` para
  siempre y la bandeja volvería a inflarse con cada conversación nueva.
  *Mitigación existente:* la aceptación humana (`--aceptar`) exige que las partes
  estáticas —default y comentario— coincidan con la referencia; ese caso se
  rechaza solo.
- Riesgo residual: la parte DDL corrió y el `UPDATE` no (por ejemplo, si se
  ejecutó sentencia por sentencia y la última se omitió o falló). Quedarían
  marcas heredadas del default viejo. No hay forma de detectarlo desde el
  catálogo.

**De ejecutarla nuevamente**

- Apaga, sin registro y sin reversión posible, marcas legítimas que no cumplen la
  condición de exclusión (el caso de `estado_escalada` sobrescrito).
- Impacto operativo directo: conversaciones de clientes que esperan a una persona
  dejan de figurar en "Sin atender".
- Además, en el ledger una ejecución solo puede ocurrir por `--aplicar`, que hoy
  **se niega** mientras esta migración sea un hueco anterior a otras anotadas.
  Ejecutarla exigiría quitar esa protección o correrla a mano, fuera del ledger.

## Las dos alternativas

**A. Aceptación humana individual, sin re-ejecutar**

1. Autorizar y ejecutar en producción las tres consultas de solo lectura.
2. Si 1 y 2 coinciden:
   `--adoptar --aceptar 202609070900_bandeja_sin_inflar.sql --motivo "<evidencia y quién decide>" --escribir-baseline`.
   Queda con origen `baseline_humano` y la nota con quién y por qué.
3. Si 3 > 0, decidir aparte, con información de producto, si esas filas se
   revisan. No se decide automáticamente.

Supuesto que se acepta: que el efecto sobre datos ocurrió, con evidencia
indirecta y sin prueba.

**B. Ejecutarla nuevamente**

1. Autorizar y ejecutar primero la consulta 3.
2. Aceptar explícitamente que toda marca contada en `marcadas_fuera_de_regla` se
   apagará, incluidas las legítimas.
3. Ejecutarla con un procedimiento que registre qué filas cambió (el archivo no
   lo hace) y **fuera** del camino `--aplicar`, que la rechaza como hueco.

Supuesto que se acepta: que ninguna marca actualmente fuera de regla es legítima.

**No se recomienda ninguna en este documento.**
