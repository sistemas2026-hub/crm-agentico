# Paso a Despacho — Fase 3: pasan solas las fallas medidas, y nunca un caso cerrado

```
BASE       origin/fix/integracion-wisphub = 19256d4c, más el commit local de la
           ficha 107b7893. Se auditó sin commitear.
VEREDICTO  CERRADO EN CÓDIGO. Tres auditorías sin ningún camino por el que pase
           algo que no debería. 53 pruebas nuevas, 42 mutaciones
           muertas, regresión de 35 archivos con solo los dos rojos anteriores.
           NO verificado en producción, y con dos chequeos que hace una persona
           antes de volver a delegar la tarea (3.8).
FECHA      16/10/2026
ALCANCE    operaciones/{paso_a_despacho,supervisor,clasificacion_de_trabajo}.py,
           un módulo nuevo (operaciones/medicion_de_fallas.py), un archivo de
           pruebas nuevo y cuatro ajustados en operaciones/tests/, y
           campo/tests/test_el_supervisor_llena_la_cola.py, autorizado por el
           usuario. Nada en nucleo/, en el código de campo/, en el frontend ni
           en tenants/. Ninguna migración.
FICHA      SPEC/objetivos/supervisor-pasa-a-despacho.md, Fase 3
```

## Qué se pidió

Que pasen solas a Despacho las fallas que la medición confirma, y nunca un caso
cerrado. Lo midió la Fase 2: la regla 1 no podía dejar pasar nada (H-1 en
`PASO-A-DESPACHO.md`), y el paso aceptaba casos ya cerrados (A-1).

**Decisiones del usuario, 16/10 por la tarde:**

- Alcance: caso abierto y fallas medidas, con re-medición. Quedan fuera
  deshacer un pase, los textos de la pantalla, la privacidad del camino y la
  relectura.
- Pasa sola solo la falla con el equipo **en línea y la señal fuera de -25 a
  -8 dBm**, el rango del motor. Una caída por **LOS/LOF va a una persona**:
  desde la OLT no se distingue de un equipo desenchufado. Cambia la regla 1 del
  14/10.
- Un caso cerrado no pasa, y su propuesta **se queda con el motivo**. No se
  cancela.
- Las fallas pendientes se vuelven a medir con `diagnosticar`, con tope.
- Se enciende **en sombra**: deploy con la tarea delegada quitada, contar, y
  recién ahí delegar.
- Se edita solo el archivo de pruebas de `campo/` que fijaba la regla vieja.

## Lo que se cambió

- **`medicion_de_fallas.py`, módulo nuevo.** Mide las fallas pendientes con
  `chat_herramientas.diagnosticar_servicio`, la herramienta del motor que ya
  usa el cierre de desincronizados. Guarda la medición como pieza propia
  (`medicion_del_equipo`), con claves fijas, vocabulario cerrado y la hora en
  que se midió. Mide primero las que nunca se midieron, la más nueva primero, y
  reintenta una vez por día lo que no fue concluyente. Un caído sin causa ni
  señal, o un en línea sin nivel, no es concluyente. No gasta una consulta en
  un caso que no puede pasar. Su presupuesto nace con la hora de la fase.
- **Una fase nueva en el ciclo**, "medición de fallas", entre la lectura y el
  paso, con su línea de log.
- **`decidir` decide la falla con la medición.** Pasa solo en línea, con la
  señal débil y un nivel en dBm finito. Cada otra medición tiene su texto
  fijo, que dice qué hacer.
- **`evaluar` y `por_que_el_caso_no_puede_pasar`**: el caso es la primera
  puerta del paso y de la rama del tope. Pasa solo un caso `New`, `Assigned`
  o `Pending`, activo y sin fusionar, con una copia de WispHub en curso, fresca
  y sin error.
- **`pasar_si_corresponde` decide solo con lo guardado.** La señal que le pasa
  la fase siempre llega vacía.
- **`motivo_para_anotar` sin el bloque de la Fase 2** que reemplazaba la frase
  de equipo sano: con la medición, ese bloque tapaba los motivos medidos.
- **`revisar` acepta un nombre fijo**, como `cancelar`, y el pase automático lo
  usa: el texto que redactó el modelo no va al feed de toda la empresa.
- **La sombra**: `pasarian_por_grupo` en el reporte y en la línea de log.

## Lo medido

Todas las corridas, con `-e MOTOR_URL=http://127.0.0.1:9`: ninguna prueba
puede llegar a un motor real ni a SmartOLT, aunque le falte un stub. El
contenedor de pruebas está en la misma red que un motor con credenciales.

**Pruebas nuevas, Postgres real** (criterio 3.1):

```
$ MSYS_NO_PATHCONV=1 docker run --rm --network wt-cerebro-prod_default --env-file …/.env.docker \
    -e MOTOR_URL=http://127.0.0.1:9 -e TEST_DATABASE_URL=postgres://test:test@pg-f3:5432/test \
    -e PYTHONDONTWRITEBYTECODE=1 -v C:/wt-area/django-crm/backend:/app -w /app wt-cerebro-prod-backend \
    python -m pytest operaciones/tests/test_pasan_las_fallas_medidas_y_nunca_un_caso_cerrado.py \
    --no-cov -q -p no:cacheprovider --reuse-db
collected 53 items
============================= 53 passed in 11.78s ==============================
```

Con las cinco suites que se ajustaron, juntas: `143 passed`.

**Mutaciones** (criterio 3.2), sobre una copia del backend, restauradas, con el
worktree intacto (misma huella antes y después):

Las 42 quedaron en rojo. Corren contra el archivo nuevo, el de la Fase 2 y
`test_las_cinco_reglas.py`.

| Grupo | Mutaciones | Resultado |
|---|---|---|
| Las ocho de 3.2 | sin la comprobación de cerrado · la copia vieja cuenta como abierta · LOS pasa solo · dying-gasp pasa solo · el rango invertido · las pendientes viejas no se re-miden · la re-medición sin tope · la re-medición llama al modelo | 8 de 8 |
| Las de la Fase 2 que siguen valiendo | M1 a M4, M6 a M14, M16 | 14 de 14 |
| Revisor de PII | el pase copia el texto del modelo · el motivo del motor tal cual · el código de error tal cual · el dBm en la clave del log | 4 de 4 |
| Auditor de frontera | la rama del tope sin la puerta del caso · sin el chequeo de fusionado · rechazado o duplicado abiertos · el pase sin el número · un NaN tal cual · el motivo sin la coma | 6 de 6 |
| Auditor independiente | caído sin causa cuenta como concluyente · débil sin número se guarda como débil · un serial suelto entra al motivo · la pieza sin la fecha · una concluyente vieja se re-mide · los reintentos antes que las nunca medidas · un caso asignado no pasa · la fase ignora que corre desatendida · escribir sin volver a mirar el estado · el techo se lee por propuesta | 10 de 10 |

Una sobrevivió en la primera corrida: quitar la exigencia del número en
`decidir`. `medicion_de_fallas` ya guarda una débil sin número como
`sin_dato`, así que ningún dato real llegaba a esa guarda. Se agregó una prueba
directa sobre `decidir`, para una pieza que llegue por otro camino, y murió.

**Regresión** (criterio 3.3), 35 archivos: la lista de 2.3, las pruebas de
`diagnostico_optico` y del cierre, `test_lectura_de_ticket`, las de `campo/`
de Despacho, y todas las que recorren `correr_ciclo`, porque el ciclo ganó una
fase. Sobre el código final:

```
collected 962 items
FAILED operaciones/tests/test_m11_indicadores.py::test_19_no_hay_segunda_cola_ni_tabla_de_kpi
FAILED campo/tests/test_despacho_pantalla.py::test_j_los_de_OTRA_empresa_no_entran
====== 2 failed, 959 passed, 1 skipped, 124 warnings in 511.50s (0:08:31) ======
```

Los dos rojos son anteriores a esta fase:

- `test_19` exige el conjunto exacto de modelos de `operaciones`, y le sobra
  `TareaDelegada`, que entró el 08/10 en `07719432` sin declararse ahí. Esta
  fase no toca ningún `models.py`.
- `test_j` afirma que RLS rechaza una escritura, y el rol `test` es
  superusuario. Bajo un rol sin privilegios, sobre el código final:

```
rol: crm_t|false|false            (rolsuper, rolbypassrls)
$ … -e MOTOR_URL=http://127.0.0.1:9 -e TEST_DATABASE_URL=postgres://crm_t:t@pg-f3r3:5432/test_rls … \
    python -m pytest campo/tests/test_despacho_pantalla.py \
    operaciones/tests/test_pasan_las_fallas_medidas_y_nunca_un_caso_cerrado.py \
    operaciones/tests/test_el_paso_mira_todas_y_dice_por_que.py \
    campo/tests/test_el_supervisor_llena_la_cola.py
collected 106 items
================= 106 passed, 28 warnings in 337.25s (0:05:37) =================
```

**ruff** (criterio 3.4), cada archivo contra su versión de origin dentro del
mismo árbol:

| Archivo | origin | cambio |
|---|---|---|
| `supervisor.py` | 9 | 9 |
| `paso_a_despacho.py` | 1 | 1 |
| `clasificacion_de_trabajo.py` | 0 | 0 |
| `medicion_de_fallas.py` | no existe | 0 |
| la prueba nueva | no existe | 0 |
| `test_el_paso_mira_todas_y_dice_por_que.py` | 0 | 0 |
| `test_las_cinco_reglas.py` | 1 | 1 |
| `test_el_paso_es_su_propia_fase.py` | 1 | 1 |
| `test_el_pase_no_se_confunde_con_un_cierre.py` | 0 | 0 |
| `campo/tests/test_el_supervisor_llena_la_cola.py` | 3 | 3 |

## Agentes

- **`orquestador`**, al encuadrar: corrigió la premisa de `LOS` (el endpoint
  liviano no trae causa) y trajo la ambigüedad de LOS que registra la skill.
- **`arquitecto-dexter`**, antes de construir: la fase propia, la pieza propia
  con su contrato en `paso_a_despacho`, el presupuesto con la hora de la fase,
  el vocabulario del cierre para "cerrado", y el choque con las pruebas de
  `campo/` que decidió el usuario.
- **`revisor-de-pii`**: con un centinela en cada clave de una respuesta del
  motor, no entra ningún dato del cliente en la pieza ni en los motivos.
  Encontró el texto del modelo en `Activity` (lo abría la Fase 3 para las
  fallas), el motivo y el código sin forma cerrada, el dBm en la clave del log
  y tres mutaciones vivas. Todo cerrado.
- **`auditor-de-frontera`**: ninguna falla pasa sin `en_linea` + `debil`
  guardado, y ningún caso cerrado pasa; quitar la puerta del caso deja 8
  pruebas en rojo. Encontró los estados rechazado y duplicado, el pase sin
  número, el NaN, la coma del motivo, dos guardas sin prueba y documentación
  vieja: cerrados.
- **`auditor-independiente`**: ningún camino hace pasar algo que no debería.
  Encontró lo contrario: un 200 del proveedor sin datos guardado como "caído"
  para siempre, el NaN con un texto contradictorio, la medición sin fecha en
  el panel, un serial que el filtro del motivo dejaba pasar, y seis
  propiedades declaradas que ninguna prueba mataba. Cerrados. Mostró también
  que el número para terminar la sombra es `concluyentes` y no `medidas`: la
  ficha (3.8) lo corrige.

## Hallazgos anotados, con su motivo

| # | Hallazgo | Gravedad | Por qué no en esta fase |
|---|---|---|---|
| F3-1 | **La sombra no está en el código.** Lo único que frena la regla 1 nueva en su primera activación es quitar la tarea `pasar_a_despacho_segun_las_reglas` **antes** del push | media | El usuario eligió ese mecanismo. Se cierra por procedimiento: el push espera la confirmación de que la tarea se quitó. Alternativa en código: una tarea delegada propia para la regla 1 |
| F3-2 | **La medición no está atada a la empresa**: `diagnosticar_servicio` usa `MOTOR_TENANT`, no la `org` | media (latente) | Es D5, igual que el cierre y el interruptor. Antes de sumar un segundo ISP |
| F3-3 | **El filtro `id_servicio` de WispHub no está verificado como exacto**, y el motor toma el primer resultado sin comprobarlo. Un filtro parcial mediría la ONU de otro cliente, y desde esta fase eso decide un pase | media (sin medir) | Medirlo es llamar a WispHub, que el `/goal` no permite. Es un chequeo de 3.8, antes de volver a delegar |
| F3-4 | **La lista blanca de la base** no está medida para `senal` y `senal_dbm` de `diagnosticar_servicio` en el rol `supervisor_noc`. Si faltaran, la única rama que pasa quedaría muerta en silencio | media (sin medir) | Es un chequeo de 3.8: ver dBm en las piezas de la sombra |
| F3-5 | **Las reglas 2 y 3 dejan pasar sin medición** una falla que el modelo clasifique como trabajo pedido u obra de red con confianza alta | media-baja | Por diseño desde el 14/10. `pasarian_por_grupo` sirve para vigilarlo |
| F3-6 | **Una medición concluyente no se renueva** en los siete días: una falla intermitente medida en rango el día 0 no pasa el día 6 aunque empeore. Y al volver a delegar, la primera vuelta decide con mediciones de toda la sombra | media-baja | Re-medir cada día también lo concluyente cambia el criterio 3.1(c). Lo decide el usuario; la recomendación es re-medir al día, unas 40 consultas diarias |
| F3-7 | **El tope de 60 no acota la primera activación**: había unas 40 fallas pendientes | baja | Si se quiere un techo real, un tope propio para las fallas. Lo decide el usuario |
| F3-8 | **Llamadas a SmartOLT**: hasta 30 `get_onu_full_status_info` por vuelta entre el cierre y la medición, más 30 por cada vuelta del botón, que puede solaparse | baja | Cada una corresponde a un ticket reportado, como pide el proveedor |
| F3-9 | **La escritura sin bloqueo de la lectura** (A-10 de la Fase 2) puede borrar la medición de una propuesta, y si ya pasó, no se vuelve a medir. El motivo con el dBm queda en `resultado` | baja | Anterior a esta fase |
| F3-10 | **El filtro del motivo deja pasar un nombre** en una frase común. Hoy los motivos del motor son textos fijos | baja | No hay forma de reconocer un nombre; el serial sí se frena |
| F3-11 | El interruptor se lee una vez por vuelta; la puerta del caso, milisegundos antes de `revisar` | baja | Anterior a esta fase |

## Límites declarados

- **Producción no se midió.** El control 3.8 de la ficha lo hace una persona:
  quitar la tarea antes del push, leer `concluyentes` en la línea `medicion de
  fallas`, ver dBm en las piezas, confirmar el filtro de WispHub, y leer
  `pasarian por grupo=` antes de volver a delegar.
- **La pantalla de Despacho sigue diciendo "equipo en línea y sano"** en la
  sugerencia de labor, porque recibe el equipo liviano (H-1 en los otros
  llamadores de `clasificar`). Quedó para otra fase.
- **La hora de la medición va en UTC**, con su etiqueta: mostrarla en la hora
  de cada empresa es trabajo del panel.
- **Los contadores del log no tienen prueba**, por la restricción del `/goal`
  de no afirmar sobre contadores. Lo que se prueba es el efecto: la pieza y el
  motivo.
