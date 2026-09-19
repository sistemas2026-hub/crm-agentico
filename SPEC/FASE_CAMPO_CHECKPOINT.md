# Dexter Campo — checkpoint

Dónde está la aplicación de campo hoy, para que una sesión nueva pueda
retomarla sin leer ninguna conversación. Es **estado**, no historia: cuando algo
de acá cambie, se actualiza; lo que ya se cerró no se vuelve a narrar.

Última actualización: 18/09/2026, al cerrar F7A.1.

## Dónde está el código

| | |
|---|---|
| Aplicación | `apps/tecnicos-mobile` (paquete `campo`) |
| Rama de trabajo | `feat/campo-diseno-stitch` |
| Base autorizada para F7A.2 | `dd89f10` |
| Producción integrada | `601d8be228afcab3115bdab941b9b84964d1ceda` |

`d8d2cdd` es la fusión de producción hacia la rama de Campo. Producción quedó
**contenida entera** en la rama y **no fue modificada**: la rama que despliega no
se tocó y no se hizo push de nada.

Commits de Campo, sobre producción:

```
dd89f10  F7A.1: los cinco datos del backend se persisten
fd5b34a  checkpoint canónico de Campo
d8d2cdd  fusión con producción 601d8be
17e2f11  documentación y backlog de datos
9dae731  implementación consolidada de F1 a F6
```

`django-crm/mobile` es otra aplicación (la que vino con BottleCRM). No es
Dexter Campo y no se toca.

## Qué está cerrado

| Fase | Qué dejó |
|---|---|
| F1 | Tema y tokens de "Field Ops Precision"; fuentes Geist y JetBrains Mono empaquetadas |
| F2 | Componentes base (`DexterCard`, badges, métrica, elección segmentada, vacío) |
| F3 | `AppShell`: encabezado, franja de sincronización, barra inferior, una sola suscripción |
| F4 | Pantalla Trabajo: pestañas, filtros reales, tarjetas por clase de trabajo |
| F5 | Pantalla Inicio y `OrdenesJornada`: una sola carga de órdenes para las dos pantallas |
| F6 | Detalle de orden: barra de pasos, acciones reales por estado, semántica offline |
| F6.5 | Integración de producción en la rama, sin conflictos |
| F7A.0 | Este checkpoint |
| F7A.1 | Migración local v5→v6 y cableado de los cinco datos que el backend ya entregaba |

Nada de eso se reabre salvo que aparezca una regresión.

## Baseline

Medido en `dd89f10`, el 18/09/2026:

```
flutter analyze                                    sin problemas
flutter test -j 1                                  129/129
flutter test -j 1 --dart-define=DEXTER_DEMO=true   129/129
```

Subió de 117 a 129 por las doce pruebas de `test/migracion_v6_test.dart`.
Ninguna prueba anterior cambió.

Es el baseline de hoy, no una invariante: una fase que agregue pruebas sube el
total, y lo que importa es poder atribuir el delta.

Dos cosas del entorno que no son regresiones:

- `flutter` no está en el PATH; vive en `C:\src\flutter\bin`.
- `flutter test` **sin** `-j 1` falla cinco pruebas porque los archivos corren en paralelo contra la misma base SQLite. Es previo a todo este trabajo (defecto CAMPO-D1, sin arreglar a propósito). El baseline se mide siempre con `-j 1`.

## Contratos que no se pueden simplificar

### Datos de ejemplo y modo demostración

```dart
FieldMockData.modoDemo = bool.fromEnvironment('DEXTER_DEMO')
```

Un dato que ningún sistema entrega se muestra **solo** con
`--dart-define=DEXTER_DEMO=true`, lleva identificador `CAMPO-DATA-XXX`, vive en
`lib/core/mock/field_mock_data.dart` y no decide nada: no habilita, no filtra,
no ordena y no alerta. `test/guarda_demo_test.dart` afirma las dos mitades y
corre en las dos compilaciones.

**`CAMPO-DATA-015`, `016` y `017` no son datos de ejemplo**: el backend ya los
entrega y el teléfono los descarta. No se condicionan por el modo demostración.

Nunca se inventa trabajo: sin órdenes, la lista se muestra vacía.

### Dos máquinas de estado, y no se mezclan

- `estado` (operativo): dónde está el trabajo. El grafo real vive en `django-crm/backend/campo/services/transiciones.py`; no es una línea.
- `estado_validacion`: si alguien lo dio por bueno. Es una máquina aparte, con sus propias transiciones.

**`estado_validacion` nunca mueve `estado` de forma implícita.** Una orden puede
estar completada en campo y rechazada, y las dos cosas son ciertas a la vez.

Tampoco al revés: una transición operativa local no toca la validación. Y
`requiere_correccion` de la máquina de validación **no** es
`correccion_requerida` de la operativa: parecerse no las hace lo mismo. Un valor
de validación que esta versión no conoce cae en `desconocido` —no se lo
convierte en otro conocido— y no rompe nada. Fijado en
`test/migracion_v6_test.dart`, grupo "Dos máquinas, no una", y en
`lib/features/trabajo/estado_validacion.dart`.

La lectura de la primera, para la interfaz, está en
`lib/features/trabajo/estado_trabajo.dart` y `lib/features/detalle_orden/pasos_orden.dart`:
`correccion_requerida` y `cancelada` se muestran como excepciones, no como pasos.

### Offline

La cola es contrato crítico. Una actualización de la aplicación conserva las
órdenes, las mutaciones pendientes con su payload, las claves de idempotencia,
la revisión base y el estado de sincronización. Una transición se guarda en la
base y se encola en la misma transacción; el envío es oportunista.

### Autoridad

El backend manda en la verdad funcional; Stitch manda en lo visual. Cuando el
diseño sugiere una máquina de estados que el backend no tiene, gana el backend
y la diferencia se documenta.

## Persistencia local: contrato de la v6

La base `dexter_campo.db` está en **versión 6**, en
`lib/core/storage/local_database.dart`. `onCreate` y `onUpgrade` dejan el mismo
esquema final; la migración v5→v6 es aditiva, con `ALTER TABLE … ADD COLUMN`
protegido por `PRAGMA table_info`, igual que las cuatro anteriores.

Columnas agregadas a `local_ordenes`, todas anulables:

```
estado_validacion     TEXT
cliente_lat           REAL
cliente_lng           REAL
iniciada_en           TEXT
completada_campo_en   TEXT
```

Las fechas se guardan como texto ISO del servidor, igual que `fecha_compromiso`;
**no** se regeneran con la hora del teléfono. Las coordenadas van como `REAL` y
puede existir una sin la otra.

### Semántica del upsert

`upsertOrden` sigue siendo un **reemplazo de fila** (`ConflictAlgorithm.replace`):
no es un parche general, y describirlo así sería falso.

El origen del dato varía: se pide el detalle y, si esa llamada falla, se guarda
el objeto reducido del listado. Por eso, **solo para CAMPO-DATA-015/016/017**:

| Qué llega | Qué se guarda |
|---|---|
| Clave ausente | Se conserva el valor local que ya estaba |
| Clave presente en `null` | Se guarda `null`: ahí el servidor está diciendo algo |

### Camino del dato

```
API de campo → upsertOrden → SQLite → getOrdenes → TrabajoVista
```

`TrabajoVista` expone `estadoValidacion`, `latitud`, `longitud`, `iniciadaEn` y
`completadaEn`. **Todavía no se muestran en ninguna pantalla**: quedan
disponibles para las fases que los necesiten.

### Contrato permanente de toda migración futura

La prueba de actualización abre una base de la versión anterior que ya contiene
una orden y una mutación pendiente, y comprueba que después de migrar siguen
ahí: la orden con su estado, y la mutación con su payload, su clave de
idempotencia, su revisión base, sus reintentos y su próximo intento.

No alcanza con comprobar que las columnas nuevas existen. Actualizar la
aplicación no puede costarle al técnico el trabajo que hizo sin señal.

## Decisiones congeladas y deudas

| Tema | Decisión |
|---|---|
| `cancelar` | Existe en el backend. **No se expone al técnico.** Que el backend lo permita no lo convierte en permiso de interfaz |
| Botón "Llamar" | Pendiente: el teléfono es real, pero la acción necesitaría `url_launcher`. No en F7A |
| `JornadaScreen` | Legado sin llamadores. **No se borra** sin auditoría de consumidores (rutas, navegación, imports, pruebas, flujos offline) |
| `SyncBadge` viejo | Legado. Le queda un llamador: `ejecucion_screen.dart`. Se borra solo cuando queden cero |
| CAMPO-D1 | Las pruebas comparten base SQLite y no son seguras en paralelo. Sin arreglar; se mide con `-j 1` |
| **CAMPO-D2** | **Bloquea F7B.** Ver abajo |
| Contador de alertas, histórico de señal, última sincronización | No se dibujan ni como ejemplo: se leerían como afirmaciones operativas |

Próximo trabajo: **F7A.2** (CAMPO-D2). Después, F7B: ejecución, formulario
dinámico, fotos y cierre.

Fuera de F7A.2: formulario de ejecución, fotos, cierre, mapas, distancia,
limpieza de legado y cualquier cambio al motor.

## CAMPO-D2 — una descarga a medias degrada los datos ricos

**Preexistente**, anterior a F7A y no causada por ella. **Bloquea F7B.**

`_descargarOrdenesAsignadas` pide el detalle de cada orden y, si esa llamada
falla, guarda el objeto reducido del listado. Como el upsert reemplaza la fila
entera, los campos que el listado no trae se pierden:

- `formulario_campos_json` queda en `[]`
- `formulario_evidencias_json` queda en `[]`
- el diagnóstico previo queda vacío

F7A.1 resolvió esto para sus cinco campos conservando el valor ante clave
ausente, pero **no tocó los demás**: era alcance nuevo.

Bloquea F7B porque esa fase construye justamente el formulario dinámico y las
evidencias: no tiene sentido levantar esa pantalla sabiendo que un fallo
temporal de red puede dejarla sin campos y sin fotos requeridas.

Se resuelve en **F7A.2**, antes de empezar F7B.

## Riesgos conocidos

- **`fecha_compromiso` puede venir vacía.** Inicio y la pestaña Hoy dependen de ella; si en producción muchas órdenes no la traen, esas vistas se ven pobres aunque haya trabajo. Falta medirlo con datos reales.
- **El aviso de varios trabajos en curso puede ser frecuente**, porque una orden queda `en_sitio` hasta completarse.
- **Los datos de ejemplo se ven igual que los reales** en la tarjeta cuando el modo demostración está encendido. Es deliberado; el límite está en el código y en el backlog.

## Dónde reconstruir el estado

| Fuente | Para qué |
|---|---|
| El código de `apps/tecnicos-mobile` | Autoridad funcional de la aplicación |
| `django-crm/backend/campo/services/transiciones.py` | Máquina operativa y acciones válidas |
| `django-crm/backend/campo/serializers.py` | Qué entrega la API de campo |
| `lib/core/storage/local_database.dart` | Esquema y migraciones locales |
| `apps/tecnicos-mobile/docs/campo_datos_pendientes.md` | Backlog de datos y qué falta construir |
| Este archivo | Fases, base, baseline, contratos y deudas |

La documentación de proveedores externos no se copia acá: vive en sus propias
skills y se consulta cuando la fase la necesita.

## Nota operativa

`Ver_Dexter_Campo.bat` y `scripts/` son archivos sin seguimiento
**preexistentes** en la copia local. No se agregan, no se borran y no entran en
ningún commit de Campo. Al reportar el estado del repositorio conviene separar
siempre el diff en seguimiento de los archivos sin seguimiento.
