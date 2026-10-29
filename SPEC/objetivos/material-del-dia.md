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
| 28/10 | **El kit y la bodega los elige el Supervisor; la configuración es solo para corregirlo.** Kit: el que comparte más raíces de palabra (6 letras, palabras de 5 o más) con el nombre de la labor; empate, no elige; ninguno, esa labor no carga. Bodega, en este orden: la única; la que nombra su zona (una palabra de 4 o más letras del nombre de la bodega dentro del nombre de la zona); la de la que ya le despacharon a su líder. Más de una que cumple, no elige. Cuando no elige, lo dice con el motivo. Lo que eligió una persona manda siempre | El usuario, al ver el panel de configuración: «la idea era que lo hiciera el Supervisor». Con los nombres de Rapilink deduce bien los dos kits y las dos bodegas (Soporte en campo → Kit de soporte técnico, Instalación → Kit de instalaciones nuevas; Soledad → BOG-SOLEDAD, SABANAGRANDE → BOF-SAB_GRANDE); la zona va antes que el historial porque el historial tiene despachos de prueba (medido con `reiniciar_custodia`) |
| 28/10 | **Cuándo carga: enseguida después de publicar el reparto de la mañana, una vez por día y cuadrilla.** Lo que se publica después durante el día no se recarga solo: se pide desde la app (pedido de material, ya existe) o va en la carga del día siguiente. Los equipos con serie no se despachan: quedan reservados en su bodega a nombre del acta hasta que el líder los escanee (fase 2) | Confirmado por el usuario («sí»). La custodia no puede decir que alguien tiene material que nadie le entregó en la bodega: cargar en cada vuelta horaria lo haría con quien ya salió, y el cierre de la jornada no cuadraría (como pasó con la cuenta de prueba) |
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
| 28/10/2026 | **El Supervisor elige solo el kit y la bodega** (decisión del 28/10 arriba). `kit_que_elige` y `bodega_que_elige` (puras salvo la consulta del historial), usadas por `propuesta` cuando nadie eligió y por `configuracion` para mostrar qué elegiría; cada tarjeta dice el kit y la bodega con su porqué («lo eligió el Supervisor: su zona la nombra» / «elegido por una persona»); el panel pasa a «Corregir lo que eligió el Supervisor» con «Que elija el Supervisor (hoy: …)» como primera opción. Medido: `test_material_del_dia` 16 passed; mutaciones de la deducción 8/8 muertas; ruff limpio; vitest 191; `svelte-check` 145 = base (tras `svelte-kit sync`: sin él, 152 por los `$types` de rutas nuevas de la otra sesión); `vite build` OK. No corrida otra vez la regresión completa: el cambio vive en el módulo nuevo, que solo lee | Que el usuario mire la propuesta; fase 2 (app) | este commit |
| 28/10/2026 | **Lo que mostró la propuesta en producción** (capturas del usuario): (1) una cuadrilla que hoy sale a SABANAGRANDE quedaba sin bodega («su zona nombra a más de una bodega») porque se sumaban sus zonas habituales, que incluyen Soledad → ahora mandan las zonas del día y las habituales solo si el día no tiene; (2) la tarjeta se empachaba con una línea «Faltan …» por material → un solo mensaje primero («Le falta material para completar el kit (N de M materiales): sale con lo que hay en bodega»), solo lo grave aparte (salir sin un equipo con serie), y la lista plegada («Ver los 14 materiales del kit · 9 incompletos») con lo que falta en la misma línea de cada material. Medido: `test_material_del_dia` 17 passed (`d6`: la captura); mutaciones 2/2 muertas; ruff limpio; vitest 193; `svelte-check` 145; `vite build` OK | Que el usuario mire otra vez; fase 2 (app) | este commit |
| 28/10/2026 | **El registro de cada entrega, a la vista** (pregunta del usuario: «¿dónde puedo ver el registro de lo entregado a los técnicos? Se tiene que guardar por entrega»). Se guardaba desde siempre (`EntregaDeKit` + `ItemDeKit` + movimientos) y ninguna pantalla lo mostraba. `inventario_operacion.entregas_a_tecnicos`: cada acta tal como quedó (técnico, bodega, quién despachó, material con la serie de cada equipo, si el técnico la confirmó), cortando el día en la zona de la empresa; reporte `entregas` en Inventario → Reportes (solo quien gestiona o atiende bodega). `inventario.despachar` guarda desde hoy el id de la entrega en cada movimiento (`datos.entrega`): sin acta no se podía saber de qué bodega salió; las viejas sin acta lo dicen. Es lo que va a mostrar las actas que cree el Supervisor en la fase 3 y las confirmaciones de la fase 2. Medido: `test_reporte_entregas` 4 passed + suites de inventario 41 (45 en total); mutaciones 5/5 muertas; ruff: los mismos avisos que HEAD; vitest de Reportes 9; `svelte-check` 145; `vite build` OK; regresión `campo operaciones business_hours`: 3798 passed, 94 failed = las mismas de la base | Fase 3 | este commit |
| 28/10/2026 | **Fase 3: el Supervisor carga el material solo** (en sombra hasta que se delegue). `operaciones/carga_del_material.py`, tarea propia `CARGAR_EL_MATERIAL` (nivel 3) con las puertas y la ventana de la publicación del reparto (`publicacion_del_reparto.cuando`), y fase del ciclo después de publicar. Carga al líder lo ASIGNADO por la propuesta con `inventario.despachar` (acta `MAT-<fecha>-<jornada>`, `despachado_por` vacío); los equipos con serie quedan reservados en su bodega con el acta al principio del motivo. Una vez por día y cuadrilla (`material_del_dia.cargadas`: por acta o por reserva). `material_del_dia.calcular` guarda los objetos para la carga (claves con «_», que no salen a la pantalla) y la propuesta dice `acta` y `cargado_en`; el reporte de entregas dice «despachó: el Supervisor»; Programación dice «Cargado por el Supervisor a las HH:MM · acta …». Medido: `test_el_supervisor_carga_el_material` 10 passed + material del día, entregas, ajustes y catálogo de tareas, publicación del reparto: 89 passed; mutaciones 8/8 muertas; ruff sin avisos nuevos; vitest 204; `svelte-check` 145; `vite build` OK; regresión `campo operaciones business_hours`: 3807 passed, 94 failed = las mismas de la base, ninguna nueva | Fase 2 (app): el técnico confirma y escanea las ONT | este commit |
