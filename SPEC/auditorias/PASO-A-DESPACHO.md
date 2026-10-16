# Paso a Despacho — Fase 2: mira todas y dice por qué

```
BASE       origin/fix/integracion-wisphub = 8fe34f0e, más los commits locales
           de la ficha (68804255, 634e4bfb). Se auditó sin commitear.
VEREDICTO  CERRADO EN CÓDIGO. Lo nuevo queda sin hallazgos abiertos: 23
           pruebas en Postgres real y 16 mutaciones muertas. Lo ya desplegado
           deja uno que cambia lo que se esperaba del paso: hoy ninguna falla
           de servicio puede pasar sola (H-1).
FECHA      16/10/2026
ALCANCE    operaciones/{supervisor,paso_a_despacho,clasificacion_de_trabajo}.py
           y una prueba nueva. Nada en nucleo/, nada en el frontend, ninguna
           migración. Auditado también lo ya desplegado del paso:
           b3e4abf2…e0663595.
FICHA      SPEC/objetivos/supervisor-pasa-a-despacho.md, Fase 2
```

## Qué se pidió, y qué midió producción antes de tocar nada

El pedido del usuario —"que el Supervisor revise los pendientes y apruebe para
pasar a Despacho según las reglas, solo, sin botón"— **ya estaba cumplido**: el
16/10 una persona midió en producción las tres tareas delegadas, el techo en 3
y el ciclo de las :07 corriendo solo. Pasó 0 de 65. Con las reglas parecía la
respuesta correcta: 33 fallas que la lectura marcaba "con el equipo sano", y la
decisión del usuario fue que esas siguen a una persona. Esa misma tarde se
midió que la etiqueta no sale de una medición (H-1). La medición de la mañana
encontró dos defectos, que son esta fase:

1. **El tope tapaba las nuevas.** La fase miraba las 60 más viejas y había 65.
2. **El motivo no quedaba escrito.** Solo salía sumado en el log del worker.

## Lo que se cambió

- `_pasar_a_despacho_los_que_las_reglas_habiliten` mira **todas** las lecturas
  pendientes. `TOPE_PASO_A_DESPACHO` acota cuántas **pasan** por vuelta; las que
  califican después del tope esperan la siguiente sin escribir nada.
- `paso_a_despacho.anotar_por_que_se_queda` escribe en la propuesta, como pieza
  de evidencia con fuente propia, por qué se queda y desde cuándo. Reemplaza la
  anterior (patrón de `diagnostico_optico.anotar_el_cierre`), solo si cambió,
  con la fila bloqueada y el estado vuelto a mirar. Cuando la propuesta pasa,
  `quitar_por_que_se_quedaba` la saca.
- `pasar_si_corresponde` devuelve además qué puerta frenó el paso. Con eso, una
  puerta de la empresa escribe texto fijo y no el motivo libre del interruptor,
  ni en la propuesta ni en el log.
- El motivo es texto fijo en todos los casos:
  - el `porque` de las reglas;
  - para una falla que no se pudo medir, además por qué (`onu_no_vinculada`, la
    ficha que no llegó);
  - para una falla cuya lectura dijo "equipo sano", un texto que dice la verdad
    de hoy: SmartOLT contestó y la lectura no sabe interpretarlo (H-1);
  - para una propuesta que todavía no se leyó, que falta la lectura.
- `decidir` no se tocó. `clasificacion_de_trabajo.EQUIPO_SANO` le da nombre al
  comienzo de la frase de equipo sano, con el mismo texto.

## H-1 · Hoy ninguna falla de servicio puede pasar sola

Lo encontró `revisor-de-pii` y se verificó por efecto, con el clasificador real
y la forma de equipo que manda el motor (la de `campo/tests/test_despacho_api.py`):

```
motor: onu_status=LOS                      verificada=False  el equipo esta en linea y sano, asi que esto NO es una falla d
motor: onu_status=Power fail               verificada=False  el equipo esta en linea y sano, asi que esto NO es una falla d
motor: Online, -20.81 dBm                  verificada=False  el equipo esta en linea y sano, asi que esto NO es una falla d
clasificador: estado=caido, causa=fibra    verificada=True   el equipo esta caido por perdida de señal optica (LOS/LOF): la
```

**El mecanismo.** `clasificacion_de_trabajo._de_la_prueba` lee `estado`,
`senal` y `causa_caida`. El motor arma el equipo con `_CAMPOS_DE_EQUIPO`
(`nucleo/canales/api.py:5910`): `onu_status`, `onu_signal*` y topología.
`campo/services/despacho.py::contexto_del_caso` lo pasa sin traducir. Ninguna
clave coincide, así que `_de_la_prueba` devuelve `None` con cualquier equipo, y
`clasificar` cae en "el equipo está en línea y sano" con solo que SmartOLT haya
contestado algo. Viene de `ac6180d4` (09/10); las pruebas del clasificador usan
su propia forma, no la del motor.

**Lo que significa:**

- La regla 1 no puede dejar pasar nada: ninguna lectura sale verificada.
- Los "33 con el equipo sano" del 16/10 cuentan "SmartOLT contestó algo". La
  decisión del usuario sigue en pie para un equipo sano de verdad; lo que cae
  es el número.
- Lo único que hoy puede pasar solo es un trabajo pedido o una obra de red con
  confianza alta.

**Lo que se hizo acá.** El motivo ya no copia la frase de equipo sano, y
tampoco deja solo el `porque` de las reglas, que dice "puede estar sano, o no
se pudo medir": con una fibra cortada las dos cosas son falsas y el texto
empujaba a llamar al cliente (lo midió `auditor-independiente`). Queda escrito
que SmartOLT contestó, que no se sabe si el equipo está sano o caído, y que
falta mirarlo en SmartOLT. El panel lo pone en "Información que falta". La
prueba `test_k` avisa el día que el clasificador entienda al motor, porque
desde ese día esta excepción sobra.

**Lo que queda:** que el clasificador lea las claves del motor. Eso hace que
las fallas con `LOS` pasen solas, así que va después de A-1 y lo decide el
usuario. Es la Fase 3 de la ficha.

## Lo medido

**Pruebas nuevas, Postgres real** (`test_el_paso_mira_todas_y_dice_por_que.py`):

```
$ MSYS_NO_PATHCONV=1 docker run --rm --network wt-cerebro-prod_default --env-file …/.env.docker \
    -e TEST_DATABASE_URL=postgres://test:test@pg-paso:5432/test -v C:/wt-area/django-crm/backend:/app \
    -w /app wt-cerebro-prod-backend python -m pytest \
    operaciones/tests/test_el_paso_mira_todas_y_dice_por_que.py --no-cov -q -p no:cacheprovider --reuse-db
collected 23 items
======================== 23 passed, 1 warning in 13.74s ========================
```

**Mutaciones**, sobre una copia del backend, restauradas. La huella de los
cuatro archivos del worktree fue la misma antes y después (`6d69db4cf47dc26f`).

| Mutación | En rojo |
|---|---|
| M1 · evaluar solo las del tope más viejas | 3 (`test_a` x2, `test_b`) |
| M2 · quitar el tope de pases | 1 (`test_b`) |
| M3 · no escribir el motivo | 14 |
| M4 · escribirlo siempre | 1 (`test_d`) |
| M5 · copiar la frase de equipo sano al motivo | 2 (`test_c`, `test_f`) |
| M6 · el log con el `porque` crudo de la puerta | 1 (`test_g`) |
| M7 · anotar sin la red del try | 1 (`test_h`) |
| M8 · el motivo con la fila recargada y no la que decidió | 1 (`test_j`) |
| M9 · no quitar el motivo al pasar | 1 (`test_i`) |
| M10 · quitar reescribe la evidencia desde la copia vieja | 1 (`test_l`) |
| M11 · quitar fuera del try | 1 (`test_h`) |
| M12 · un pase que no se pudo registrar se anota como que se queda | 1 (`test_m`) |
| M13 · pasado el tope, la que no califica tampoco se anota | 1 (`test_b`) |
| M14 · quitar borra toda la evidencia menos la primera pieza | 1 (`test_l`) |
| M15 · a la fibra sin interpretar, el `porque` de las reglas | 2 (`test_c`, `test_f`) |
| M16 · a la que nunca se leyó, el texto de una lectura guardada | 1 (`test_n`) |

M1 a M4 son las del criterio 2.2. M10 a M14 son las cinco que el auditor
independiente encontró vivas con la suite anterior.

**Regresión de la zona**, la lista del criterio 2.3 más
`test_clasificacion_de_trabajo.py`, con el rol `test` de la receta:

```
collected 202 items
FAILED campo/tests/test_despacho_pantalla.py::test_j_los_de_OTRA_empresa_no_entran
================= 1 failed, 201 passed, 32 warnings in 53.67s ==================
```

`test_j` afirma que el RLS rechaza una escritura, y el rol `test` es
superusuario (`rolsuper = t`); falla igual sobre el código de origin. Bajo un
rol sin privilegios, en un Postgres aparte y sobre el código final:

```
rol: crm_t|false|false            (rolsuper, rolbypassrls)
$ … -e TEST_DATABASE_URL=postgres://crm_t:t@pg-paso-rls3:5432/test … python -m pytest \
    campo/tests/test_despacho_pantalla.py operaciones/tests/test_el_paso_mira_todas_y_dice_por_que.py
collected 44 items
================= 44 passed, 21 warnings in 276.85s (0:04:36) ==================
```

**ruff**, cada archivo contra su versión de origin dentro del mismo árbol:

| Archivo | origin | cambio |
|---|---|---|
| `supervisor.py` | 9 | 9 |
| `paso_a_despacho.py` | 1 | 1 (el mismo `I001`) |
| `clasificacion_de_trabajo.py` | 0 | 0 |
| la prueba nueva | no existe | 0 |

**Alcance del diff.** Contra `634e4bfb` (el último commit de la ficha) solo
cambian los cuatro archivos de `operaciones/`, esta nota, el índice y la ficha.
Contra origin aparecen además dos documentos del objetivo anterior,
commiteados en `a0af16a0` y todavía sin push.

## Hallazgos de las auditorías

### Cerrados en este cambio

| Hallazgo | Lo encontró | Cómo se cerró | La prueba |
|---|---|---|---|
| El motivo copiaba "el equipo está en línea y sano", que no sale de medir | `revisor-de-pii` | `motivo_para_anotar` no la copia | `test_f` (M5) |
| Sin esa frase, a una fibra cortada le quedaba "puede estar sano, o no se pudo medir", falso las dos veces, y el panel lo mostraba como hecho | `auditor-independiente` | `_FALLA_SIN_INTERPRETAR`, que el panel pone en "Información que falta" | `test_f` (M15), `test_k` |
| A una propuesta sin leer se le escribía que "la lectura guardada no trae el grupo" | `auditor-independiente` | `_SIN_LECTURA` | `test_n` (M16) |
| El log de la fase y el resultado de la tarea en Celery llevaban el motivo libre del interruptor | `revisor-de-pii` | `motivo_para_el_registro`: texto fijo para la puerta de la empresa | `test_g` (M6) |
| Una falla al anotar o al quitar cortaba la vuelta, y las más nuevas quedaban sin mirar | los tres | try alrededor de anotar y quitar; `anotaciones fallidas` en la línea de log | `test_h` (M7, M11) |
| El motivo podía mezclar la lectura que decidió con una que llegó después | `revisor-de-pii`, `auditor-de-frontera` | el motivo sale de la copia que decidió; la evidencia, de la fila bloqueada | `test_j` (M8) |
| Una ACEPTADA seguía diciendo "se queda para una persona" | `auditor-de-frontera` | `quitar_por_que_se_quedaba` cuando pasa | `test_i` (M9) |
| Nada exigía que quitar el motivo dejara intacto el resto de la evidencia; sin la lectura, Despacho muestra una hipótesis vacía | `auditor-independiente` | prueba sobre la evidencia completa, con una lectura que llega después de cargar la copia | `test_l` (M10, M14) |
| Un pase que no se pudo registrar no tenía guarda contra anotarse como "se queda" | `auditor-independiente` | prueba con `revisar` fallando | `test_m` (M12) |
| La rama del tope nunca corría con una propuesta que no califica | `auditor-independiente` | `test_b` suma una que no califica, después del tope | `test_b` (M13) |
| Las pruebas de ausencia miraban solo `dato` y `porque`, sin centinela en lo que escribe el modelo | `revisor-de-pii` | centinelas en la acción, el motivo y la lectura; ausencia sobre la pieza entera | `test_c`, `test_f`, `test_g`, `test_g2` |
| `test_a` probaba solo una falla confirmada, que hoy no se produce | `revisor-de-pii` | `test_a` también con trabajo pedido de confianza alta | `test_a` (M1) |
| El control de producción (`miradas=` igual al total) se calcula antes del bucle y no ve si el bucle dejó de evaluar | `auditor-independiente` | el control 2.8 de la ficha pasa a ser `miradas = pasaron + esperan el tope + se quedaron + fallaron` | (control de una persona) |

### Anotados, con su motivo

| # | Hallazgo | Dónde | Gravedad | Por qué no en esta fase |
|---|---|---|---|---|
| A-1 | **El paso no mira si el caso sigue abierto.** Acepta un ticket cerrado en WispHub o un caso cerrado en Dexter, y lo deja en la cola hasta que Dexter lo cierra. El auditor lo midió con una prueba propia | `pasar_si_corresponde`; la cola excluye solo `status="Closed"` (`campo/despacho_pantalla_views.py:221`) | media-alta | Desplegado, y es una condición nueva. Va primero en la Fase 3, antes de arreglar H-1 |
| A-2 | **Una ACEPTADA no puede salir de la cola.** `revisar` y `cancelar` contestan 409, la pantalla no tiene la acción, y el admin borra sin rastro | `operaciones/views.py:311-322`, `:411-413`; `operaciones/admin.py:23` | media | Desplegado. El nivel 3 se justificó con un "se saca" que no existe |
| A-3 | **La pantalla dice que todo lo aprobó una persona:** "Nada sale a campo sin pasar por ahí" y "Confirmación humana: Obligatoria"; varios docstrings dicen "NO EJECUTA NADA" | `supervisor-noc/despacho/+page.svelte:297`; `supervisor-noc/+page.svelte:2535`; `campo/despacho_pantalla_views.py:144-199` | media | Frontend, fuera de esta fase |
| A-4 | **La aceptación automática copia el texto del modelo** (`accion_propuesta`) a `Activity.entity_name`, que ve cualquier usuario autenticado en `/api/activities/` | `supervisor.py::revisar`; `common/views/dashboard_views.py` | media | Desplegado y compartido con la aceptación humana. Arreglo: un nombre fijo, como ya hace `cancelar` |
| A-5 | **La ruta interna del motor no redacta texto libre:** aplica la lista blanca, pero `consultar_ticket` le devuelve al modelo la descripción y el asunto crudos | `nucleo/canales/api.py:4500-4505` | alta (mecanismo confirmado, frecuencia sin medir) | `nucleo/` está fuera de esta fase |
| A-6 | **`tapar` es una copia parcial de `redaccion.py`:** coordenadas de hasta 5 decimales y URLs llegan al modelo | `operaciones/lectura_de_ticket.py:52-64` | media | También lo usa la pantalla de Despacho; los patrones extra van solo en la entrada del modelo |
| A-7 | **`nombre` está en la lista blanca de `supervisor_noc`:** el modelo puede pedir el nombre del cliente, contra lo que dicen dos docstrings | `tenants/rapilink.config.yaml:1922` (semilla; producción sin medir) | media | Escribir `tenant_config` está fuera de esta fase |
| A-8 | **La relectura todavía corta en las 60 más viejas.** Una propuesta nueva cuya lectura vino sin grupo no se relee mientras haya más de 60 pendientes, y sin grupo nunca pasa. Es la forma del defecto que cierra esta fase, una fase antes | `supervisor.py::_las_que_esperan_relectura` (`TOPE_RELECTURA_SIN_SENAL`) | media (mecanismo verificado; la tasa de grupo vacío, sin medir) | La relectura llama al modelo y su tope acota ese costo: cambiar el orden es otra decisión |
| A-9 | **Vueltas solapadas pueden pasar dos topes en la misma hora**, y una propuesta que otra vuelta ya decidió se cuenta como "se quedaron" | el bloqueo de la organización cubre solo `_correr_ciclo` | baja | El tope es por vuelta, por decisión de la ficha |
| A-10 | **`guardar_en_propuesta` escribe la lectura sin bloqueo** y sin mirar el estado: puede borrar o devolver la pieza del motivo, y reescribir una propuesta ya aceptada | `operaciones/diagnostico_de_ticket.py:621-664` | baja | Anterior a este cambio; dicho en el docstring de `anotar_por_que_se_queda` |
| A-11 | **Quitar el motivo no se reintenta.** Si falla, o si A-10 le devuelve la pieza a una ya aceptada, la aceptada sigue diciendo "se queda para una persona": ninguna vuelta vuelve a mirarla | `quitar_por_que_se_quedaba` | baja | Exige un error de base justo ahí, o ciclos solapados. Arreglo posible: barrer en cada vuelta las aceptadas sin firma que conserven la pieza |
| A-12 | **La que espera el tope conserva su motivo anterior**, aunque ya no sea cierto | la rama del tope en `_pasar_a_despacho_los_que_las_reglas_habiliten` | baja | Se corrige en la vuelta siguiente, y exige más de 60 que califiquen en una vuelta |
| A-13 | **"Solo cuando cambia" compara texto.** Un retoque de redacción en `decidir`, en las puertas o en el clasificador reescribe todas las pendientes y reinicia el "desde cuándo" | `anotar_por_que_se_queda` | baja (plausible) | Comparar un veredicto estructurado en vez del texto es otro diseño |
| A-14 | **El paso no vuelve a mirar el área del caso:** depende de que el retiro haya corrido antes en la misma vuelta | `retirar_propuestas_fuera_de_area` | baja | Del objetivo anterior |
| A-15 | El interruptor se lee con `MOTOR_TENANT` y no con la organización; "solo TICKET_SIN_DIAGNOSTICO" lo garantiza la consulta del llamador, no `pasar_si_corresponde` | `operaciones/autonomia.py:105-159` | informativo | Multi-empresa, anterior |

## Agentes

- **`arquitecto-dexter`**, antes de cerrar el diseño: pieza de evidencia y no
  campo con migración, porque el detalle ya la devuelve y el panel la dibuja;
  reemplazar y no apilar; la escritura en el módulo de dominio. Encontró tres
  cosas que se cerraron: las 40 fallas tenían el mismo texto genérico, una
  puerta cerrada copiaba el motivo libre del interruptor, y un comentario del
  tope quedaba falso.
- **`auditor-de-frontera`**, sobre todo el camino: confirmó que el tope acota
  una vuelta, que la puerta 3 falla cerrada, que el modelo no puede abrir la
  puerta 2 y que el efecto es una sola fila sin llamadas externas. Midió A-1
  con una prueba propia: un caso cerrado en WispHub y otro cerrado en Dexter
  pasaron los dos.
- **`revisor-de-pii`**: el motivo nuevo no lleva datos del cliente, no va al
  modelo ni a terceros, y solo lo devuelve un detalle que exige jefe de
  operaciones. Corrió dos guardas del motor en verde. Encontró H-1.
- **`auditor-independiente`**, sobre el código ya corregido: confirmó que corre
  en la topología real (beat de las :07 y el botón llegan a la fase con el
  contexto RLS puesto), que no hace falta aplicar nada a la base, y que la
  pieza nueva no altera a ninguna función que lea la evidencia. Encontró el
  texto falso para la fibra cortada, el de la propuesta sin leer, cinco
  mutaciones vivas, el control de producción que no ve el bucle, A-8, A-11,
  A-12 y A-13. Leyó una versión anterior de esta nota; lo que señaló de ella
  ya no aplica.

## Límites declarados

- **Carrera con la lectura (A-10).** Si dos ciclos se solapan —basta el botón
  durante los ~19 minutos de la fase de lectura—, la pieza del motivo puede
  borrarse o volver a la anterior. Si la propuesta sigue pendiente, se repara
  sola en la vuelta siguiente, pero el "desde cuándo" empieza de nuevo. Si ya
  pasó, la pieza vieja se queda (A-11).
- **Dónde se ve en el panel.** El motivo aparece en el detalle de la propuesta,
  sin la hora. Va a "Hechos observados", salvo que el texto contenga "falta" o
  "no se pudo": entonces va a "Información que falta", que es donde caen la
  fibra sin interpretar, la propuesta sin leer y `onu_no_vinculada`. La hora
  está en la tabla plegada del análisis técnico. En la bandeja no se ve.
  Mejorarlo es tocar el frontend, que esta fase no toca.
- **Producción no se midió.** El control 2.8 de la ficha lo hace una persona
  después del deploy.
