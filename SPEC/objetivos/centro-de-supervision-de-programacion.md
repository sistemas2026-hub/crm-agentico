# Objetivo · El centro de supervisión de Programación (y, después, el mapa GPS)

> Abierto el 31/10/2026. Estado: **Etapa 1 construida, sin desplegar**. Etapas 2 y 3 bloqueadas por dos decisiones.

## Qué significa terminado

Un supervisor abre Programación y, **sin leer nada**, sabe: cuántas cuadrillas hay y cuántas van en ruta, cuánto se publicó y cuánto espera, qué necesita que alguien actúe, y cuánto del día está terminado. Más adelante, dónde está cada cuadrilla.

## De dónde sale

El usuario, 31/10/2026, con un spec y una referencia visual: *«rediseñar el módulo de Programación y Seguimiento de Cuadrillas… un centro de supervisión que permita controlar las órdenes, las cuadrillas, los técnicos, los materiales y la ubicación GPS»*. Y: *«toma la mejor decisión para el proyecto y solo me pides el push»*.

## Las etapas

| # | Qué | Estado |
|---|---|---|
| 1 | Franja de indicadores, panel de alertas, resumen del día | **Construida** (este commit) |
| 2 | GPS en la app: envío en segundo plano, permiso visible, señal y batería | Bloqueada |
| 3 | Almacén de posiciones + mapa en el web + los 4 escenarios sin coordenadas | Bloqueada |

## Decisiones (31/10/2026)

**1 · La navegación de la app NO cambia**

La referencia traía un sidebar propio. Cambiar la navegación tocaría todas las pantallas del módulo y no agrega información: el valor está en los indicadores, las alertas y el resumen. Se conservan `PestanasNoc` y el lienzo actual.

**2 · Los números los calcula el servidor, nunca el navegador**

`cuentas` gana seis campos: `cuadrillas`, `en_camino`, `completadas`, `pendientes`, `cumplimiento`, `con_novedad`. Una cuenta sumada en el navegador no se puede probar con pytest y cada pantalla la redondearía distinto. El `cumplimiento` es un entero, calculado una sola vez.

**3 · `en_camino` cuenta CUADRILLAS, no órdenes**

La pregunta del supervisor es cuántas cuadrillas van en ruta. Una cuadrilla con dos órdenes en camino sigue siendo una.

**4 · Las alertas no piden nada nuevo al servidor**

`alertasDelDia()` las arma con lo que la página ya cargó, así que **no puede decir algo que las tarjetas no digan**. Orden por gravedad: `grave` (dejó de reportar, sin app, sobrecargada) antes que `avisa` (novedad vigente, material faltante, espera revisión) antes que `dato` (espera cuadrilla).

**5 · Si el material no se pudo leer, la ficha de kits NO se dibuja**

Un `0` ahí diría «están todos completos», que es justo lo que no se sabe. Distinguir «no hay faltantes» de «no se pudo averiguar».

**6 · Solo las novedades VIGENTES son alerta**

Una resuelta hace tres horas no es algo que atender.

## Lo que queda fuera de la Etapa 1, dicho

- **El mapa y el GPS.** Son las etapas 2-3.
- **«Técnico sin actualización de ubicación»** como alerta: necesita el GPS continuo, que no existe. Hoy la app solo captura coordenadas **al tomar una foto** (`apps/tecnicos-mobile/lib/core/storage/ubicacion_de_captura.dart`).

## Bloqueos de las etapas 2 y 3

1. **Proveedor de mapa.** Google/Mapbox son terceros nuevos: exigen resolver la autorización de tratamiento (Ley 1581) antes de activarse, igual que cualquier tercero (CLAUDE.md §5). OpenStreetMap no agrega tercero.
2. **Cuándo comparte posición el técnico.** Recomendado: solo durante la jornada, con la notificación fija visible. Nunca oculto.
3. **Adopción de la app.** El 31/10/2026, **4 de 5 técnicos** figuran «sin teléfono registrado · nunca se conectó». Sin la app no hay pin, ni recordatorio, ni órdenes en el teléfono. No es código.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 31/10/2026 | **Etapa 1 construida.** Servidor: `dia_publicado.cuentas` + 6 campos derivados. Web: `FranjaDeIndicadores`, `AlertasDelDia`, `ResumenDelDia` y el helper `alertasDelDia()`. **Medido:** `test_dia_publicado` 26/26 contra Postgres; **mutaciones 7/7 muertas** —una sobrevivió hasta reforzar la prueba: con una sola orden en camino, contar cuadrillas y contar órdenes dan igual—; 275 pruebas de la web (9 nuevas, dos encontraron errores míos: el `78 %` no vive en la franja y Svelte agrega su sufijo a las clases); `svelte-check` 143 = base; `vite build` OK; regresión completa del backend = la base | Regresión; deploy; la pantalla con la franja arriba | este commit |

## Nota de método

El agente `arquitecto-dexter` reportó ese día que **nada de esto existía** (`dia_publicado.py`, `lib/supervisor/`, los componentes). Era falso: los subagentes arrancan en `C:\Users\Usuario\crm-agentico`, el repo principal, **200+ commits atrás**, no en el worktree donde se trabaja. No confiar en el «no existe» de un subagente sobre código del worktree sin comprobarlo.
