# Retiro de las alertas de caso antiguo de los casos que ya están en Despacho

```
BASE       origin/fix/integracion-wisphub = a9aa3d36 (la Fase 4 del paso a
           Despacho, desplegada el 16/10 a las 23:35). Se auditó sin commitear.
VEREDICTO  CERRADO EN CÓDIGO. NO verificado en producción.
FECHA      17/10/2026, madrugada (hora de Bogotá)
ALCANCE    operaciones/{paso_a_despacho,supervisor}.py,
           campo/despacho_pantalla_views.py y una prueba nueva. Ninguna
           migración. Nada en nucleo/, en el frontend ni en tenants/.
FICHA      SPEC/objetivos/supervisor-pasa-a-despacho.md, decisión del 17/10
```

## Qué se pidió

La vuelta de las 00:07 del 17/10 pasó 15 casos a Despacho. A las 00:30 el
usuario mandó una captura de Pendientes (44): el 77986, el 86528 y el 84000 ya
estaban en Despacho y seguían ahí, con "Revisar y priorizar este caso, o
cerrarlo si ya está resuelto". Es la alerta de **caso abierto antiguo** (más de
7 días abierto), que el paso a Despacho no toca. Se le propuso retirarlas y
dijo que sí.

## Lo que se cambió

- **Una sola definición de la cola de Despacho**, en `paso_a_despacho`
  (`propuestas_que_llevan_a_despacho`, `casos_en_despacho`). Vivía escrita
  solo en la pantalla de Despacho, que ahora la importa, en la lista y en la
  ficha.
- **El detector de caso antiguo** deja de proponer los casos que entraron a
  Despacho en los últimos `DIAS_CASO_ANTIGUO` días. Sin esto, la alerta
  retirada volvería cada hora: una cancelada no bloquea repetir.
- **Una fase nueva del ciclo**, después del paso a Despacho, cancela con motivo
  las alertas de caso antiguo pendientes de esos mismos casos. Solo ese tipo y
  solo pendientes, con el patrón del retiro por área (`cancelar`, renglón con
  título fijo y sin usuario, y una persona que decidió antes gana).
- **Con el mismo corte de 7 días**: si el caso sigue abierto 7 días después de
  entrar a Despacho, la alerta vuelve. Lo pidió el auditor independiente, y es
  lo que más cambió el diseño (ver abajo).

## Lo medido

Todas las corridas con `-e MOTOR_URL=http://127.0.0.1:9`, Postgres efímero
propio, sobre el worktree `C:/wt-area` con el código final.

**Regresión amplia**, 44 archivos: los 43 de la Fase 4 y la prueba nueva.

```
collected 1148 items
FAILED operaciones/tests/test_m11_indicadores.py::test_19_no_hay_segunda_cola_ni_tabla_de_kpi
FAILED operaciones/tests/test_cerebro_integracion.py::test_7_las_dos_entradas_comparten_el_bucle_y_el_catalogo
FAILED operaciones/tests/test_cerebro_integracion.py::test_26_SEGURIDAD_el_techo_de_la_etapa_sigue_en_RECOMENDAR
FAILED operaciones/tests/test_cerebro_integracion.py::test_27_SEGURIDAD_una_propuesta_de_nivel_2_3_o_4_NO_ejecuta[2]
FAILED operaciones/tests/test_cerebro_integracion.py::test_27_SEGURIDAD_una_propuesta_de_nivel_2_3_o_4_NO_ejecuta[3]
FAILED operaciones/tests/test_herramientas_tecnicas.py::test_2_el_catalogo_son_20_y_las_dos_familias_conviven
FAILED campo/tests/test_despacho_pantalla.py::test_j_los_de_OTRA_empresa_no_entran
===== 7 failed, 1140 passed, 1 skipped, 133 warnings in 713.29s (0:11:53) ======
```

Los siete son los rojos anteriores a esta sesión, medidos sobre origin en la
nota de la Fase 4. Ninguno nuevo.

**Bajo un rol sin superusuario**, donde `test_j` sí pasa:

```
rol: crm_t|false|false            (rolsuper, rolbypassrls)
$ … TEST_DATABASE_URL=postgres://crm_t:t@pg-f5rls3:5432/test_rls … python -m pytest     operaciones/tests/test_las_alertas_de_un_caso_en_despacho_se_retiran.py     campo/tests/test_despacho_pantalla.py campo/tests/test_despacho_api.py     campo/tests/test_ficha_despachable.py campo/tests/test_el_supervisor_llena_la_cola.py
collected 60 items
================= 60 passed, 40 warnings in 487.74s (0:08:07) ==================
```

La prueba entre empresas (`test_f`) fallaba en la primera versión bajo este
rol: creaba los datos de la otra empresa desde la sesión de la primera, y el
RLS lo rechaza. Así debe ser. Se reescribió para crear y leer cada empresa con
su contexto (`set_rls_context`), como `test_ficha_despachable`.

**ruff**, por archivo contra origin: ningún aviso nuevo en los trece archivos
del backend tocados.

**Mutaciones**: sobre una copia del backend, cada una restaurada, con el
worktree intacto (huella `14e4fd4e92916e9a` antes y después). Corrieron la
prueba nueva, el retiro por área y las tres pruebas de la pantalla de
Despacho, sin `test_j` (rojo anterior con el superusuario). Las quince en
rojo:

| # | Mutación | La mata |
|---|---|---|
| N1 | El retiro no mira la cola | `test_a` (el de control), `test_l` |
| N2 | El retiro toca todos los tipos | `test_d` |
| N3 | El detector vuelve a proponer | `test_g`, `test_h`, `test_l` |
| N4 | La fase no corre | `test_h`, `test_i` |
| N5 | La fase corre antes del paso | `test_i` |
| N6 | La cola incluye casos cerrados | `test_c` y la pantalla (`test_h_un_caso_CERRADO_no_entra`) |
| N7 | Una propuesta modificada no cuenta | `test_b` y la pantalla (`test_r_MODIFICADA…`) |
| N8 | Una visita aceptada no cuenta | `test_b` y siete de la pantalla |
| N9 | El renglón del feed repite la acción propuesta | `test_a` |
| N10 | El detector sin el corte de 7 días | `test_l` |
| N11 | El retiro sin el corte de 7 días | `test_l` |
| N12 | Un caso inactivo cuenta | `test_j[inactivo]` |
| N13 | Un caso fusionado cuenta | `test_j[fusionado]` |
| N14 | Un `origen_id` raro rompe | `test_k` |
| N15 | La fecha de entrada no importa | `test_l` |

Que N6, N7 y N8 las maten también las pruebas de la pantalla es la medida de
que la pantalla y el Supervisor leen ya la misma regla.

## Auditor independiente

Corrió unos 30 minutos sobre la primera versión, con Postgres propio. Ningún
camino cancela algo ajeno: filtra por empresa, tipo, estado y origen, y
`cancelar` vuelve a leer la fila bloqueada. Encontró:

| # | Hallazgo | Qué se hizo |
|---|---|---|
| 1 | Tres protecciones sin una prueba que las sostenga: caso fusionado, caso inactivo, `origen_id` que no es un id de caso. VERIFICADO con una mutación que las quitaba las tres y dejaba todo verde. Importa más que antes: la definición ahora corre dentro del detector, en la transacción del ciclo, y una excepción revertiría la vuelta entera | **Corregido.** `test_j` (fusionado, inactivo) y `test_k` (id raro, detector incluido). Mutaciones N12, N13, N14 |
| 2 | Una vez en Despacho, la alerta no volvía nunca: la cola no tiene otra salida que cerrar el caso, y un caso despachado que nadie cierra quedaba sin ninguna alarma de antigüedad | **Corregido** con el corte de `DIAS_CASO_ANTIGUO`, el mismo de la alerta. `test_l`. Mutaciones N10, N11, N15 |
| 3 | Una aceptación a mano retira su alerta en la vuelta siguiente, no en el acto | **Anotado** en el docstring: como mucho una hora con el ciclo automático |
| 4 | "Alguien ya lo hizo" y "ya tiene respuesta" no son ciertos en el pase automático, y "respuesta" choca con la del hilo del ticket | **Corregido**: el motivo dice que la alerta pedía revisarlo y priorizarlo y ya está en la cola, y cuándo vuelve |
| 5 | El tablero y el latido, que comparten el detector, cuentan menos casos antiguos; un caso que cumple 7 días en la misma vuelta en que pasa puede recibir una alerta que se cancela minutos después; `_ids_de_caso` duplicaba `_uuids` | **Anotado** lo primero (es lo buscado) y lo segundo (raro). **Corregido** lo tercero: una sola copia |

## Límites declarados

- **Producción no se midió.** Lo esperado en la primera vuelta después del
  deploy: una línea de log "N alertas de caso antiguo retiradas", y en
  Pendientes dejan de aparecer las alertas de caso antiguo de los casos que
  pasaron a Despacho en los últimos 7 días.
- **Las alertas de "requiere visita" de un caso en Despacho no se tocan.** Se
  acordó solo caso antiguo; extenderlo es otra decisión.
