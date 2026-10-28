# Objetivo · El Supervisor carga el material del día

Abierto el 28/10/2026. Sigue a `supervisor-arma-la-jornada.md` (el Supervisor ya
arma las jornadas, crea las órdenes y publica el reparto solo).

## Qué significa terminado

Cada mañana, sin que nadie lo decida, cada cuadrilla que sale tiene cargado en la
custodia de su líder el kit de su labor, sacado de su bodega; si en la bodega no
alcanza, lo que hay se reparte según el trabajo publicado del día y se avisa lo
que falta. El técnico confirma en la app lo que recibió (las ONT, escaneándolas)
y al final del día la devolución llega a inventario precargada, para que quien
la recibe solo confirme o marque la diferencia.

Pedido del usuario (28/10/2026), textual en lo esencial: «el supervisor, como es
quien despacha los tickets de las cuadrillas, debe indicar qué plantilla de
material sale (Kit de soporte técnico y Kit de instalaciones nuevas) … hay veces
que no está la cantidad necesaria y el supervisor debe ver cómo está programado
el día para distribuir los materiales y sus cantidades bien entre las
cuadrillas … el objetivo está en que no haya intervención humana».

## Decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 28/10 | **El kit va al líder de la cuadrilla**, no uno por persona | Decidido por el usuario: es como se entrega físicamente |
| 28/10 | **Qué kit lleva cada labor** es configuración por empresa (`Labor.plantilla_de_kit`), sobre las plantillas que ya existen en Inventario | Las plantillas de kit ya son por empresa (`PlantillaDeKit`); qué labor usa cuál varía por empresa (CLAUDE.md §3.3) |
| 28/10 | **De qué bodega carga cada cuadrilla** es configuración por cuadrilla (`Cuadrilla.bodega`) | La empresa tiene más de una bodega (BOG-SOLEDAD, BOF-SAB_GRANDE, medido en el simulacro de `reiniciar_custodia`); elegida la recomendada por la regla del usuario |
| 28/10 | **Se carga lo que falta para completar el kit**: kit menos lo que el líder ya tiene en custodia, nunca negativo | Si el día anterior no devolvió todo, cargar el kit entero duplicaría material en la calle |
| 28/10 | **Si la bodega no alcanza, se reparte en proporción al trabajo publicado del día de cada cuadrilla, pesando la prioridad (alta 3, media 2, baja 1)**, sin pasarse de lo que cada una necesita; lo que no alcanza se avisa por cuadrilla, y una cuadrilla que sale sin un equipo con serie de su kit (p. ej. instalación sin ONT) es una alerta | Decidido por el usuario («ver cómo está programado el día para distribuir»); los pesos, elegidos por la regla del usuario |
| 28/10 | **Las ONT se atan a su serie cuando el técnico las escanea** al confirmar por la mañana (fase 2), no al despachar | El despacho exige la serie de cada equipo serializado; el Supervisor no puede leerla. Medido el mismo día: un despacho con series que la bodega nunca registró las da de alta sin control (`_comprobar_serie_libre`), y así nacieron 11 ONT de prueba |
| 28/10 | **Las dos confirmaciones físicas siguen siendo de una persona**: el técnico por la mañana y quien recibe la devolución | El sistema no puede contar objetos (CLAUDE.md §10: escalar cuando la garantía no se puede dar en código). «Sin intervención humana» es decidir, repartir y cargar |

## Fases

| Fase | Qué | Escribe en producción |
|---|---|---|
| 1 | Configuración (kit por labor, bodega por cuadrilla) y **«Material del día»** en Programación: la propuesta por cuadrilla, lo que alcanza y lo que falta | Solo la configuración |
| 2 | App: el técnico confirma lo recibido o marca la diferencia; las ONT se escanean | Sí (APK nuevo) |
| 3 | El Supervisor carga el material solo (tarea delegada, en sombra primero), con `inventario.despachar` | Sí |
| 4 | La devolución llega precargada (entregado − consumido) y se confirma con un toque | Sí |

## Criterios de aceptación (fase 1)

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | `pytest campo/tests/test_material_del_dia.py` pasa contra PostgreSQL | salida pegada |
| 2 | Mutaciones de la propuesta muertas (kit menos custodia, reparto, alertas) | salida del script pegada |
| 3 | vitest de Programación y `svelte-check` sin errores nuevos | salida pegada |
| 4 | El usuario ve en Programación la propuesta del día con sus kits y bodegas | captura |

## Restricciones

- Push a `fix/integracion-wisphub` = DEPLOY: solo con «haz el push».
- La fase 1 no mueve material: ningún `despachar`, ninguna reserva.
- Stage por rutas explícitas; no tocar `nucleo/`.

## Qué NO hacer

- No cargar material desde el código de la propuesta (eso es la fase 3, delegada).
- No elegir series de ONT en el servidor.

## Agentes involucrados

| Agente | Para qué | Estado |
|---|---|---|
| arquitecto-dexter | ¿ya existe? | La sesión principal lo hizo leyendo el código: `PlantillaDeKit`, `inventario.despachar`, `existencia`/`libre`, `ActaDeDevolucion`, `cierre_jornada`; falta la confirmación del técnico (`EntregaDeKit.confirmado_en` no lo escribe nadie) |
| auditor-de-frontera | Fase 3 (mueve material solo) | pendiente |

## Bloqueos

Ninguno para la fase 1.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 28/10/2026 | Ficha abierta. Antes de empezar: la cuenta de prueba de un técnico se dejó en cero con `manage.py reiniciar_custodia` (ver la bitácora de `supervisor-arma-la-jornada.md`) | Fase 1 | este commit |
| 28/10/2026 | **Fase 1: la propuesta y su configuración** (sin desplegar). `Labor.plantilla_de_kit` y `Cuadrilla.bodega` (migración `campo/0040`, dos columnas vacías); `campo/material_del_dia.py`: `configuracion`/`guardar_configuracion` (solo lo que viene, todo o nada, solo filas de la empresa y solo ubicaciones de tipo bodega), `repartir_lo_que_hay` (pura, D'Hondt por unidades con tope en lo que cada una necesita) y `propuesta` (no escribe; el peso sale de `dia_publicado.del_dia`, sin lo terminado; lo disponible es `libre`, no la existencia); `GET /api/campo/material-del-dia/?fecha=` y `GET/PUT …/configuracion/` (solo quien gestiona). En Programación: el resumen del material del día, lo que falta por bodega, un panel para elegir el kit de cada labor y la bodega de cada cuadrilla, y en cada tarjeta lo que se le cargaría y sus avisos. Medido: `test_material_del_dia` 11 passed contra Postgres; mutaciones 9/9 muertas; ruff limpio; `makemigrations --check` sin cambios; vitest 187 + carga y acción de Programación 11; `svelte-check` 145 = base; `vite build` OK; regresión `campo operaciones business_hours`: 3788 passed, 94 failed = las mismas 94 de la línea de base, ninguna nueva | Que el usuario configure kits y bodegas y mire la propuesta; fase 2 (app) | este commit |
