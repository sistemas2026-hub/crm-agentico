# Paso a Despacho — Fase 4: pasa salvo que la medición lo contradiga

```
BASE       origin/fix/integracion-wisphub = bd8def5c (la Fase 3 y el informe
           de pendientes ya desplegados). Se auditó sin commitear.
VEREDICTO  CERRADO EN CÓDIGO. Las reglas que el usuario decidió el 16/10,
           más los arreglos de dos auditorías. Dos hallazgos quedan para el
           usuario (no se pudo medir por falla de la cadena; Despacho sin
           el porqué del pase). Medido en producción el 17/10 a las 00:07: pasaron 15.
FECHA      16/10/2026
ALCANCE    operaciones/{paso_a_despacho,medicion_de_fallas,cerebro,
           diagnostico_de_ticket}.py, el comando informe_de_pendientes y sus
           pruebas. Nada en nucleo/, en campo/, en el frontend ni en tenants/.
           Ninguna migración.
FICHA      SPEC/objetivos/supervisor-pasa-a-despacho.md, Fase 4
```

## Qué se pidió, y con qué medición

La Fase 3 se desplegó el 16/10 en sombra. La primera vuelta real, a las 20:07
del 16/10, midió 9 fallas y no pasó ninguna. El usuario pidió ver los tickets
uno por uno antes de tocar las reglas, y para eso entró el comando de solo
lectura `informe_de_pendientes` (desplegado en `10e7107f` y `bd8def5c`).

**Lo que mostraron los 64 pendientes reales:**

- 36 eran casos ya cerrados: el ISP resolvía las fallas de fibra por su flujo
  normal en 1 a 3 días, mientras el Supervisor esperaba a que una persona
  decidiera la propuesta.
- De los 27 abiertos: 3 caídos por LOS (hipótesis de fibra cortada), 5 con el
  equipo en línea y en rango, 6 obras de red o trabajos frenados por la
  confianza, 6 que ninguna herramienta mide o no son de red, 6 sin grupo, y 1
  con la medición incompleta.
- 9 lecturas tenían sus tres relecturas gastadas en "la respuesta del modelo
  no es un objeto": el modelo pedía herramientas en todas sus vueltas y el
  bucle devolvía ese pedido como contenido. Eran los tickets complejos, tres
  de ellos obras de red evidentes, una con 28 afectados.

**Lo que decidió el usuario**, ticket por ticket: se queda con una persona
solo la falla que la medición contradice. Todo lo demás pasa. Las cuatro
situaciones que su frase no cubría se le preguntaron y están en la ficha:
sin luz, persona; no se pudo medir, pasa; nada lo mide y órdenes internas,
persona; trabajos y obras, pasan siempre.

## Lo que se cambió

- **`decidir`**: una falla con medición pasa salvo `_EN_RANGO` y
  `_SIN_ENERGIA`. Pasan LOS/LOF, caído con otra causa, caído sin datos, en
  línea sin nivel, y lo que el proveedor no pudo medir. Sin medición todavía,
  espera. Trabajo pedido y obra de red pasan siempre:
  `CONFIANZA_EXIGIDA_SIN_MEDICION` se fue, y la confianza se escribe en el
  motivo.
- **`medicion_de_fallas`**, tras el auditor de frontera: un error del motor no
  se guarda como medición, y la falla espera a que se pueda medir. Un estado
  que el motor no usa hoy, o vacío, se guarda como `no_reconocido` y no pasa.
  Las piezas de error que la Fase 3 ya guardó cuentan como falta de medición
  y se miden en la vuelta siguiente.
- **`cerebro.razonar`**: cuando el modelo agota sus vueltas pidiendo
  herramientas, una llamada más sin herramientas le pide el cierre con lo que
  ya tiene. La pide solo la lectura de tickets (`concluir(..., cierre=True)`):
  el chat no tiene contrato JSON y queda como antes. Si el cierre falla, queda
  lo de antes. `agotado` sigue en True, y `validar` sigue exigiendo que cada
  hecho cite una herramienta consultada.
- **`_cuantas_veces_se_leyo`**: una lectura cuya respuesta no se pudo leer no
  cuenta para el tope de relecturas, con un tope absoluto del doble.
- **`informe_de_pendientes`**: sin las columnas de reglas alternativas, que ya
  no aplican; distingue "no entendida" y "error del motor".
- **Textos que afirmaban algo falso**, corregidos: el comentario de la "cola
  reversible" en `paso_a_despacho` (no hay acción para sacar un caso de la
  cola, A-2), el del tope de relecturas cuando no se puede contar, la medición
  que prometía "se vuelve a medir" en una propuesta que ya pasó, y
  `_CAIDO_SIN_CAUSA`, que decía que el proveedor no distingue la causa.

## Lo medido

Todas las corridas con `-e MOTOR_URL=http://127.0.0.1:9`, Postgres efímero
propio, sobre el worktree `C:/wt-area`.

**Regresión amplia sobre el código final**, 43 archivos: los 35 de la Fase 3,
más el cerebro, la lectura, el chat y las herramientas técnicas.

```
collected 1132 items
FAILED operaciones/tests/test_m11_indicadores.py::test_19_no_hay_segunda_cola_ni_tabla_de_kpi
FAILED operaciones/tests/test_cerebro_integracion.py::test_7_las_dos_entradas_comparten_el_bucle_y_el_catalogo
FAILED operaciones/tests/test_cerebro_integracion.py::test_26_SEGURIDAD_el_techo_de_la_etapa_sigue_en_RECOMENDAR
FAILED operaciones/tests/test_cerebro_integracion.py::test_27_SEGURIDAD_una_propuesta_de_nivel_2_3_o_4_NO_ejecuta[2]
FAILED operaciones/tests/test_cerebro_integracion.py::test_27_SEGURIDAD_una_propuesta_de_nivel_2_3_o_4_NO_ejecuta[3]
FAILED operaciones/tests/test_la_lectura_llega_a_la_propuesta.py::test_si_el_modelo_agota_sus_vueltas_la_lectura_igual_cierra
FAILED operaciones/tests/test_herramientas_tecnicas.py::test_2_el_catalogo_son_20_y_las_dos_familias_conviven
FAILED campo/tests/test_despacho_pantalla.py::test_j_los_de_OTRA_empresa_no_entran
===== 8 failed, 1123 passed, 1 skipped, 133 warnings in 730.25s (0:12:10) ======
```

`test_si_el_modelo_agota_sus_vueltas_la_lectura_igual_cierra` es de esta fase
y estaba mal escrita: buscaba el grupo en la última pieza de la lectura, y la
lectura deja varias. Lo delató la ronda de mutaciones, porque esa prueba caía
con todas. Se corrigió para buscar el grupo como lo busca el paso
(`_ultima_lectura_con_grupo`) y para afirmar también que la hipótesis del
cierre llegó. El archivo, corrido de nuevo: `4 passed in 11.35s`.

**Los otros siete son anteriores a esta sesión**, medidos sobre el código de
origin (`bd8def5c`):

- `test_7` cuenta 19 herramientas y `test_herramientas_tecnicas::test_2` cuenta
  20; hay 24 (`assert 24 == 20` también en origin). El catálogo creció sin que
  se actualizaran.
- `test_26` y `test_27` afirman el techo de la etapa en "recomendar" (1); está
  en 3 desde Autonomía 2 (09/10).
- `test_19`: el modelo `TareaDelegada` (`07719432`) no está en la lista de
  tablas que la prueba permite.
- `test_j`: el rol de prueba es superusuario y RLS queda inerte; bajo `crm_t`
  pasa (abajo).

En el camino aparecieron y se corrigieron otros rojos de esta fase. Dos
pruebas del chat (`test_cerebro_integracion::test_3` y
`test_p5_chat_supervisor::test_13`) se habían ajustado a la vuelta de cierre.
Cuando el cierre quedó solo para la lectura, volvieron a su versión de origin
y pasan. `test_lectura_de_ticket::test_una_propuesta_leida_con_resumen_viejo_se_detecta`
usa propuestas sin base, y el contador devolvía "agotado" donde el original
devolvía 0: se restauró el 0.

**Bajo un rol sin superusuario**, sobre el código final:

```
rol: crm_t|false|false            (rolsuper, rolbypassrls)
$ … TEST_DATABASE_URL=postgres://crm_t:t@pg-f4rls3:5432/test_rls … python -m pytest     campo/tests/test_despacho_pantalla.py     operaciones/tests/test_pasan_las_fallas_medidas_y_nunca_un_caso_cerrado.py     operaciones/tests/test_el_paso_mira_todas_y_dice_por_que.py     campo/tests/test_el_supervisor_llena_la_cola.py
collected 109 items
================= 109 passed, 28 warnings in 443.26s (0:07:23) =================
```

**Mutaciones**, sobre una copia del backend, cada una restaurada, con el
worktree intacto. Las veintitrés en rojo. R8 a R10 y R18 a R23 corrieron sobre
el código final (huella `e0a8bdcc64f98d82`), con los cuatro rojos anteriores
de `test_cerebro_integracion` fuera por `--deselect` para que no contaran como
muertes. R1 a R7 y R11 a R17 corrieron una ronda antes (huella
`d6901b793438fdfe`): el último parche no tocó esas líneas ni las pruebas que
las matan.

| # | Mutación | En rojo | La mata |
|---|---|---|---|
| R1 | En rango pasa | 17 | las reglas y el paso |
| R2 | Sin energía pasa | 2 | `test_b2[dying_gasp]`, `test_r1` |
| R3 | LOS no pasa | 3 | `test_b2b[los_lof]`, `test_r1`, `test_h3` |
| R4 | Trabajo u obra con confianza media no pasa | 4 | `test_e2`, `test_r2`, `test_r3` |
| R5 | Lo que el proveedor no pudo medir no pasa | 3 | `test_b2b[sin_medicion]`, `test_f4`, `test_r1` |
| R6 | Caído sin datos no pasa | 2 | `test_b2b[caido_sin_datos]`, `test_g` |
| R7 | En línea sin nivel no pasa | 3 | `test_b2b`, `test_f2`, `test_r1` |
| R8 | Sin la vuelta de cierre | 3 | `test_22b`, `test_22d`, la lectura de punta a punta |
| R9 | Una lectura rota cuenta para el tope | 1 | `test_una_lectura_que_el_modelo_no_contesto…` |
| R10 | Sin el tope absoluto | 1 | la misma |
| R11 | Un estado no reconocido pasa | 1 | `test_h` |
| R12 | Un error del motor se guarda como medición | 3 | `test_c8`, `test_e3`, `test_h2` |
| R13 | Un error guardado por la Fase 3 pasa | 1 | `test_h3` |
| R14 | Un error guardado espera 24 h para medirse | 1 | `test_h3` |
| R15 | Un estado vacío se toma como "no se pudo medir" | 1 | `test_h` |
| R16 | Un estado raro se toma como "no se pudo medir" | 1 | `test_h` |
| R17 | Después de un error se sigue como si hubiera medición | 2 | `test_e3`, `test_h2` |
| R18 | La lectura no pide el cierre | 1 | la lectura de punta a punta |
| R19 | Un cierre que falla se lleva la lectura | 1 | `test_22d` |
| R20 | `concluir` ignora el cierre | 1 | la lectura de punta a punta |
| R21 | El chat también pide cierre | 3 | `test_22c`, `test_3`, `test_13` |
| R22 | `validar` cambia el texto del descarte | 3 | `test_19`, `test_22d`, el tope por el camino real |
| R23 | Toda lectura con descartes deja de contar | 1 | `test_una_lectura_con_otro_descarte_SI_cuenta` |

**ruff**, por archivo contra origin: ningún aviso nuevo en los doce archivos
del backend tocados. Los que tienen avisos ya los tenían en origin, en la
misma cantidad.

## Agentes

**`auditor-de-frontera`.** Ningún camino nuevo salta las puertas: el pase
sigue saliendo solo por `pasar_si_corresponde` (caso abierto y fresco, tarea
delegada, techo, tope), y `revisar(automatico=True)` solo acepta. La vuelta de
cierre no ejecuta herramientas: la lista vacía llega al motor como "sin
herramientas", y `cerebro` ignora las llamadas que vengan en el cierre. Con
siete pruebas de efecto propias y tres mutaciones encontró:

| # | Hallazgo | Qué se hizo |
|---|---|---|
| H1 | Un estado que el motor no usa hoy ("online") se guardaba como "desconocido" y pasaba como "no se pudo medir", con el equipo en rango inclusive (medido: −21 dBm → aceptada) | **Corregido.** Se guarda como `no_reconocido` y no pasa; tampoco un estado vacío, porque el motor siempre lo escribe (verificado en `nucleo/herramientas/diagnostico_servicio.py`). `test_h`; R11, R15, R16 |
| H2 | Con el motor caído una vuelta, el error quedaba como "no se pudo medir" y la vuelta siguiente lo pasaba sin volver a medir (medido: 5 en rango pasaron con 0 llamadas al motor sano) | **Corregido.** Un error no es una medición: no se guarda y la falla espera a que se pueda medir. Las piezas de error que la Fase 3 ya guardó cuentan como falta de medición y se miden en la vuelta siguiente. `test_h2`, `test_h3`; R12, R13, R14, R17 |
| H3 | La "cola reversible" no existe: no hay acción para sacar un caso de la cola, sale cerrándolo (A-2, abierto desde la Fase 2), y la Fase 4 multiplica lo que entra | **Anotado; decide el usuario.** Se corrigió el comentario de `paso_a_despacho` que lo afirmaba |
| H4 | `test_p5_chat_supervisor::test_13` contaba 3 llamadas; con el cierre son 4 | **Corregido** |
| H5 | "Sin id de servicio" y "equipo no registrado en el proveedor" pasan siempre, sin gastar presupuesto | **Dentro de la decisión del usuario** ("no se pudo medir, pasa"). Lo acota el tope de 60 pases por vuelta |
| H6 | Si contar las relecturas falla, se cuenta 0 y el tope absoluto no alcanza | **Anterior a esta fase.** El comentario decía lo contrario y se corrigió |
| H7 | El cierre suma un mensaje: una lectura que llegue al tope de 40 mensajes del motor falla en el cierre y se reintenta en la vuelta siguiente | **Anotado**, marginal |

Dejó sin correr su mutación "sin energía pasa" al entregar a pedido; la
cubre R2 de esta nota, con 2 en rojo.

**`auditor-independiente`.** Auditó mientras el árbol cambiaba, y declaró
sobre qué foto midió cada cosa. De su primera foto, tres hallazgos ya estaban
corregidos por el auditor de frontera. Lo que encontró sobre el código con
esos arreglos:

| # | Hallazgo | Qué se hizo |
|---|---|---|
| 1 | "No se pudo medir" pasa también cuando lo que falla es la cadena: SmartOLT sin responder, WispHub caído, la empresa sin SmartOLT configurado, la config que no carga. Pasa en la misma vuelta, con el equipo sano inclusive, y una empresa sin SmartOLT haría pasar todas sus fallas. El log no separa los pases por motivo. VERIFICADO con cinco frases del motor | **Corregido el 17/10, por decisión del usuario:** "no se pudo medir" tiene que repetirse en dos vueltas seguidas para pasar; la primera vez la falla espera y se vuelve a medir en la vuelta siguiente. `test_m1`, `test_m2`, `test_m3` y `test_r1`; cinco mutaciones muertas (bitácora de la ficha) |
| 2 | El aviso que justifica pasar un LOS ("el despachador lo confirma con el cliente") no llega a la pantalla de Despacho: la API manda hipótesis y recomendación, no el porqué del pase. VERIFICADO en la API | **Corregido el 17/10, por decisión del usuario:** la ficha de Despacho trae `por_que_paso` (el motivo del pase, sin el prefijo, solo si lo aceptó el Supervisor) y la pantalla lo muestra antes de "Qué hay que hacer". `test_f`, `test_g` de la ficha y `test_n` de punta a punta; cuatro mutaciones muertas |
| 3 | La vuelta de cierre corría también en el chat, que no tiene contrato JSON: la persona habría visto el objeto crudo; y si fallaba, el turno perdía la traza de sus vueltas. Las dos pruebas ajustadas a +1 estaban verdes con el síntoma | **Corregido.** El cierre es opcional y lo pide solo la lectura; el chat vuelve a ser el de antes, y sus dos pruebas a su versión de origin. `test_22c`; R21 |
| 4 | Si la llamada de cierre fallaba, la lectura se perdía sin dejar fila, y el ticket se releía en cada vuelta sin techo | **Corregido.** Un cierre que falla deja lo de antes: el contenido de la última vuelta, que `validar` descarta y el tope cuenta. `test_22d`; R19 |
| 5 | Dos mutaciones vivas: cambiar el texto del descarte en `validar` (la prueba lo escribía a mano), y contar como rota toda lectura con descartes | **Corregido.** El texto es una constante de `cerebro` que lee el contador, y la prueba lo produce con `validar` y `registrar` de verdad. Otra prueba afirma que una lectura con otro descarte cuenta. R22, R23 |
| 6 | Textos que mienten: la medición promete "se vuelve a medir" en una propuesta que ya pasó; `_CAIDO_SIN_CAUSA` dice que el proveedor no distingue la causa; el docstring de `razonar` decía que no pide cierre; `vueltas` no cuenta el cierre; una propuesta aceptada sola conserva "por eso lo decide una persona" y la acción "Decidir qué se hace…", que Despacho precarga | **Corregidos** los cuatro primeros; `vueltas` queda documentado (el cierre no es una vuelta). **Anotado** el último: el motivo y la acción se escriben al crear la propuesta, y cambiarlos al aceptar es del mismo frente que el hallazgo 2 |
| 7 | El cierre también correría, sin efecto, en las dos fases del ciclo que llaman a `concluir` | **Corregido** con el 3: solo la lectura lo pide |
| 8 | El criterio 4.5 ("`pasaron=` alrededor de 10") es un conteo sobre una población que se mueve | **Corregido** en la ficha: se mira ticket por ticket, con el informe antes y después de la vuelta |

Lo que verificó en verde: la lectura, la medición y el paso corren desde el
beat de las :07 y desde el botón; el cierre no ejecuta una herramienta que se
le pida en el cierre; una respuesta en prosa o con JSON roto se marca rota y
no cuenta; 3 rotas y 2 buenas releen, 3 y 3 se dejan; un error del motor y una
pieza de error de la Fase 3 esperan. Lo que dejó sin auditar, porque necesita
producción o el modelo real: cuántas piezas "no se pudo medir" por falla de la
cadena hay hoy en propuestas vivas (pasarían en la primera vuelta), y qué
causas reales de caída caen en "otra".

## Límites declarados

- **"No se pudo medir" pasa recién en la segunda vuelta seguida** (desde el
  17/10). Antes de ese cambio, la regla era esta, y valía también para un
  SmartOLT o un WispHub que no responde: las fallas medidas en esa vuelta
  pasan, hasta el presupuesto de medición (15 por vuelta desatendida) y el
  tope de 60 pases, con el equipo sano inclusive. Una empresa sin SmartOLT
  configurado haría pasar todas sus fallas. Lo que no pasa es un error del
  motor ni un estado que no se reconoce. Hallazgo 1 del auditor
  independiente: se le plantea al usuario.
- **Despacho ve por qué pasó un caso** desde el 17/10: la ficha muestra
  "Pasó solo a Despacho: <motivo>", con el aviso de un LOS incluido. Antes
  ese motivo quedaba en la propuesta y no llegaba a quien despacha.
- **No hay acción para sacar un caso de la cola de Despacho** (A-2). Un pase
  equivocado hoy se corrige cerrando el caso. Si la cola se llena de pases que
  no correspondían, es lo primero que conviene construir.
- **LOS puede ser un equipo desenchufado.** Es la decisión del 14/10
  restaurada: el despachador confirma con el cliente antes de mandar a
  alguien. Conviene anotar las primeras semanas cuántos LOS resultaron
  desenchufados.
- **Medido en producción** el 17/10 a las 00:07 (criterio 4.5): pasaron 15,
  los 10 que el informe marcaba PASA y 5 obras de red que estaban trabadas
  sin grupo. Ver la bitácora de la ficha.
