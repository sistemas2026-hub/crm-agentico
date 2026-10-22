# AUTONOMÍA 2 — CORRECCIÓN QUIRÚRGICA: DECISIÓN DESCONOCIDA → FAIL-CLOSED

Fecha: 2026-09-19 · **PASS**

Sin commit. Sin activar Autonomía 2. Sin migraciones productivas. Sin tocar
`DBUSER`, Dokploy, RLS, M09 ni M11.

---

## EL CAMBIO

`nucleo/seguridad/idempotencia.py::ejecutar()`. Tres líneas de lógica:

```python
if decision != "ejecutar":
    return Resultado(ejecutada=False, decision="desconocida", clave=clave,
                     codigo=DECISION_DESCONOCIDA, ...)

# decision == "ejecutar": la operacion es nuestra.
respuesta = hacer()
```

Antes, ese punto se alcanzaba con un comentario que **decía**
`decision == "ejecutar"` y un código que no lo comprobaba: cualquier valor
distinto de los cuatro tratados arriba caía ahí y **la mutación salía**.

Dos decisiones dentro del cambio, ambas deliberadas:

- **No se toca el registro.** El reclamo pudo haber dejado la fila en
  `ejecutando` o no haberla tocado — no se sabe, porque no se entiende su
  respuesta. Marcarla `fallida` afirmaría que la operación se intentó, y no se
  intentó. Si quedó reclamada, vence sola por `SEGUNDOS_VENCIDA` (300 s) y otro
  proceso la rescata: eso es un estado controlado; inventar una transición no
  lo sería.
- **El código se declara como bloqueo**, no como error de un tercero. Sin eso,
  el modelo le diría al cliente que falló un sistema — cuando lo que pasó es
  que el sistema prefirió no actuar.

## Lo que hubo que declarar además (el código lo exige, y tres guardas lo cazaron)

| Archivo | Qué |
|---|---|
| `nucleo/seguridad/idempotencia.py` | `DECISION_DESCONOCIDA = "DECISION_DE_RECLAMO_DESCONOCIDA"` |
| `nucleo/modelo/motor.py` | el código en `CODIGOS_DE_BLOQUEO` |
| `nucleo/seguimiento/forzado.py` | el código en `CODIGOS_MOTOR_GUARD` |
| `conversaciones/[id]/+page.svelte` | el motivo en palabras para la pantalla |

Las tres guardas que lo exigieron (`test_bloqueos_en_traza` ×2,
`test_escalada_forzada` ×2) **no se relajaron**: siguen comparando conjuntos
exactos. En `test_escalada_forzada` el conteo pasó de 16 a 17 códigos de gate,
declarado con su motivo — una función nueva que se agregue sin pasar por ahí
volverá a hacerlas fallar.

## Lo que NO cambió

Claves, estados, idempotencia, concurrencia, kill switch, `frontera.autonoma()`,
autorización granular, `PropuestaSupervisor`, el piloto `crear_tag_crm`, B-7,
M09, M11. **Los límites tampoco**: no hizo falta tocarlos.

---

## PRUEBAS — los 10 casos: **PASS**

Casos 1–6 en `tests/test_idempotencia_externa.py` §16 (su tema, contra la
emulación del SQL real de `db.py`). Casos 7–10 en `tests/test_autonomia2.py`,
re-ejecutados.

| # | Caso | Resultado |
|---|---|---|
| 1 | decisión válida permitida → ejecuta | `ejecutar` → 1 llamada, cerrada `exitosa` |
| 2 | decisión válida rechazada → no ejecuta | `repetida`, `en_curso`, `rechazada`, `fallida` → **0 llamadas**, cada una con su código |
| 3 | **decisión desconocida → no ejecuta** | 9 valores (`'devolver'`, `'esperar'`, `'rechazar'`, `''`, `'EJECUTAR'`, `'ejecutar '`, `None`, `0`, `True`) → **0 llamadas**, código `DECISION_DE_RECLAMO_DESCONOCIDA`, **0 transiciones inventadas** |
| 4 | misma clave → no duplica | 1 llamada |
| 5 | clave con argumentos distintos → rechaza | 1 llamada, `CLAVE_REUTILIZADA` |
| 6 | concurrencia → un solo efecto | 8 hilos → 1 llamada |
| 7 | kill switch detenido → no ejecuta | bloquea, **y con su propio motivo** |
| 8 | autorización ausente → no ejecuta | 0 llamadas |
| 9 | autonomía insuficiente → no ejecuta | techo 0 y 1 bloquean; techo 1 + autorización 4 → efectivo **1** |
| 10 | B-7 NO-GO → no ejecuta | `B7_REQUERIDO`, 0 llamadas |

Dos cosas que hacen que el verde signifique algo:

- **Se cuenta el efecto**, no la presencia del mecanismo: cuántas veces se llamó
  al proveedor.
- **Prueba de desarme**: con la *misma* tubería, `'ejecutar'` sí sale. Así el
  cero del caso 3 es la decisión desconocida y no otra cosa.

Y el caso 3 incluye `'EJECUTAR'` y `'ejecutar '` a propósito: la comprobación es
por igualdad exacta, y esos dos son los que más fácil se colarían.

### Dos casos míos fallaron primero, y por qué importa

- **Caso 5**: `clave_de()` mete el hash de los argumentos *dentro* de la clave,
  así que dos argumentos distintos dan **dos claves distintas** y el choque no
  existiría. El caso solo es posible con `clave` explícita — corregido con el
  mismo patrón que ya usaba la §4 del archivo.
- **Caso 6**: `threading.Thread` arranca con contexto vacío, así que el permiso
  de la frontera (un `ContextVar`) **no cruza al hilo**. Sin abrirlo dentro, los
  8 hilos daban 0 llamadas y el verde no habría probado nada sobre concurrencia.

---

## REGRESIÓN

### Núcleo: **86 de 88** — PASS

Los 2 que fallan son previos y ajenos: `test_p2_inerte` (guarda del scheduler)
y `test_reloj` (barridos sin datos de conexión). Ninguno menciona Autonomía 2 ni
importa los módulos tocados.

### CRM (Django), la corrida que ya estaba lanzada: **4383 pasan, 10 fallan, 64 omitidas** (15 min 20 s)

`django-crm/backend` **no importa nada de `nucleo/`** (grep completo: 0
coincidencias), así que ni este cambio ni el bloque anterior pueden alcanzarla.
Las 10, clasificadas mirando cada una:

| Cuántas | Qué | Causa |
|---|---|---|
| 7 | `test_18/19/20_concurrencia` (m03fb), `test_20_completar_y_cancelar_a_la_vez`, `test_dos_hilos_reales_compitiendo`, `test_18_ciclos_concurrentes`, `test_12_dos_asistentes_simultaneos` | concurrencia real: exigen dos conexiones PostgreSQL; la suite corre sobre **SQLite** |
| 1 | `test_6_el_lock_de_lineas_va_antes_que_el_del_plan` | «no se emitió ningún FOR UPDATE» — `select_for_update()` es **no-op en SQLite** |
| 1 | `test_la_rls_de_la_tabla_esta_puesta_y_forzada` | consulta `pg_policies`: **no existe en SQLite** |
| 1 | `test_no_documented_variable_is_read_nowhere` | deriva de documentación **previa**: la variable que reclama es `ADMIN_PASSWORD`, no ninguna de este trabajo |

Las diez son de **entorno o previas**. Ninguna es de esta corrección.

`test_m09f_gobernanza::test_no_existe_ninguna_ruta_de_ejecucion` sigue en verde.

---

## `[INCIDENTE]` Dejé un archivo ajeno en conflicto, y lo reparé

**Qué pasó.** En el bloque anterior, para comprobar si dos fallos eran previos,
ejecuté `git stash push` y `git stash pop` sobre un repositorio que tiene **dos
stashes de otro colaborador**, ambos marcados «AJENO, no tocar». El `push` no
guardó nada, pero el `pop` **sí corrió**: intentó aplicar `stash@{0}` y dejó
`tests/test_habilidades.py` en estado `UU` con **6 marcadores de conflicto**.

No lo vi en el momento porque mi comprobación encadenaba con `&&` y el fallo no
imprimía nada. Lo destapó la regresión de esta corrección, cuando
`test_habilidades` empezó a fallar con `SyntaxError: invalid syntax` en la línea
`<<<<<<< Updated upstream`.

**Qué se perdió: nada.** Git conserva el stash cuando el `pop` conflictúa —
verificado: los **2 stashes siguen ahí**, y el stash afectado contenía ese único
archivo.

**Reparación.** `git checkout HEAD -- tests/test_habilidades.py`. El archivo
quedó idéntico a HEAD (`git status` limpio, 0 marcadores) y la prueba vuelve a
pasar. Lo que el colaborador tenía guardado sigue intacto en `stash@{0}`.

**Lo que cambio.** No vuelvo a usar `git stash` en este repositorio: hay trabajo
ajeno guardado ahí y no es mío para moverlo. Para saber si un fallo es previo
hay formas que no tocan el árbol — mirar el mensaje de error y comprobar si el
archivo siquiera importa el módulo cambiado, que es lo que terminé usando y lo
que debí usar desde el principio.

---

## PRODUCCIÓN

Sin tocar, medido al cerrar:

```
asistente.nivel_autonomia            existe=False  ok
asistente.autorizacion_herramienta   existe=False  ok
asistente.ejecucion_autonoma         existe=False  ok
kill switch: Rapilink | detenido     (sin cambios)
tablas en public: 135                ok
DBUSER efectivo: postgres
```

`AUTONOMIA_2_ACTIVA` sigue ausente del `.env`: apagada.

---

## VEREDICTO: **PASS**

El fail-open está cerrado. Una decisión que el módulo no entiende ya **no
ejecuta**: rechaza con su propio código, no inventa una transición en el
registro, y el modelo lo lee como guarda del sistema y no como fallo de un
tercero. Todo lo que debía quedar igual quedó igual, y las cuatro guardas que se
interpusieron se satisficieron **declarando**, nunca relajando.

Lo único que empaña el resultado es mío y está arriba: rompí un archivo que no
era mío con un `git stash pop` que no debí ejecutar. Está reparado, nada se
perdió, y la práctica que lo causó no se repite.

---

**No se hizo commit. No se activó Autonomía 2. No se aplicaron migraciones
productivas. No se tocó M09, M11, el kill switch ni `DBUSER`.**
