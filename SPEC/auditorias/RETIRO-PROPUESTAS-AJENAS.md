# Retiro de propuestas ajenas — las auditorías del bloque

```
BASE       origin/fix/integracion-wisphub = 1482523d, más c0954bec (la ficha)
           y el cambio en django-crm/backend/operaciones/, auditado SIN commitear
VEREDICTO  CERRADO EN CÓDIGO. Verde en Postgres real; siete mutaciones muertas.
           NO verificado en producción: el worker tiene que recibir el mapa
           de áreas del motor, y eso solo se mide después del deploy.
FECHA      16/10/2026
ALCANCE    operaciones/{areas_del_tenant,supervisor,tasks}.py, el comando
           propuestas_fuera_de_area y sus pruebas. Nada en nucleo/, nada en
           el frontend, ninguna migración, ninguna variable nueva.
FICHA      SPEC/objetivos/supervisor-retira-propuestas-ajenas.md
```

## Qué pedía la ficha

Que la pestaña Pendientes de `/supervisor-noc` quede solo con tickets de
`soporte_tecnico` y `operativo` (salvo las propuestas de cierre, por decisión
del usuario), que las propuestas viejas sobre otras áreas se cancelen solas
con motivo, y que las señales de ruido no vuelvan a proponer un ticket ajeno.

## Lo medido

**Criterio 1 — pruebas sobre Postgres real** (`scratchpad/evidencia_pytest_final.txt`,
una sola sesión, la línea de comando con `TEST_DATABASE_URL` pegada):

```
python -m pytest operaciones/tests/test_el_supervisor_retira_lo_ajeno.py
  operaciones/tests/test_el_supervisor_lee_su_area_y_no_la_ajena.py --no-cov -v
======================== 37 passed in 290.19s (0:04:50) ========================
```

(28 pruebas nuevas más las 9 del archivo hermano; corrida final sobre el
código definitivo, después de las tres auditorías.)

**Criterio 2 — mutaciones**, cada una sobre una copia del código definitivo,
restaurada después (el worktree nunca se tocó: `grep -c MUTACION` = 0):

| Mutación | Pruebas en rojo |
|---|---|
| M1 · quitar el fail-closed del mapa vacío en el retiro | 1 (`test_g`) |
| M2 · retirar también `ACEPTADA` (sin filtro de estado y `cancelar` sin su guarda) | 3 (`test_h` ×3) |
| M3 · quitar el filtro de área de `_casos_abiertos_antiguos` | 2 (`test_j1`, `test_j1b`) |
| M4 · `EXPIRADA` en vez de `CANCELADA` | 6 |
| M5 · retirar también las propuestas de cierre | 2 (`test_k2`, `test_l4`) |
| M6 · el título de la auditoría vuelve a ser la acción propuesta | 1 (`test_a`) |
| M7 · el área escrita se compara exacta otra vez (grafía distinta = ajena) | 4 (`test_n` ×4) |

M2 a medias —solo sin el filtro de estado— **sobrevive**: la guarda de
`cancelar` (`YaRevisada`) la tapa. Son dos defensas, y la mutación tiene que
quitar las dos para que se vea; quedó escrito así.

**Criterio 3 — ruff**: los archivos nuevos (`management/`, la prueba nueva)
pasan `ruff check` y `ruff format --check`; `areas_del_tenant.py` pasa `check`
y **no** `format --check` (ya fallaba en origin: deuda heredada, no
introducida). `supervisor.py`, `views.py` y `tasks.py` conservan los avisos que
ya tenían en la base (`I001`, `F541`, `E402`). El auditor independiente
encontró **un** `I001` nuevo (el import de `areas_del_tenant` separado del
bloque en `_casos_que_necesitan_visita`); corregido. `ruff check operaciones/`
entero tiene 218 avisos y `format --check` reformatearía 155 archivos: el
criterio 3 tal como estaba escrito era inalcanzable sin tocar ~150 archivos
ajenos, y se midió como "el cambio no agrega avisos". El workflow con ruff
vive en `django-crm/.github/workflows/tests.yml`, fuera del `.github/` de la
raíz: GitHub no lo ejecuta.

**Criterio 4 — alcance del diff**: 10 rutas, todas bajo
`django-crm/backend/operaciones/` más la ficha y esta nota.

## Hallazgos de los agentes, y qué se hizo con cada uno

**`arquitecto-dexter`** — confirmó dónde vive cada pieza (criterio en
`areas_del_tenant.py`, retiro junto a `expirar_vencidas`, comando por `--org`
UUID como `seed_campo_demo`) y advirtió que un fail-closed en las dos señales
de ruido rompería 14 archivos de pruebas que siembran casos sin área, sin
asignado y sin mapa. Se siguió.

**`auditor-de-frontera`** (siete pruebas propias contra Postgres real, 37 en
verde):

| # | Hallazgo | Qué se hizo |
|---|---|---|
| H1 | Con el motor caído una vuelta, un caso sin área de alguien de cartera se re-proponía y se cancelaba a la vuelta siguiente, **caso por caso**, con cota del orden de los ~500 tickets de cartera importados antes del campo | Cerrado: sin mapa, las señales de ruido no proponen lo que solo el mapa puede decidir (`indecidible_sin_mapa` en `sin_ajenos`). `test_j1b` lo fija |
| H2 | El mapa se pedía 10 veces por ciclo, 4 dentro de la transacción con la organización bloqueada; con el motor sin contestar, hasta 50 s por ciclo y lecturas distintas en la misma vuelta | Cerrado: caché negativa de 60 s (`SEGUNDOS_SIN_RESPUESTA`) |
| H3 | El mapa es del `MOTOR_TENANT` del proceso y `AREAS_DEL_SUPERVISOR` es constante: con una segunda empresa cuya área de soporte se llame distinto, el retiro cancelaría cada hora sus propuestas con área escrita | **Deuda anotada en la ficha**, no resuelta: es D5 de CLAUDE.md §13, y la ficha prohíbe tocar la constante |
| H4 | `fuera de área: 0` no significa "Pendientes solo soporte": las propuestas de cierre sobre cartera se quedan | Cerrado: el comando imprime `pendientes de cierre sobre otras áreas: N`; `test_l4` |
| H5 | Un mapa con forma inesperada levantaba dentro del lock y deshacía la vuelta entera | Cerrado: `_solo_texto` valida `{str: str}` y descarta el resto |

Y lo verificado bien: solo `PROPUESTA` + origen `case` + tres tipos; fail-closed
parcial y total; ningún receiver ni efecto más allá del estado y la fila de
auditoría; el comando respeta el tenant; retiro antes de `detectar` y dentro
del `atomic` del ciclo.

**`revisor-de-pii`** (lectura; su contenedor de pruebas fue denegado por
permisos y no lo rodeó):

| # | Hallazgo | Qué se hizo |
|---|---|---|
| H1 | `cancelar` escribía `entity_name = accion_propuesta`, que para la lectura con diagnóstico es texto del modelo leyendo el ticket; cada cancelación lo repetía en el feed | Cerrado: `cancelar` acepta `nombre` y el retiro pasa un título fijo. `test_a` afirma `entity_name == FUERA_DE_AREA`; M6 lo mide |
| H2 | `test_a` y `test_l` no sembraban `external_client_name` ni afirmaban sobre la descripción, el correo ni el id de perfil | Cerrado: las semillas traen cliente, teléfono en la descripción y nombres distintivos; `_sin_datos_de_nadie` afirma ausencia de todos sobre la fila entera y sobre la salida del comando |

**`guardia-de-release`**: sin migración, sin variable nueva, `core.hooksPath`
puesto, origin sin avanzar, sin artefactos. Dos cosas que hay que saber: el
`pre-commit` no tiene reglas para `django-crm/` y el workflow de CI filtra por
`paths` que no incluyen `django-crm/backend/`, así que **nada automático ve
este push**; y el sello `/_app/version.json` no sirve para este deploy (no
toca el frontend). La evidencia post-deploy está en la ficha, criterio 7.

**`auditor-independiente`**: ver la sección siguiente.

## Pasada adversarial (auditor-independiente)

Corrió bajo un rol **no superusuario** con `FORCE ROW LEVEL SECURITY` (el rol
`test` de la receta es superusuario y RLS queda inerte): 31 en verde ahí
también. Ocho hallazgos:

| # | Hallazgo | Qué se hizo |
|---|---|---|
| H1 | El área escrita se comparaba exacta: `Soporte_Tecnico`, `soporte_tecnico ` o `SOPORTE_TECNICO` eran "ajenas" y se cancelaban cada hora (medido con 4 grafías) | Cerrado: comparación sin mayúsculas ni espacios alrededor (`iregex`); `test_n` ×4 y mutación M7. Normalizar al escribir sigue siendo deuda de la importación |
| H2 | Un caso sin área asignado a alguien fuera del mapa no es propio ni ajeno: se sigue proponiendo y `fuera de área: 0` no lo cuenta | Cerrado en el comando: `pendientes sobre casos cuya área no se sabe: N` (`test_l5`); la ficha lo dice en "Qué significa terminado". Las señales no lo excluyen: no se adivina |
| H3 | Una lectura con diagnóstico cancelada por área no vuelve a proponerse aunque el caso reciba área propia: `ya_leidos` no mira el estado | **Decisión abierta** para el dueño; docstring y ficha corregidos para no afirmar lo contrario |
| H4 | `test_l` quedaba verde si el comando no fijaba `app.current_org` (el fixture deja el contexto puesto) | Cerrado: `test_l6` limpia el contexto antes de llamar. Solo ve algo bajo un rol no superusuario |
| H5 | Un `I001` nuevo en `supervisor.py`; dos afirmaciones falsas de esta nota sobre ruff | Cerrado: import movido al bloque; nota corregida (arriba) |
| H6 | El orden "antes de detectar" no tiene guarda: moverlo al final deja `test_i` verde | Se deja: lo que impide re-proponer es el filtro de las señales, no el orden; el orden solo decide cuándo el panel se ve limpio |
| H7 | Casos borrados o fusionados con propuesta pendiente se cancelan "por área" | Se deja: el efecto (sacarlos de Pendientes) es el correcto; el motivo escrito es impreciso |
| H8 | Comentarios viejos: cabecera de `areas_del_tenant.py`, docstring de `_tickets_abiertos_con_tecnico`, la condición del log "sin responsables", `CicloSupervisorView` ("no como trabajo del scheduler"), el docstring del retiro sin el filtro por tipo | Cerrados los cinco. `nucleo/config/schema.py::DestinoTicket` sigue diciendo que `Case` no tiene columna de área: fuera de alcance, ya anotado |

También verificó: la topología real (celery-beat `:07` → `ciclo_del_supervisor`
→ `correr_ciclo` → `_correr_ciclo` → retiro; botón → `ciclo_a_pedido` → mismo
camino); que `test_i` sí atrapa "cancelar todo"; que el comando dos veces
seguidas retira 1 y luego 0 con una sola fila de auditoría; que un `origen_id`
que no es UUID no se cancela ni se cuenta como ajeno; y que `responsables_de`
quedó sin llamador en código de producción (lo usan las pruebas).

## Lo que queda

- **Producción**: que el worker de Celery reciba el mapa (`MOTOR_*` están
  declaradas en `docker-compose.prod.yml` para `celery-worker`; el valor no se
  ve desde acá). Si no lo recibe, el retiro no retira nada y el síntoma es
  idéntico a "no hay ajenos": la línea `sin mapa de areas, no se retira
  ninguna propuesta esta vuelta` en el log del worker lo dice.
- **H3** (multi-tenant), como deuda.
- Las propuestas de cierre sobre otras áreas siguen en Pendientes por
  decisión: el comando las cuenta aparte.
