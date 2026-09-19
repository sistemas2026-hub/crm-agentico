# Dexter Campo — checkpoint

Dónde está la aplicación de campo hoy, para que una sesión nueva pueda
retomarla sin leer ninguna conversación. Es **estado**, no historia: cuando algo
de acá cambie, se actualiza; lo que ya se cerró no se vuelve a narrar.

Última actualización: 18/09/2026, al abrir F7A.

## Dónde está el código

| | |
|---|---|
| Aplicación | `apps/tecnicos-mobile` (paquete `campo`) |
| Rama de trabajo | `feat/campo-diseno-stitch` |
| Base autorizada para F7A | `d8d2cdd` |
| Producción integrada | `601d8be228afcab3115bdab941b9b84964d1ceda` |

`d8d2cdd` es la fusión de producción hacia la rama de Campo. Producción quedó
**contenida entera** en la rama y **no fue modificada**: la rama que despliega no
se tocó y no se hizo push de nada.

Commits de Campo, sobre producción:

```
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

Nada de eso se reabre salvo que aparezca una regresión.

## Baseline

Medido en `d8d2cdd`, el 18/09/2026:

```
flutter analyze                                    sin problemas
flutter test -j 1                                  117/117
flutter test -j 1 --dart-define=DEXTER_DEMO=true   117/117
```

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

## Lo autorizado para F7A

Conservar de punta a punta tres datos que el backend **ya entrega** y
`_upsertOrden` descarta hoy:

| ID | Campos |
|---|---|
| CAMPO-DATA-015 | `estado_validacion` |
| CAMPO-DATA-016 | `cliente.lat`, `cliente.lng` |
| CAMPO-DATA-017 | `iniciada_en`, `completada_campo_en` |

Contrato de la migración: **aditiva, columnas anulables, compatible hacia
atrás**. Prohibido: reiniciar la base, `DROP TABLE`, recrear tablas, perder
órdenes, perder mutaciones o payloads pendientes. Si el mecanismo obligara a
reconstruir una tabla, **detenerse antes de hacerlo** y reportar.

Estado de la persistencia local hoy, en `lib/core/storage/local_database.dart`:

- base `dexter_campo.db`, **versión 5**, con `onCreate` y `onUpgrade`;
- el mecanismo ya es aditivo: `ALTER TABLE … ADD COLUMN` protegido por `PRAGMA table_info`, que es exactamente lo que F7A necesita;
- tablas: `local_ordenes`, `local_datos_dirty`, `cola_mutaciones`, `cola_evidencias`.

Pruebas mínimas que F7A debe dejar: base nueva, actualización desde el esquema
anterior, orden previa preservada, mutación pendiente preservada, campos nuevos
persistidos y leídos, ausencia o nulo compatible, segundo upsert correcto, y que
`estado_validacion` no mueva `estado`. Más una mutación que demuestre que alguna
de esas guardas muerde de verdad.

## Decisiones congeladas y deudas

| Tema | Decisión |
|---|---|
| `cancelar` | Existe en el backend. **No se expone al técnico.** Que el backend lo permita no lo convierte en permiso de interfaz |
| Botón "Llamar" | Pendiente: el teléfono es real, pero la acción necesitaría `url_launcher`. No en F7A |
| `JornadaScreen` | Legado sin llamadores. **No se borra** sin auditoría de consumidores (rutas, navegación, imports, pruebas, flujos offline) |
| `SyncBadge` viejo | Legado. Le queda un llamador: `ejecucion_screen.dart`. Se borra solo cuando queden cero |
| CAMPO-D1 | Las pruebas comparten base SQLite y no son seguras en paralelo. Sin arreglar; se mide con `-j 1` |
| Contador de alertas, histórico de señal, última sincronización | No se dibujan ni como ejemplo: se leerían como afirmaciones operativas |

Fuera de F7A: formulario de ejecución, fotos, cierre, mapas, distancia,
limpieza de legado y cualquier cambio al motor.

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
