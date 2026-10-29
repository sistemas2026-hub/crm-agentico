# Objetivo · Medir los atascos del Supervisor

> Abierto el 29/10/2026. Estado: **abierto** (fase 1 construida; falta la medición de 1–2 semanas).

## Qué significa terminado

Hay un número, medido en producción durante 1–2 semanas, de cuántas cosas no
supo decidir el Supervisor cada día y de qué clase. Con ese número se decide qué
atascos le tocan a un agente de IA, y no antes.

## Por qué

El usuario, el 29/10/2026, viendo que «Trabajos» quedaba sin kit: *«siento que le
falta conocimiento al supervisor, ¿por qué no se hace agente IA?»*, y después:
*«siento que se hará algo bajo un flujo en una sola línea y cuando se presente
un problema no va a saber solucionar, se va a frenar o atascar»*. La propuesta
fue un **agente de excepciones**: las reglas resuelven lo normal; cuando una
regla se traba, el atasco pasa a un agente que investiga y elige una salida de
una lista cerrada; el código la valida antes de que tenga efecto; una persona
solo si el agente no encuentra salida.

A la pregunta *«¿eso mejora al Supervisor en qué rango de fallar?»* no había un
número. Lo único medido:

| Medición | Atascos que más contexto podía destrabar |
|---|---|
| Material del día, 29/10 (captura del usuario) | 0 de 1: «Trabajos» sin kit es correcto (las obras no llevan kit fijo) |
| Paso a Despacho, informe del 16/10 (`INFORME_PENDIENTES_DESPACHO_2026-10-17.md`) | a lo sumo 6 de 27 (22 %), y esos 6 los había trabado **la IA** (pedía herramientas en sus tres vueltas y nunca contestaba) |

Un agente no elimina atascos: cambia unos por otros (resuelve los imprevistos,
agrega que se trabe o se equivoque con algo que parece válido). Por eso,
**medir primero** (decisión del usuario: «dale hazlo»).

## Decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 29/10 | **Se mide antes de construir el agente.** Cada cosa que el ciclo no pudo decidir queda en `operaciones_atasco_supervisor`, con su tipo de un catálogo cerrado y su clase | El usuario: «dale hazlo», a la recomendación de medir 1–2 semanas |
| 29/10 | **Una fila por día, fase, tipo y sujeto**; `veces` cuenta las vueltas. Se mide en DÍAS y COSAS distintas, no en filas | El ciclo corre cada hora: contar filas inflaría el número doce veces |
| 29/10 | **Se anota también en la sombra** | Se mide si el Supervisor sabe decidir, no si tiene permiso |
| 29/10 | **Siete clases**: no sabe decidir · no alcanza lo que hay · falta un dato · la IA no contestó bien · las reglas lo dejan con una persona · una puerta de la empresa · algo se cayó | Solo la primera (y quizá la de la IA) es trabajo para un agente; las demás se resuelven con material, configuración o código |
| 29/10 | **Sin RLS, con filtro por empresa explícito** | El patrón más reciente del repo (`TareaDelegada`, las tablas de campo); el manifiesto de producción no cambia |
| 29/10 | **Anotar nunca levanta**: si la base falla, la fase sigue | La misma regla del paso a Despacho: lo informativo no tumba la vuelta |

## Qué se anota, y desde dónde

| Fase | Tipos |
|---|---|
| Material del día (`carga_del_material`) | `kit_sin_elegir` (por labor), `bodega_sin_elegir`, `sin_lider`, `material_no_alcanza`, `sale_sin_equipo`, `carga_fallo` |
| Reparto del día (`publicacion_del_reparto`) | `orden_sin_labor`, `orden_sin_zona`, `orden_sin_cuadrilla`, `orden_sobrante`, `cuadrilla_sin_cuenta`, `cuadrilla_ausente` |
| Paso a Despacho (`supervisor`) | `despacho_por_reglas`, `despacho_sin_delegar`, `despacho_sin_autorizar`, `despacho_otra_puerta`, `despacho_fallo`, `techo_ilegible` |
| Lectura de tickets (`diagnostico_de_ticket`) | `ia_error`, `ia_respuesta_rota`, `ia_sin_hipotesis` |
| El ciclo | `fase_caida` |

Fuera, a propósito: el armado de jornadas y la creación de órdenes (sus atascos
aparecen en el reparto como orden sin cuadrilla o sin labor).

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | Las pruebas de los atascos pasan contra PostgreSQL | `pytest operaciones/tests/test_atascos_del_supervisor.py operaciones/tests/test_el_supervisor_carga_el_material.py operaciones/tests/test_el_paso_mira_todas_y_dice_por_que.py operaciones/tests/test_rastro_de_la_lectura.py` → salida pegada |
| 2 | Las mutaciones mueren | `mutar_atascos.py` → N/N |
| 3 | La regresión `campo operaciones business_hours` no suma fallas a la base | comparación pegada |
| 4 | En producción, después del deploy, el informe imprime | `python manage.py informe_de_atascos --org <id> --dias 1` → salida pegada |
| 5 | Después de 1–2 semanas, el informe con `--dias 14` y la decisión de qué le toca a un agente, registrada acá | salida pegada + fila en Decisiones |

## Restricciones

- Push a `fix/integracion-wisphub` = DEPLOY: solo con «haz el push».
- No escribir `tenant_config`. No tocar `nucleo/`.
- Nada de datos del cliente en la tabla: ids y textos fijos.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 29/10/2026 | Ficha abierta y fase 1 construida (sin desplegar): modelo y migración `operaciones/0028`, `operaciones/atascos.py` (catálogo, `anotar`, `informe`), los ganchos de las cinco fuentes y `manage.py informe_de_atascos`. Medido: 58 pruebas de los atascos y de los archivos que tocan passed contra Postgres (18 nuevas); mutaciones 24/24 muertas (dos sobrevivieron con datos simétricos —un sujeto por día, 1 día y 1 cosa— y se corrigieron las pruebas); ruff: los mismos avisos que HEAD, más el orden de imports de la migración generada (lo tienen 28 migraciones); `makemigrations --check` sin cambios; regresión `campo operaciones business_hours`: 3836 passed, 95 failed = las 94 de la base + la guarda de modelos declarados de `test_m09m_asistentes`, que exige declarar cada modelo nuevo de operaciones (declarado, pasa). Un error encontrado al probar: la carga y el reparto anotaban con la hora actual y no con la de la vuelta | Deploy; criterio 4 en producción; 1–2 semanas de datos | este commit |
