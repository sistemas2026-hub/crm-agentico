# Objetivo · La cuadrilla avisa una novedad y el Supervisor reacomoda

> Abierto el 30/10/2026. Estado: **abierto**.

## Qué significa terminado

Un técnico avisa desde Inicio, de un toque y sin escribir en ningún ticket, que
le pasó algo que le frena el día —«se me pinchó la llanta»—, y cuánto le
afecta. La oficina lo ve en Programación y le llega un aviso; mientras dura, la
regla de los 30 minutos no lo acusa; y si es «el resto del día», el Supervisor
pasa sus órdenes sin empezar a otras cuadrillas, por la misma puerta que una
ausencia.

## De dónde sale

El usuario, 30/10/2026: «¿cómo el técnico reporta alguna novedad sin tener que
escribir en el ticket, por ejemplo se pinchó la llanta, y esas novedades?».
Medido antes de empezar: lo único que existía era BLOQUEAR una orden
(`campo/bloqueos.py`), que es de una orden; una llanta pinchada es de la
cuadrilla y del resto del día.

## Decisiones (30/10/2026, las recomendadas; el usuario: «arrancá»)

| # | Qué | Decisión |
|---|---|---|
| 1 | Qué se avisa | Opciones de un toque: llanta, vehículo varado, accidente, lluvia o clima, se quedó sin material, otra; texto corto opcional |
| 2 | Cuánto afecta | 30 minutos, 1 hora o el resto del día. Lo dice el técnico; no se calcula |
| 3 | Cuándo termina | El técnico toca «Ya seguí»; las de 30 min y 1 h vencen solas a su hora; la del resto del día dura hasta que la cierra él o la oficina |
| 4 | Qué hace el Supervisor | «El resto del día» = sus cuentas cuentan como fuera hoy en la publicación (`publicacion_del_reparto`): su jornada no recibe trabajo y sus órdenes SIN EMPEZAR pasan a otras. Las empezadas no se mueven. Lo corto no mueve nada |
| 5 | La regla de los 30 minutos | Pausada mientras la novedad está vigente, con su nombre (`salud_seguimiento`), como un bloqueo esperando al NOC |
| 6 | A quién le avisa | A quienes gestionan en la empresa, por el despachador único (`common.notifications`): la campanita de la web |
| 7 | Sin señal | La app la encola como lo demás que escribe el técnico, con clave de idempotencia: un reintento no la duplica |

## Criterios de aceptación

```
pytest campo/tests/test_novedad_de_cuadrilla.py                → todo verde contra Postgres
mutaciones de: la de 30 min no vence, el resto del día no saca a
  la cuadrilla, mueve una empezada, no pausa los 30 minutos,
  otra empresa la ve, un reintento la duplica                  → todas mueren
pytest campo operaciones business_hours                        → los 94 rojos de la base, ninguno nuevo
makemigrations --check, vitest + svelte-check + vite build, flutter analyze + suite
```

## Restricciones

- No push sin «haz el push» (push = deploy). No tocar `nucleo/` ni `tenant_config`.
- El texto libre del técnico no va a logs (CLAUDE.md §5): se guarda y se muestra a la oficina, nada más.
- Las ausencias siguen igual: la novedad del resto del día se SUMA a `ausentes`, no la reemplaza.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 30/10/2026 | **Construida, con el seguimiento en Programación.** Servidor: `campo/novedades.py` (`NovedadDeCuadrilla`, migración `campo/0044`; `avisar` idempotente por `Idempotency-Key` —la restricción de la base frena la carrera de dos reintentos— y aviso a quien gestiona por `common.notifications`, una sola vez; `vigente`: la corta vence sola; `fuera_por_novedad`: la del resto del día suma a la cuadrilla a las ausencias de `publicacion_del_reparto`, que ya no le da trabajo y pasa lo suyo SIN EMPEZAR a otra; `pausa_de`: `salud_seguimiento` responde `pausado_novedad`). No es `operaciones.NovedadOperativa`: aquella es la causa de una reprogramación (Planes semanales), con lista cerrada y ciclo de gestión; esta la avisa el técnico, es de la cuadrilla y vence sola (se miró antes de crearla; chocaban dos nombres inversos y se cambiaron los de esta). `dia_publicado.jornada_de_la_persona`: una sola regla para `mi-dia/` y la novedad. **El seguimiento en Programación** (el usuario: «unos cuadros con la cuadrilla, qué tiene en progreso, qué tiempo lleva, y un log contraíble»): `campo/tiempos_del_dia.py` calcula con la bitácora la salida, la llegada y el fin de cada orden (traslado y tiempo en sitio), el resumen de la cuadrilla y el log del día —lo que hizo el Supervisor y lo que reportó el técnico, en orden de hora, sin datos del cliente—; Programación los trae con la regla de los 30 minutos por orden; arriba de todo los cuadros (`SeguimientoDeCuadrillas.svelte`), las novedades en la tarjeta de la cuadrilla y los tiempos en la de cada orden. La hora de los tiempos es la del servidor: con la app sin señal un traslado puede salir más largo, y se dice. App: base local v26 (`cola_novedades`), la subida con la clave de la fila y el «Ya seguí» aparte, «Avisar una novedad» en Inicio, la hoja de un toque y la franja mientras dura. Medido: `test_novedad_de_cuadrilla` 10 + publicación (`l3`: el resto del día mueve lo sin empezar y no lo empezado; `l4`: la corta no mueve nada) contra Postgres, y 126 vecinas; mutaciones del servidor 10/10 muertas (la del reintento sobrevivió hasta la prueba de la carrera); web: 15 pruebas nuevas, vitest del Supervisor 226, mutaciones 6/6, `svelte-check` 152 = base, `vite build` OK; app: `novedad_de_cuadrilla_test`, `subir_novedades_test` (la clave en la cabecera, el «Ya seguí», el 400 definitivo) y el grupo 17 de Inicio, mutaciones 7/7, suite 1163 passed, 1 fallida = `e2e_002` #3; regresión `campo operaciones business_hours`: 3905 passed, 94 failed = las mismas de la base, 0 errores | Deploy; APK 1.0.7; avisar una novedad desde un teléfono y verla en Programación | este commit |
