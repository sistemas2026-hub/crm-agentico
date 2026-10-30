# Objetivo · La cuadrilla con cupo libre ayuda con otra labor

> Abierto el 30/10/2026. Estado: **abierto**.

## Qué significa terminado

Una cuadrilla que no llena su cupo con su labor recibe, en sus mismas zonas,
órdenes de otra labor que se quedaron sin cuadrilla —sin quitarle nunca lugar a
la suya—, sale con el material de las dos y Programación y la app lo dicen.

## De dónde sale

El usuario, 30/10/2026: «en caso de que no haya tanto ticket de soporte y haya
instalaciones disponibles, ¿cómo se puede hacer para que el Supervisor pueda
programar al mismo técnico soporte e instalaciones?».

**Amplía, no reabre, la decisión D1 de `labores-propias-por-empresa.md`
(20/10/2026)**: «una cuadrilla sale con UNA labor por día». La cuadrilla sigue
teniendo una labor principal, que manda; la de apoyo solo usa el cupo que la
principal deja libre. El usuario lo aprobó al pedirlo y con «arrancá» (30/10).

## Decisiones (30/10/2026, las recomendadas; el usuario: «arrancá»)

| # | Qué | Decisión |
|---|---|---|
| a | Sentido | Cualquiera: soporte con apoyo de instalación, instalación con apoyo de soporte, y lo mismo con las labores propias de la empresa |
| b | Cuánto | Solo el cupo libre: el reparto llena primero la labor principal de TODAS las cuadrillas y recién después reparte lo que quedó sin cuadrilla entre las que tienen apoyo y lugar |
| c | Quién | El Supervisor la pone solo en las jornadas que arma o reajusta él (`armada_por = automatica`), con la demanda que quedó sin cubrir en las zonas de esa cuadrilla. Una jornada armada por una persona no la toca (regla del 17/10); la persona la pone o la quita a mano. Hoy no hay registro de qué técnico sabe instalar: no se inventa |
| d | Material | El kit del día suma el de las dos labores |
| e | Orden | El del día del Supervisor, el de siempre (`campo.orden_del_dia`) |

## Criterios de aceptación

```
pytest campo/tests/test_labor_de_apoyo.py                      → todo verde contra Postgres
mutaciones de: apoyo antes que la principal, apoyo en otra zona,
  apoyo sin cupo, apoyo en jornada armada por una persona,
  kit sin el apoyo                                             → todas mueren
pytest campo operaciones business_hours                        → los 94 rojos de la base, ninguno nuevo
makemigrations --check                                         → sin cambios pendientes
vitest del Supervisor + svelte-check (sin errores en lo tocado) + vite build
flutter analyze + suite de la app                              → verde salvo e2e_002 #3
```

## Restricciones

- No push sin «haz el push» (push = deploy). No tocar `nucleo/` ni `tenant_config`.
- La labor principal no cambia de regla: `_elegir_labores` sigue igual para ella.
- El reparto sigue sin escribir: `repartir` devuelve, `publicar` escribe.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 30/10/2026 | **Construida.** Servidor: `JornadaDeCuadrilla.labor_de_apoyo` y `Labor.se_toma_de_apoyo` (migración `campo/0043`: dos columnas con valor por omisión —ninguna jornada cambia— y la obra de red, `trabajos`, en «no»: un corte de fibra pide equipo de empalme, la regla de `test_simular_el_dia::test_l`). `jornada_automatica._elegir_apoyos`: después de TODAS las principales, con el cupo que cada una deja libre (`_cubrir` devuelve lo que sobra), la labor con más casos sin cubrir en sus zonas, solo las que la empresa toma de apoyo; descuenta lo que toma; solo en las que arma o reajusta sola; con su auditoría. `reparto.repartir`: dos pasadas —lo que quedó sin cuadrilla o sin lugar va, en el mismo orden, a una con esa labor de apoyo en esa zona y cupo—. El kit del día suma el de apoyo (lo repetido, una vez). Programación, `mi-dia/`, Cuadrillas (una persona lo pone o lo quita: si no lo manda, no lo borra; igual a la principal, 400), la vista previa del armado, «Simular el día» y la cobertura de Despacho lo conocen; «se toma de apoyo» se edita con el kit de cada labor en Programación. Medido: `test_labor_de_apoyo` 17 + `test_mi_dia` 7 contra Postgres; las vecinas (armado, reparto, material, Programación, simulación, publicación, carga) 164 + 74 passed, los 5 rojos de `test_m03c_publicacion` son de la base; mutaciones 8/8 muertas (dos sobrevivieron y se cerraron con pruebas: la jornada de una persona —tenía dos guardas y solo una con prueba— y el apoyo sin cupo); `makemigrations --check` sin cambios; regresión `campo operaciones business_hours`: 3891 passed, 96 failed = los 94 de la base + 2 del ciclo del Supervisor que no encontraban Redis (quedó apagado al caerse Docker; levantado, las dos pasan): ninguno nuevo. Frontend: vitest del Supervisor 226, `svelte-check` 152 = base, ninguno en lo tocado; `vite build` OK. La app («y apoyás …») va con la novedad de la cuadrilla, que toca los mismos archivos | Deploy; ver una cuadrilla con apoyo en Programación | este commit |
