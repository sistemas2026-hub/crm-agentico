# Dexter Campo — backlog de datos

Qué muestra la aplicación hoy, qué de eso es real, y qué hay que construir para
que lo que todavía no lo es deje de ser un valor de ejemplo.

El diseño de Google Stitch ("Dexter Campo Mobile App", sistema visual "Field Ops
Precision") muestra información que ningún sistema entrega todavía. Esa
información se pinta con valores de ejemplo, y cada uno tiene un identificador
`CAMPO-DATA-XXX` que se busca en el repositorio: `grep -rn CAMPO-DATA-001 lib/`
lleva al fixture y a cada lugar donde se usa.

## Las reglas

- **REAL** — llega de la API de campo, de la base local o de la sesión. Se usa tal cual.
- **MOCK** — el diseño lo muestra, ningún sistema lo entrega. Se ve **solo con el
  modo demostración encendido**, vive en `lib/core/mock/field_mock_data.dart` y
  nunca decide nada: no habilita, no filtra, no ordena, no descuenta ni alerta.
- **NO SE MUESTRA** — está en el diseño y ni siquiera como ejemplo se dibuja,
  porque se leería como una afirmación operativa (una alerta, un contador de
  avisos).

Mockear un **dato** está permitido; inventar **lógica de negocio** sobre ese dato
no. Y nunca se inventa trabajo: si el técnico no tiene órdenes, la lista se
muestra vacía.

```
flutter run --dart-define=DEXTER_DEMO=true    # producto completo, para mostrarlo
flutter run                                    # producción: solo datos reales
```

## Qué cambia con el modo demostración

| | Demostración apagado (producción) | Demostración encendido |
|---|---|---|
| Tarjeta de un trabajo | Número, cliente, dirección, tipo, estado y hora de compromiso | Se suman SLA, zona, prioridad y distancia |
| Inicio, encabezado | La fecha de hoy | Turno y cuadrilla |
| Inicio, señal del cliente | No aparece | Potencia RX, CTO, puerto PON y serial de la ONT |
| Inicio, Mi kit | No aparece | Recibidos, consumidos y disponibles |
| Campana del encabezado | Sin número | Con número |
| Todo lo demás | Igual | Igual |

## Datos reales, y de dónde salen

| Pantalla | Dato | Fuente |
|---|---|---|
| Todas | Colores, tipografía, tamaños | `lib/core/theme/` |
| Todas | Fuentes Geist y JetBrains Mono | `assets/fonts/` (empaquetadas, ver `LEEME.md`) |
| Encabezado | Logo | `assets/images/logo_dexter_campo.png` |
| Encabezado | Nombre, empresa e iniciales | Sesión (`SecureStorageService`) |
| Encabezado | Estado de conexión | `connectivity_plus` + resultado del último envío |
| Franja e Inicio | Estado de la cola | `SyncQueueService` → `SyncPresentacion` |
| Inicio y Trabajo | Órdenes de la jornada | `local_ordenes`, vía `OrdenesJornada` (una sola carga) |
| Inicio | Asignados, terminados, sin empezar | Calculado sobre esas órdenes (ver la nota de abajo sobre "Asignados") |
| Inicio | Trabajo en curso y próximos | Estado + fecha de compromiso |
| Trabajo | Pestañas y sus conteos | `features/trabajo/estado_trabajo.dart` |
| Trabajo | Filtro por clase de trabajo | `tipo_codigo` / `tipo_nombre` |
| Barra inferior | Contador de Trabajo | Órdenes en `asignada`, `en_camino`, `en_sitio` o `correccion_requerida` |

## Backlog: los datos que faltan

| ID | Pantalla | Componente | Dato futuro | Valor de ejemplo | Tipo | Fuente futura | Campo esperado | ¿Backend? | Prioridad | Estado |
|---|---|---|---|---|---|---|---|---|---|---|
| CAMPO-DATA-001 | Inicio | Señal del cliente | Potencia óptica RX | -18.7 dBm | decimal | SmartOLT vía backend | `telemetria.rx_dbm` | Sí | Alta | MOCK |
| CAMPO-DATA-002 | Inicio, Trabajo | Tarjeta | SLA restante | 01:42 | duración | Backend de Campo | `trabajo.sla_restante` | Sí | Alta | MOCK |
| CAMPO-DATA-003 | Trabajo | Tarjeta y filtro | Zona | Norte Urbano | texto/id | Backend de Campo | `trabajo.zona` | Sí | Media | MOCK |
| CAMPO-DATA-004 | Trabajo | Tarjeta y filtro | Prioridad | Alta | enum | Backend de Campo | `trabajo.prioridad` | Sí | Media | MOCK |
| CAMPO-DATA-005 | Inicio, Trabajo | Tarjeta | Distancia y tiempo de viaje | 4.2 km | decimal + entero | Ubicación del técnico + dirección | `trabajo.distancia_km`, `.eta_min` | Sí (y permiso de ubicación) | Media | MOCK |
| CAMPO-DATA-006 | Inicio | Encabezado | Turno de la jornada | 07:30 - 17:00 | rango horario | Backend de Campo | `jornada.turno` | Sí | Media | MOCK |
| CAMPO-DATA-007 | Inicio | Encabezado | Cuadrilla y móvil | Cuadrilla 04 · Móvil 12 | texto | Backend de Campo | `jornada.cuadrilla` | Sí | Baja | MOCK |
| CAMPO-DATA-008 | Inicio (futuro) | Vehículo | Placa y preoperacional | ABC123 | texto + booleano | Módulo de vehículos | `vehiculo.placa`, `.preoperacional_ok` | Sí | Baja | MOCK, sin usar todavía |
| CAMPO-DATA-009 | Inicio, Materiales | Mi kit | Recibidos, consumidos, disponibles | 24 / 8 / 16 | enteros | Inventario de Dexter | `kit.recibidos`, `.consumidos`, `.disponibles` | Sí | Alta | MOCK |
| CAMPO-DATA-010 | Encabezado | Campana | Notificaciones sin leer | 2 | entero | Backend de Campo | `notificaciones.sin_leer` | Sí | Baja | MOCK |
| CAMPO-DATA-011 | Inicio | Señal del cliente | CTO, puerto PON, serial ONT | CTO-04-A, PON 0/1/4 | texto | SmartOLT / WispHub | `telemetria.cto`, `.pon`, `.serial_ont` | Sí | Alta | MOCK |
| CAMPO-DATA-012 | Inicio (futuro) | Señal del cliente | Histórico de señal 48 h | — | serie temporal | SmartOLT | `telemetria.historico` | Sí | Media | NO SE MUESTRA |
| CAMPO-DATA-013 | Trabajo | Resumen | Contador de alertas de red | — | entero | SmartOLT | `jornada.alertas_rx` | Sí | Media | NO SE MUESTRA: un contador de alertas de ejemplo se lee como una alarma real |
| CAMPO-DATA-014 | Franja de sincronización | — | Marca de la última sincronización | — | fecha y hora | **App móvil**: `SyncQueueService` guarda la fecha de cada envío exitoso | `sync.ultima_exitosa_en` (local) | **No** | Baja | NO SE MUESTRA. No es deuda de API: se resuelve entero en el teléfono |
| CAMPO-DATA-015 | Detalle | Estado de validación | Si el supervisor lo aprobó o lo devolvió | — | enum | **Ya existe en el backend** | `estado_validacion` | No (falta guardarlo en el teléfono) | Alta | REAL DISPONIBLE, sin consumir |
| CAMPO-DATA-016 | Trabajo, Detalle | Ubicación del cliente | Coordenadas para navegar | — | decimal | **Ya existe en el backend** | `cliente.lat`, `cliente.lng` | No (falta guardarlo en el teléfono) | Media | REAL DISPONIBLE, sin consumir |
| CAMPO-DATA-017 | Detalle | Cabecera | Cuándo se inició y cuándo se completó | — | fecha y hora | **Ya existe en el backend** | `iniciada_en`, `completada_campo_en` | No (falta guardarlo en el teléfono) | Baja | REAL DISPONIBLE, sin consumir |

## Conversiones descubiertas en la Fase 6

Auditando la API de campo aparecieron tres datos que **el backend ya entrega** y
la aplicación tira a la basura: el serializador los manda y
`local_database.dart::_upsertOrden` no los guarda.

| ID | Antes | Hallazgo | Qué falta para usarlo |
|---|---|---|---|
| CAMPO-DATA-015 | No estaba en la lista | `estado_validacion` viaja en las dos respuestas (lista y detalle), con seis valores reales y su propia máquina de estados en el backend | Una columna en `local_ordenes` y guardarlo al descargar. **No se hizo ahora**: esta fase tiene prohibido tocar el esquema de SQLite |
| CAMPO-DATA-016 | Parte de CAMPO-DATA-005 | `cliente.lat` y `cliente.lng` ya vienen | Ídem. Con eso, "Navegar" deja de necesitar backend nuevo; la distancia sigue necesitando la ubicación del técnico |
| CAMPO-DATA-017 | No estaba en la lista | `iniciada_en` y `completada_campo_en` ya vienen | Ídem |

El más valioso es **CAMPO-DATA-015**: hoy una orden completada se ve igual esté
aprobada, esperando revisión o devuelta, y esa diferencia le importa al técnico
—es lo que le dice si el trabajo quedó cerrado o va a volver—. Propongo
conectarlo en cuanto se autorice una migración local; es una columna y una
lectura, sin tocar el contrato de la API.

## Qué hay que construir, agrupado por quién debe producirlo

### Backend de Dexter Campo

**Datos:** CAMPO-DATA-002 (SLA), 003 (zona), 004 (prioridad), 006 (turno),
007 (cuadrilla), 010 (notificaciones).

Son campos de la orden y de la jornada que hoy no existen en el modelo. La
cadena: agregarlos a `OrdenTrabajo` / un modelo de jornada → exponerlos en
`OrdenTrabajoListSerializer` y `OrdenTrabajoDetailSerializer` → guardarlos en
`local_ordenes` (migración de SQLite, que hoy no se toca) → leerlos en
`TrabajoVista` en vez de `FieldMockData`. Zona y prioridad además habilitan los
dos filtros que hoy se ven apagados.

### SmartOLT y la red

**Datos:** CAMPO-DATA-001 (RX), 011 (CTO, PON, serial), 012 (histórico),
013 (alertas).

Dexter ya habla con SmartOLT desde el motor (ver `PRD.md` §7.7), así que la
integración externa existe; lo que falta es exponerla para campo. La cadena:
endpoint en el backend que, dado el serial de la ONT del cliente, devuelva
señal e identificadores → decidir si viaja con la orden o se pide al abrirla
(pesa para el modo sin conexión) → definir qué se guarda offline y por cuánto
tiempo, porque una señal vieja engaña más que no tener ninguna.

### Inventario y materiales

**Datos:** CAMPO-DATA-009 y todo lo de la Fase 8 (bobinas, serializados,
consumibles, custodia, devolución).

Es el grupo que no tiene **nada** construido: ni modelo, ni API, ni pantalla. La
cadena: modelo de kit y movimientos → API de asignación, consumo y devolución →
cola offline propia, porque el consumo se registra sin señal → pantalla. Es la
más cara de las cuatro y la que más valor operativo tiene, porque hoy el
descuadre de material se resuelve en papel.

### Otros módulos

- **Distancia y tiempo de viaje** (CAMPO-DATA-005): necesita permiso de
  ubicación en el teléfono y una fuente de rutas. Decisión previa: si la
  distancia se calcula en el teléfono o en el servidor.
- **Vehículo y preoperacional** (CAMPO-DATA-008): módulo propio, hoy inexistente.
- **Academia**: sin diseño completo en Stitch y sin contenido definido.
- **Marca de última sincronización** (CAMPO-DATA-014): lo único de esta lista que
  no necesita backend — alcanza con que la cola guarde la fecha del último envío
  exitoso.

**Por dónde empezaría:** el grupo del backend de Campo (SLA, zona, prioridad,
turno), porque son campos en modelos que ya existen, desbloquean dos filtros y
no dependen de ningún sistema externo. Después la señal de SmartOLT, que es lo
que más le sirve al técnico parado en la casa del cliente.

## Una nota sobre "Asignados"

La métrica **Asignados** de Inicio es "las órdenes de la jornada vigente del
técnico", no "todo lo que alguna vez se descargó". Hoy las dos cosas coinciden
porque `local_ordenes` guarda lo que el servidor manda como asignado y nada más,
pero eso es una **inferencia**, no una garantía: el día que la base conserve
historia, este número empezaría a significar otra cosa sin que nadie lo cambie.

Cuando el backend tenga jornada o turno explícitos (CAMPO-DATA-006), la métrica
debería salir de ahí y no de contar filas.

## Una aclaración de dominio

**Ticket ≠ Orden de Trabajo ≠ Instalación.** Son tres cosas distintas del
negocio.

Lo que Campo recibe hoy es una **representación común para el técnico**:
`OrdenTrabajo` con `tipo_codigo` y `tipo_nombre`. La aplicación la usa para
cambiar el icono, la palabra y el acento de la tarjeta — nada más. Eso no es una
decisión de unificar las tres entidades, y no debe leerse como tal: el día que
un ticket necesite su propio flujo, lo va a tener.
