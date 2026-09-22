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
| Inicio, modo de jornada | No aparece | Selector de estado (sin guardar) y turno |
| Inicio, recursos del turno | Solo la cola de sincronización, que es real | Se suman kit, vehículo y academia |
| Inicio, señal del cliente | No aparece | Potencia RX, CTO, puerto PON y serial de la ONT |
| Inicio, Mi kit | No aparece | Recibidos, consumidos y disponibles |
| Campana del encabezado | Sin número | Con número |
| Trabajo, resumen | Completadas y en curso | Se suman Alertas RX y SLA del día |
| Trabajo, tarjetas | Cliente, dirección, tipo, estado, ventana real | Se suman distancia, telemetría, plan, requisito de seguridad y acta |
| Trabajo, buscador | Búsqueda real por cliente, dirección y OT | Se suma el botón de escanear, que avisa que falta |
| Detalle, secciones | Cliente, ubicación real, pasos reales y acciones | Se suman origen NOC, matriz de telemetría, materiales, protocolo y la guía de procedimiento |
| Detalle, ubicación | Coordenadas reales de la orden, o aviso de que faltan | Se suma la zona |
| Detalle | Cabecera con pasos, cliente y diagnóstico | Se suman telemetría de red, histórico y triage |
| Materiales | Dice que falta construir el módulo | Kit completo: custodia, trazabilidad y cierre de jornada |
| Ejecución | Formulario del backend y evidencia real | Se suman el equipo sugerido, el medidor por Bluetooth, la longitud de onda, el umbral de referencia y Academia |
| Trabajo, pie | No aparece | Última sincronización con el servidor |
| Detalle, franja | No aparece | Enlace Dexter y hora del último envío |
| Barra inferior | Contador real de trabajos | Se suman los puntos de aviso de Academia y Más |
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
| CAMPO-DATA-018 | Inicio | Chip de academia | Cursos pendientes | 1 | entero | Módulo de Academia | `academia.cursos_pendientes` | Sí | Baja | MOCK |
| CAMPO-DATA-019 | Inicio, encabezado | Avatar | Foto del técnico | — | url | Perfil del CRM | `profile.foto_url` | Sí | Baja | NO SE MUESTRA: se usan sus iniciales, que son reales |
| CAMPO-DATA-020 | Inicio, Trabajo | Tarjeta | Ventana horaria comprometida | 10:00 - 12:00 | rango | Backend de Campo | `trabajo.ventana_inicio`, `.ventana_fin` | Sí | Alta | MOCK |
| CAMPO-DATA-021 | Inicio, Materiales | Kit | Hora de confirmación del kit | 08:02 AM | hora | Inventario de Dexter | `kit.confirmado_en` | Sí | Media | MOCK |
| CAMPO-DATA-022 | Franja | — | Modo de trabajo de datos | Modo Dinámico | texto | Sin definir | — | Sí | Baja | MOCK. El número de cambios sin enviar, al lado, es real |
| CAMPO-DATA-023 | Trabajo | Tarjeta de instalación | Plan contratado | Fibra 500 Mbps | texto | **Ya existe en el backend** | `contexto.cliente.plan` | **No, desde el 22/09/2026** | Media | REAL DISPONIBLE (el plan). Los **materiales previstos** siguen sin existir |
| CAMPO-DATA-024 | Detalle | Triage | Lista de comprobaciones y causa sugerida | Facturación AL DÍA · Atenuación DEGRADADO | estructura | Dexter + SmartOLT | `triage.checks[]`, `triage.causa_sugerida` | Sí | Media | MOCK. La cita del cliente **sí** es real: es `diagnostico_previo_ia` |
| CAMPO-DATA-025 | Materiales | Custodia | El kit completo: consumibles, bobinas, serializados, terminales | 5 ítems | estructura | Inventario de Dexter | `kit.items[]` | Sí | Alta | MOCK. Ver `lib/core/mock/kit_mock_data.dart` |
| CAMPO-DATA-026 | Ejecución | Formulario | Equipo sugerido para reemplazo y su stock a bordo | ONT Huawei GPON HG8145V5 · 2 en camioneta | estructura | Inventario de Dexter cruzado con el tipo de falla | `kit.sugerencia_reemplazo` | Sí | Media | MOCK. Se muestra al responder que sí; **no se guarda** con la respuesta |
| CAMPO-DATA-027 | Ejecución | Medición óptica | Lectura tomada por el power meter por Bluetooth | — | decimal | Medidor del técnico (integración pendiente) | `medicion.bluetooth` | Sí | Alta | MOCK **que no escribe**: el botón se ve en demostración y no completa el campo. Una medición inventada quedaría firmada por el técnico |
| CAMPO-DATA-028 | Ejecución | Academia | Cápsulas de consulta del procedimiento en curso | 2 cápsulas | estructura | Módulo de Academia | `academia.capsulas[]` | Sí | Baja | MOCK. Ver `lib/features/ejecucion/widgets/bloque_academia.dart` |
| CAMPO-DATA-013 | Trabajo | Resumen | Trabajos del día con la señal fuera de rango | 1 | entero | SmartOLT cruzado con la jornada | `jornada.alertas_rx` | Sí | Media | MOCK. Estaba escrito a mano dentro de la pantalla; ahora vive en el catálogo |
| CAMPO-DATA-014 | Trabajo | Resumen | Cumplimiento del SLA del día | 94 % | entero | Backend de Campo | `jornada.cumplimiento_sla` | Sí | Media | MOCK. Misma historia que el anterior |
| CAMPO-DATA-029 | Trabajo | Tarjeta en curso | De qué ticket nació la orden | Ticket #1234 | estructura | **Ya existe en el backend** | `origen.{sistema,tipo,ref}` | **No, desde el 22/09/2026** | Media | REAL DISPONIBLE: el servidor ya lo entrega; falta que la aplicación lo guarde y lo muestre |
| CAMPO-DATA-030 | Detalle | Telemetría | Serie de potencia de las últimas 48 h | 10 lecturas | serie | SmartOLT | `telemetria.rx_48h[]` | Sí | Media | MOCK. Sin la serie no se puede dibujar la curva del diseño |
| CAMPO-DATA-031 | Detalle | Telemetría | Rango óptico esperado | -18.0 a -25.0 dBm | rango | Parámetro de la empresa | `red.rango_optico` | Sí | Alta | MOCK. Cada ISP define el suyo: no puede quedar fijo en el código |
| CAMPO-DATA-032 | Ejecución | Medición | Longitud de onda de la medición | 1490nm Óptico | texto | Catálogo de red | `red.longitud_onda_medicion` | Sí | Baja | MOCK |
| CAMPO-DATA-033 | Ejecución | Medición | Umbral de aceptación de la lectura | -15 a -25 dBm | rango | Parámetro de la empresa | `red.umbral_aceptacion_campo` | Sí | Alta | MOCK **que no valida**: se muestra como referencia, no bloquea el cierre ni marca la respuesta como incorrecta |
| CAMPO-DATA-035 | Detalle | Franja superior | Nombre y versión del enlace de sincronización | Dexter Link v4.2 | texto | Backend de Dexter | `enlace.nombre`, `.version` | Sí | Baja | MOCK |
| CAMPO-DATA-036 | Trabajo, Detalle | Pie y franja | Cuándo fue la última sincronización con éxito | Hace 1 min | marca de tiempo | **La propia aplicación** | — | Sí | Alta | MOCK. No es deuda del backend: la cola sabe cuántos cambios faltan, pero no guarda la hora del último envío bueno |
| CAMPO-DATA-037 | Detalle | Cabecera | Qué hay que hacer, en una línea | Diagnóstico en domicilio y verificación de potencia | texto | Backend de Campo | `trabajo.resumen` | Sí | Baja | MOCK |
| CAMPO-DATA-038 | Inicio | Modo de jornada | En qué está el técnico: en sitio, en ruta, disponible, pausa | 4 estados | enum | Backend de Campo + cola propia | `jornada.estado` | Sí | Alta | MOCK. El selector cambia lo que se ve y **no guarda nada**: marcar "Pausa" no llega a ningún supervisor |
| CAMPO-DATA-039 | Inicio | Tarjeta en curso | Hora estimada de llegada | 10:15 AM | hora | Cálculo con la posición del técnico | — | Sí | Media | MOCK |
| CAMPO-DATA-040 | Inicio | Cliente | Identificador del abonado en el ISP | ID 10984214 | texto | WispHub vía backend | `cliente.id_abonado` | Sí | Media | MOCK |
| CAMPO-DATA-041 | Inicio | Dirección | Cómo se entra: torre, piso, apartamento | Interior 3 - Apto 402 | texto | Backend de Campo | `cliente.detalle_acceso` | Sí | Alta | MOCK. Sin esto el técnico llega al edificio y no al apartamento |
| CAMPO-DATA-042 | Inicio | Vehículo | Modelo, odómetro y combustible | Kangoo · 82.451 km · 75 % | estructura | Módulo de vehículos | `vehiculo.modelo`, `.odometro`, `.combustible` | Sí | Baja | MOCK |
| CAMPO-DATA-043 | Inicio | Academia | Curso obligatorio y cuándo vence | Alturas (SST) · Vence hoy 18:00 | estructura | Módulo de Academia | `academia.obligatorio`, `.vence_en` | Sí | Media | MOCK |
| CAMPO-DATA-044 | Trabajo | Buscador | Lector de código del equipo del cliente | — | acción | Cámara + inventario | `equipo.serial` | Sí | Media | MOCK **que no lee**: el botón avisa que falta. La búsqueda por texto, al lado, sí es real |
| CAMPO-DATA-045 | Trabajo | Tarjeta | Requisito de seguridad del trabajo y aptitud del técnico | Certificación de alturas | estructura | `trabajo.requisitos[]` + `perfil.certificaciones` | — | Sí | Alta | MOCK. **No habilita ni bloquea**: hoy el técnico se entera del riesgo en el sitio |
| CAMPO-DATA-046 | Trabajo | Tarjeta terminada | Acta de cierre: estado y medición final | Aprobado · -19.4 dBm | estructura | Backend de Campo | `trabajo.acta` | Sí | Media | MOCK |
| CAMPO-DATA-047 | Detalle | Origen | De qué sistema y con qué referencia se abrió | wisphub · ticket · WH-91288 | estructura | **Ya existe en el backend** | `origen` | **No, desde el 22/09/2026** | Media | REAL DISPONIBLE. La **hora** de apertura sigue sin existir |
| CAMPO-DATA-048 | Detalle | Telemetría | OLT y puerto, distancia al splitter, potencia TX | 4 filas | estructura | SmartOLT vía Dexter API | `telemetria.olt`, `.distancia_splitter`, `.tx_dbm` | Sí | Media | MOCK |
| CAMPO-DATA-049 | Detalle | Protocolo | Los pasos del procedimiento del tipo de trabajo | 3-8 pasos | lista | **Ya existe en el backend** | `tipo.pasos[]` (de `WorkTypeVersion.esquema`) | **No, desde el 22/09/2026** | Alta | REAL DISPONIBLE: venían con la plantilla y nadie los entregaba. **No es la máquina de estados**: van aparte de la barra de pasos |
| CAMPO-DATA-050 | Detalle | Guía FTTH | Procedimiento recomendado para la falla | 4 pasos | lista | Base de conocimiento de Dexter | `procedimiento.pasos[]` | Sí | Media | MOCK. Material de consulta: no valida ni completa nada |
| CAMPO-DATA-051 | Materiales | Recepción | Acta del kit, quién lo despachó y a qué hora | Acta #K-2024-094 · M. Morales | estructura | Inventario de Dexter | `kit.acta`, `kit.despachado_por` | Sí | Media | MOCK |
| CAMPO-DATA-052 | Materiales | Serializado | MAC del equipo, cómo llegó y en qué estado | 48:57:54:A9:B0:C1 · Validado OLT | estructura | Inventario de Dexter | `equipo.mac`, `.estado_previo` | Sí | Media | MOCK |
| CAMPO-DATA-015 | Detalle | Estado de validación | Si el supervisor lo aprobó o lo devolvió | — | enum | **Ya existe en el backend** | `estado_validacion` | No (falta guardarlo en el teléfono) | Alta | REAL DISPONIBLE, sin consumir |
| CAMPO-DATA-016 | Trabajo, Detalle | Ubicación del cliente | Coordenadas para navegar | — | decimal | **Ya existe en el backend** | `cliente.lat`, `cliente.lng` | No (falta guardarlo en el teléfono) | Media | REAL DISPONIBLE, sin consumir |
| CAMPO-DATA-017 | Detalle | Cabecera | Cuándo se inició y cuándo se completó | — | fecha y hora | **Ya existe en el backend** | `iniciada_en`, `completada_campo_en` | No (falta guardarlo en el teléfono) | Baja | REAL DISPONIBLE, sin consumir |


## Una corrección de la paleta (22/09/2026)

Hasta esta fecha los colores salían del texto del sistema visual "Field Ops
Precision", que describe la intención: azul marino, azul de acción, blanco,
borde fino. **Las pantallas de Stitch usan otra cosa**: una paleta tonal de
Material, con `primary #00236f`, `secondary #0051d5`, `surface #faf8ff` y una
escala de contenedores (`surface-container-low/high/highest`). Y su
configuración redefine los radios: 2, 4, 8 y 12 px, donde `rounded-full` no es
un círculo sino 12 px.

Cuando el texto y la pantalla discrepan, gana la pantalla: es lo que el usuario
mira. `lib/core/theme/app_colors.dart` y `app_radius.dart` ahora llevan los
valores exactos de la maqueta, con los nombres anteriores conservados como
alias para no tener que tocar cada widget de una vez.


## Cambio de diseño de referencia (22/09/2026)

Hasta esta fecha se replicaba el proyecto de Stitch **"Dexter Campo Mobile
App"**. El proyecto que manda es **"Dexter Campo  App"**, que es otro diseño
del mismo producto: Inter en vez de Geist, otra paleta tonal (el terciario es
azul oscuro, así que lo correcto se pinta con un verde propio), `rounded-full`
vuelve a ser un círculo, y la pantalla de Inicio es un *Home Operacional* con
modo de jornada, avance del día y una rejilla de recursos del turno.

Lo que **no** cambió: qué datos son reales y cuáles de ejemplo, la guarda del
modo demostración y la regla de que nada de este catálogo decide nada.



## Lo que el servidor ya sabía (22/09/2026)

Al revisar el backend de Campo aparecieron **siete datos guardados en la base
que ningún serializador entregaba**. No eran deuda: eran datos disponibles sin
consumir, como pasó antes con `estado_validacion` y las coordenadas.

Ya se exponen (tanda 1 de `SPEC/BACKEND_CAMPO_DATOS.md`): el origen de la orden,
el contexto técnico congelado al despachar, los pasos del procedimiento, la
vuelta de validación, `cerrada_en`, la cuadrilla completa con sus roles, y —lo
más importante— **qué pidió rehacer el supervisor**: hasta ahora esa lista vivía
solo en la bitácora del servidor, así que una orden devuelta llegaba al teléfono
sin decir qué corregir.

Lo que falta ahora es del lado de la aplicación: guardarlos y mostrarlos.

## La aplicación ya consume lo que el servidor entrega (22/09/2026)

La base local pasó a la versión 7 con siete columnas nuevas y anulables, con el
mismo patrón aditivo de siempre: nada se recrea y una orden que ya estaba sigue
estando.

Lo que cambió en pantalla:

- **El Detalle dice qué hay que rehacer.** Una orden devuelta muestra la vuelta,
  la observación del supervisor y las evidencias a repetir, con el título que
  usa la plantilla y no el identificador interno.
- **El protocolo de atención es real** cuando la plantilla lo trae: se ve aunque
  no haya modo demostración, porque es un dato del tipo de trabajo. Solo cae al
  ejemplo si la orden todavía no lo trajo.
- **El ticket de origen y el plan del cliente** salen del backend cuando vienen;
  si no, siguen los valores de ejemplo.

Lo que **no** se guarda de un listado: la devolución, el contexto, los pasos y la
cuadrilla solo los puede afirmar el detalle. Un listado que llega después de un
fallo de red no los borra (CAMPO-D2).

## Números de identificador

Los identificadores no se reutilizan: si un dato se retira, su número queda
quemado. **CAMPO-DATA-034 nunca se asignó** —se saltó al numerar—, así que no
falta una fila: falta el número, a propósito.

## Las dos pantallas que faltaban en el diseño (22/09/2026)

El proyecto "Dexter Campo  App" no tenía pantalla de Materiales ni de
Ejecución. Con autorización del usuario se generaron las dos en Stitch, con el
mismo sistema visual del proyecto, y de ahí salieron los datos 051 y 052, más
la forma de la cadena de custodia.

De la de Ejecución, lo que se incorporó es **real**, no de ejemplo: la versión
del formulario que manda el backend (`schema_version`), cuántas fotos de las
pedidas ya están tomadas, y qué requisito sigue pendiente. El diseño proponía
además un hash de respaldo local del formulario; no se puso porque la
aplicación no lo calcula, y un identificador inventado en una pantalla de
trazabilidad es exactamente lo que no se debe hacer.

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
- **Marca de última sincronización** (CAMPO-DATA-036): lo único de esta lista que
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
