# Evidencia de adopción y ledger de solo agregar

> Rama `ledger/evidencia`. Pasos `0002_evidencia.sql` y `0003_solo_agregar.sql`
> de `supabase/ledger/esquema/`. Probado por `tests/test_ledger_evidencia.py`.
> Nada de esto se ejecutó fuera de bases efímeras locales.

## Qué faltaba

Una fila adoptada dice que una migración se dio por aplicada **sin ejecutarla**.
Dentro de seis meses tiene que poder contestar quién, por qué, contra qué
manifiesto, contra qué servidor y qué se comprobó.

| dato | ledger v1 | desde el paso 0002 |
|---|---|---|
| migración | `archivo`, `sha256`, `algoritmo` | igual |
| que fue una adopción, y de qué tipo | `origen` | igual |
| motivo | `nota` | igual; **no** se duplica en la evidencia |
| momento | `aplicada_en` (UTC) | igual |
| rol PostgreSQL | `por_usuario` (`current_user`) | igual, y `evidencia.operacion.rol_sesion` (`session_user`) y el proceso |
| quién autorizó | — | `evidencia.autorizacion.declarada_por`; **obligatoria** con `--aceptar` |
| manifiesto exacto | — (el "manifiesto v1" de la nota es la versión del **formato**, una constante) | `evidencia.manifiesto`: `sha256`, `git_blob`, referencia con su huella |
| servidor | — | `evidencia.entorno`: `server_version`, `server_version_num`, cada extensión con versión y schema, **medidos en la base adoptada, dentro del lock** |
| qué se comprobó | solo una cantidad, en texto, y solo en las automáticas | `evidencia.verificacion`: estado en el manifiesto, comprobaciones totales y coincidentes, efectos sin comprobar |

## `--autorizado-por` es una identidad declarada

La herramienta **no autentica** a esa persona: registra lo que declara quien
corre el comando. La evidencia lo dice en `autorizacion.naturaleza`. Lo que sí
autentica PostgreSQL es el rol de la sesión, y queda aparte, en `operacion`.

- Con `--aceptar` es **obligatoria** (exit 2 sin ella, antes de conectarse al lock).
- En una baseline automática es opcional; si se da, queda en cada fila, y si no,
  `autorizacion` es `null`.
- Entre 3 y 200 caracteres, sin saltos de línea ni caracteres de control.
- Puede ser un nombre o una referencia verificable fuera del sistema (acta,
  ticket). Si se quiere evitar un nombre propio en la base, la referencia alcanza.

## Formato (`formato: 1`)

Ejemplo de una fila `baseline_humano`, tomado de la base efímera de la prueba
(solo se acortaron los hashes):

```json
{
  "formato": 1,
  "manifiesto": {
    "sha256": "…",
    "git_blob": "…",
    "calculado_sobre": "archivo",
    "formato": 1,
    "referencia": {
      "postgres": "16.14 (Debian 16.14-1.pgdg12+1)",
      "descripcion": "…",
      "huella": {"major": 16, "server_version_num": 160014, "extensiones": {"…": "…"}}
    }
  },
  "entorno": {
    "server_version": "16.14 (Debian 16.14-1.pgdg12+1)",
    "server_version_num": 160014,
    "extensiones": {
      "pg_trgm":  {"version": "1.6",   "schema": "public"},
      "pgcrypto": {"version": "1.3",   "schema": "ext"},
      "vector":   {"version": "0.8.6", "schema": "public"}
    }
  },
  "verificacion": {
    "estado_en_manifiesto": "requiere_revision_humana",
    "comprobaciones_totales": 42,
    "comprobaciones_coincidentes": 42,
    "efectos_sin_comprobacion": [["dinamico", "…"]]
  },
  "autorizacion": {
    "declarada_por": "Responsable de pruebas (acta efimera 0001)",
    "naturaleza": "declarada por quien corrio el comando; la herramienta no la autentica"
  },
  "operacion": {"rol_sesion": "motor", "aplicacion": "migrar_asistente pid=… host=…"}
}
```

- **`manifiesto.sha256`** se calcula sobre los bytes canónicos del archivo
  **leídos una sola vez**: lo que se identifica es lo que se usó.
- **`manifiesto.git_blob`** es el id que git le da a esos bytes. Encuentra el
  commit con `git log --all --find-object=<git_blob>`, aunque el archivo se haya
  regenerado después.
- **`calculado_sobre`** vale `serializacion` solo cuando el manifiesto llega
  como objeto (uso programático) y no desde el archivo.
- **`comprobaciones_coincidentes`** es igual a las totales en toda fila escrita,
  y no por suposición: la adopción automática y la aceptación humana se niegan a
  escribir con una sola comprobación que no coincida.
- **Servidor y manifiesto** se miden una vez por comando, después de la
  compuerta de huella y dentro del lock, y son los mismos en todas las filas de
  esa adopción.

## Constraints: la base las exige, no solo la CLI

| constraint | regla |
|---|---|
| `ma_evidencia_objeto` | `evidencia` es null o un objeto JSON |
| `ma_evidencia_adopcion` | toda fila que no es `aplicada` tiene evidencia con `formato`, `manifiesto`, `entorno`, `verificacion` y `operacion` |
| `ma_evidencia_autorizacion` | una `baseline_humano` tiene `autorizacion.declarada_por` de al menos 3 caracteres |

Un `INSERT` a mano de una adopción sin evidencia falla con `check_violation`
(probado).

## Un ledger v1: qué pasa al actualizarlo

**Hoy no existe ningún ledger fuera de bases efímeras.** La base objetivo no
tiene ledger: al adoptarla, los tres pasos corren juntos y no hay filas viejas.
Esto cubre el caso de todas formas.

| ledger v1 con… | resultado |
|---|---|
| solo filas `aplicada` | se actualiza a la versión 3 **sin tocar una fila**: evidencia `null`, que es lo correcto para filas ejecutadas |
| alguna fila `baseline` o `baseline_humano` | **fail-closed**: 0002 termina con SQLSTATE `LG001` antes de cambiar nada, la transacción se deshace, el lock se suelta y el comando sale con **exit 8** diciendo cuántas filas son. Pasa con `--aplicar`, `--adoptar --escribir-baseline` y `--aceptar`. Los modos de solo lectura siguen funcionando y no actualizan nada |

**Por qué no hay otra salida automática:**
- **Rellenar evidencia** de esas filas sería fabricarla: el servidor, el
  manifiesto y la persona de aquel momento no se pueden medir hoy.
- **Una constraint `NOT VALID`**, que acepte las viejas y exija la evidencia
  solo a las nuevas, dejaría para siempre una clase de filas cuya falta de
  evidencia es invisible en el catálogo. Una falla ruidosa es preferible a esa
  excepción silenciosa.

**El camino honesto**, si alguna vez aparece un ledger así, es una decisión
humana fuera de la herramienta:
1. El owner quita las filas adoptadas. En v1 no hay trigger de solo agregar.
2. Se adopta de nuevo con el migrador actual. Las automáticas se **re-verifican
   ahora** y las humanas se **re-aceptan ahora**, con `--autorizado-por`.

La evidencia resultante tiene la fecha de hoy y describe lo medido hoy, no
aquella decisión. Probado de punta a punta con el migrador v1 real
(`git archive 7c73b5a`).

## Solo agregar (paso 0003)

### Auditoría: quién modifica filas del ledger

Búsqueda de `migraciones_aplicadas` y `migraciones_ledger_esquema` en todo el
repositorio:

| lugar | operación sobre filas |
|---|---|
| `cli/migrar_asistente.py` → `aplicar` | `INSERT` en `migraciones_aplicadas` |
| `cli/migrar_asistente.py` → `asegurar_ledger` | `INSERT` en `migraciones_ledger_esquema`; los pasos son DDL |
| `cli/manifiesto_adopcion.py` → baseline y aceptación humana | `INSERT` |
| `cli/migrar_asistente.py --estado`, `manifiesto_adopcion.py --generar`, `cli/base_desde_cero.py` | `SELECT` |
| `nucleo/`, `django-crm/`, frontend | ninguna referencia |
| paso 0001 (convergencia de ledgers viejos) | `ALTER TABLE`: DDL, no filas |
| `tests/test_ledger_migraciones.py` (secciones O, Q, S) | **tres `DELETE`** para vaciar el ledger antes de adoptar |

**Ningún flujo legítimo hace `UPDATE`, `DELETE` ni `TRUNCATE`.** Los tres
`DELETE` de las pruebas simulaban "una base sin ledger". Se reemplazaron por
`DROP TABLE` de las dos tablas, que es lo que realmente tiene una base sin
ledger y lo que ya usaban `test_ledger_carreras.py` y
`test_ledger_orden_forzado.py`.

Se protegen **las dos tablas enteras**, no solo las filas `baseline*`: una fila
`aplicada` reescrita, o un paso del esquema borrado, falsean el registro igual
que una adopción.

### Qué bloquea y qué no (medido)

| operación | resultado |
|---|---|
| `UPDATE` / `DELETE` / `TRUNCATE` en cualquiera de las dos tablas | SQLSTATE `LG002`, "es de solo agregar" |
| lo mismo desde un rol que **no** es owner pero tiene `GRANT UPDATE` | `LG002`, no un error de permisos |
| `INSERT` (una migración nueva que se aplica) | funciona |
| `ALTER TABLE` sobre el ledger (lo que haría un paso 0004) | funciona: el DDL no dispara estos triggers |
| **el owner** hace `ALTER TABLE … DISABLE TRIGGER` y borra | **funciona.** No es una protección contra el owner ni contra un superusuario; es una barrera contra errores operativos |

La función del trigger vive en el schema `asistente_ledger` y no en `asistente`.
El manifiesto de adopción compara los grants de **todas** las funciones de
`asistente` (`grant execute on all functions in schema asistente`), y una
función nueva ahí haría "no equivalente" a cualquier base adoptada.

### Si una fila está mal

No hay camino en la herramienta, a propósito. Corregirla es un acto deliberado
del owner: en una transacción, desactivar el trigger, corregir y reactivarlo. Y
dejar constancia **fuera** del ledger (acta o ticket) de qué se cambió y por
qué. Si un paso futuro del esquema necesitara reescribir filas, tendría que
desactivar y reactivar el trigger explícitamente dentro de su propio archivo,
donde queda revisable.

## Cómo citar la inspección previa

La decisión de aceptar se toma leyendo el resultado de
`supabase/ledger/analisis/inspeccion_solo_lectura.sql`. Conviene que el
`--motivo` cite el commit y el git blob del script usado:

```
git rev-parse <commit>:supabase/ledger/analisis/inspeccion_solo_lectura.sql
```

Así queda escrito con qué consultas exactas se decidió.
