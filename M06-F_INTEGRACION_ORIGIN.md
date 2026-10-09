# M06-F — Integración de M04–M06 sobre `origin/fix/integracion-wisphub`

Fecha: 22/09/2026 · Rama: `integracion/m06f` (worktree `C:\Users\Usuario\crm-m06f`), creada desde `origin/fix/integracion-wisphub` en `dc21cfd` · Sin commit, sin push, sin PR.

Este documento reemplaza la sección 13 de `M04-M06_CIERRE_FASE_GOBIERNO.md`. Allí se diagnosticó el NO GO; aquí se resuelve.

## 1. Producción: `ZZ-TEST-APROBACION`

Se hizo una sola consulta a producción, con SELECT únicamente, sobre `asistente.documents` y `asistente.document_chunks`, y terminó en rollback. Resultado:
- **0 documentos** con `codigo = 'ZZ-TEST-APROBACION'`;
- **0 fragmentos** asociados;
- **0 fragmentos huérfanos** en toda la tabla.

El documento de prueba de las corridas anteriores no dejó residuo.

La sesión se abrió pidiendo `default_transaction_read_only`, pero el servidor ignoró la opción (quedó `read_only: off`). La garantía fue la del propio código: solo SELECT y después rollback.

## 2. Base y alcance

La rama nace idéntica a origin. Encima se integró el trabajo local sin commitear del que M04–M06 dependen:

| Grupo | Qué | Por qué entra |
|---|---|---|
| Seguridad (motor) | `nucleo/seguridad/{interruptor, idempotencia, autonomia2, autorizacion, frontera, techo, aprobacion}.py`, `cli/autonomia.py` | M06 se apoya en ellos, y origin no tiene nada equivalente: ni kill switch, ni techo, ni autorización por herramienta, ni idempotencia hacia el tercero, ni frontera |
| Migraciones ya **aplicadas en producción** | `202609151700`…`151720` | Están en el ledger de producción con estos checksums (verificados). Faltaban en el repo |
| Migraciones nuevas | `202609221000`, `221010`, `221020`, `221030` | §5 |
| M04/M05 (Django) | `operaciones/` (sla, incidencias, novedades, migraciones 0006–0008), `common/0041` | Son el bloque |
| Aislamiento (Django) | Registro RLS y scope de tokens de las tablas de `operaciones`, roles SUPERVISOR/OPERACIONES | Las tablas donde vive M05 no tenían RLS registrada en origin |
| Rutas de programación (Django, `campo/`) | `campo/urls.py`, despacho, serializers (M03-B/D y M03-F-B) | **Sin ellas, 54 pruebas de M03 que origin ya versiona en `operaciones/tests` fallan con 404.** Se midió sacándolas: 56 fallas contra 2 |
| Pruebas y documentos | Baterías M06-A…E, M10-A, Autonomía 2, interruptor, idempotencia y la nueva `test_m06f_integracion_postgres.py`; reportes M06 y la matriz | Evidencia |

**Quedó fuera a propósito:**
- `despliegue/` (scripts operativos de B-7 y PASO10, ya ejecutados);
- `directivas/K-0x`;
- los ~120 reportes de otros bloques.

## 3. El ciclo de aprobación de origin (B5), documentado

**Modelo.** `asistente.acciones_propuestas` (con `conversation_id`, `vence_en` y `clave_equivalencia`, que es única entre las filas vivas) y `asistente.acciones_eventos`, que es append-only. Tiene RLS forzada por organización.

**Estados:** `pendiente, ejecutando, ejecutada_ok, ejecutada_fallo, desconocida, vencida, cancelada, rechazada`. Además `aprobada`, que solo existe como terminal de legado. Las transiciones se controlan en Python con compare-and-set (`UPDATE … WHERE estado = X`); la base no tenía triggers.

**Cómo avanza una acción:**
1. **Propuesta:** `motor._ejecutar_propuesta_de_accion` → `db.guardar_accion_propuesta`, con deduplicación T12. La acción se liga a su conversación al persistir el turno (`vincular_accion_a_conversacion`).
2. **Aprobación:** `POST /acciones/propuestas/<id>/aprobar`. El proxy de SvelteKit exige una sesión y fija `revisado_por` desde esa sesión. Aprobar es **reservar**: un compare-and-set `pendiente → ejecutando` que exige estar en plazo, tener conversación y que la conversación esté abierta.
3. **Revalidación:** fuera de la transacción (§3.7) → `liberar_accion` si no se pudo comprobar, o `vencer_accion` si no se cumple.
4. **Ejecución:** `motor.ejecutar_accion_aprobada`, con los argumentos guardados, por `ejecutor_http`.
5. **Desenlace:** `resolver_ejecucion_de_accion` → `ejecutada_ok`, `ejecutada_fallo` o `desconocida`, con su evento.

Lo que origin **no** tenía:
- sello ni origen;
- idempotencia hacia el tercero;
- kill switch;
- verificación del rol de quien aprueba;
- compare-and-set en el rechazo.

## 4. Cómo se integró la aprobación: una sola cadena

No se creó una segunda máquina de estados. La cola de B5 **es** la aprobación. M06 le agrega una capa:

```
propuesta B5 (+ huella, origen, contexto si es irreversible)
 → aprobación = reserva B5 pendiente→ejecutando, que escribe el SELLO en la misma sentencia
 → tenant/identidad (RLS + legado X24 + conversación abierta)
 → revalidación §3.7 (origin)
 → frontera.critica: kill switch → techo → etapa A2/B-7 → autorización → sello recalculado
 → previas frescas (M06-A) → idempotencia (accion_aprobada:<id>) → frontera.exigir
 → efecto → desenlace B5 con evento
```

Cambios concretos:
- **`aprobacion.APROBADA` pasa a ser `"ejecutando"`**: es el único estado en que una aprobación puede autorizar el efecto. `aprobada` (legado) y cualquier desenlace ya no valen, así que una aprobación no se reutiliza.
- **Lo que se eliminó:** `db.aprobar_accion_propuesta` y `registrar_resultado_accion` de M06-A (la máquina paralela), `api._aprobar_irreversible` y el vínculo duplicado con la conversación.
- **Endpoint único:** `_aprobar_y_ejecutar` contiene los pasos de B5. Si una guarda del código frena la acción antes del efecto, la fila queda `vencida` con el código del bloqueo; no queda `ejecutada_fallo`.
- **Rechazo:** ahora hace compare-and-set sobre `pendiente` (antes podía pisar una acción `ejecutando`) y responde 409 con el estado real.
- **Reinicio desde la Bandeja** (`POST /conversaciones/<id>/equipo/reiniciar`, de origin): antes llamaba al ejecutor directo. Ahora deja la propuesta en la cola, la aprueba quien aprieta el botón (su nombre queda en el sello) y sigue la misma cadena. Las cuatro condiciones de origin se mantienen: motivo, control humano, dueño o ADMIN, conversación abierta.

## 5. Migraciones

| Migración | Objetivo | Tablas y columnas | RLS | Triggers | Producción | Probada en PG |
|---|---|---|---|---|---|---|
| `141200`, `141300` (origin) | scheduler P2 | — | — | — | aplicadas, checksum = origin | sí |
| `151700`, `151705` | scheduler reconciliado | — | — | — | **aplicadas** (redundantes con las de origin; quedan porque el ledger las anota) | sí |
| `151710` | kill switch | `interruptor_autonomia` | sí | — | **aplicada** | sí |
| `151715` | idempotencia | `operaciones_externas` | sí | — | **aplicada** | sí |
| `151720` | rol operador | `autonomia_operador` | — | — | **aplicada** | sí |
| `202609221000` (antes `191430`) | Autonomía 2 | `nivel_autonomia`, `autorizacion_herramienta`, `ejecucion_autonoma` | vía `221010` y `221020` | — | no | sí |
| `202609221010` (antes `211900`) | techo | `nivel_autonomia.origen`, check 0..3, `techo_autonomia_intentos` | forzada | — | no | sí |
| `202609221020` (mitad RLS de la antigua `212000`) | aislamiento | `autorizacion_herramienta`, `ejecucion_autonoma` | forzada | — | no | sí |
| `202609221030` (reconstruida: `211800` + sello de `212000`) | aprobación vinculante sobre B5 | `acciones_propuestas`: `hash_argumentos`, `origen`, `contexto`, `sello_aprobacion` + 2 checks | conserva la de origin | **uno solo**, `acciones_propuestas_vinculante` | no | sí |

Qué se eliminó de las versiones anteriores:
- la columna duplicada `conversation_id` (B5 ya la trae);
- las dos versiones de `acciones_propuestas_inmutable`, reemplazadas por un solo trigger.

El trigger nuevo:
- conoce las transiciones de B5;
- borra el sello al liberar;
- permite `conversation_id → NULL` (`ON DELETE SET NULL` la deja como legado, que no se aprueba).

Las cuatro migraciones nuevas se renumeraron para ordenar después de la última de origin (`202609210900`): con los nombres viejos el runner las habría tratado como huecos.

Hallazgo sobre el ledger: los checksums que producción registra para `141200` y `141300` (`897cb5…`, `f325bd…`) son los de las versiones de **origin**. La "reconciliación" local de PASO10.5 partió de una copia desactualizada. Por eso `151700/151705` quedaron aplicadas encima como redundantes; no hacen daño, y deshacerlas no corresponde.

Pruebas en PostgreSQL descartable (pgvector pg16, `127.0.0.1:55433`):
- `cli/base_desde_cero.py` sobre la rama: **63/63 migraciones por el ledger**, verificación canónica en verde y segunda pasada con 0 pendientes;
- la misma construcción con origin: 54/54.

## 6. Sello

`sello_de(tenant, organization_id, herramienta, origen, huella, aprobador)`, que es el principio de M06-C sin cambios:
- **Se escribe** en la reserva, en la misma sentencia que pasa la fila a `ejecutando`, con un WHERE que exige que la herramienta, la huella y el origen sean los que se leyeron.
- **Está protegido** por el trigger: no se escribe a mano, no se reescribe y se borra al liberar.
- **Se recalcula** al ejecutar con el tenant y la herramienta que se van a ejecutar.
- **Invalida:** otro tenant, otro origen, otros argumentos, otro aprobador o un sello copiado de otra aprobación.
- **Queda auditado:** eventos B5, bitácora de la frontera y `operaciones_externas`.

## 7. RLS

- `acciones_propuestas`, `acciones_eventos` (origin), `interruptor_autonomia` y `operaciones_externas` (aplicadas): forzada.
- `nivel_autonomia`, `techo_autonomia_intentos`, `autorizacion_herramienta` y `ejecucion_autonoma`: forzada por las migraciones nuevas.
- El runtime corre con `SET ROLE app_backend`, que no tiene BYPASSRLS. Las comprobaciones de `221020` exigen además que `app_backend` no pueda escribir autorizaciones ni reescribir la bitácora.

Medido en PG: la otra empresa no ve ni puede reservar la propuesta (`no_existe`).

## 8. Techo

Sin cambios de diseño: fail-closed, por tenant, solo desde `cli:`, compare-and-set con advisory lock, auditado y con máximo 3. No sube por aprobación ni por propuesta. Ninguna herramienta declara `nivel_autonomia`.

Medido en PG: techo 1 contra un nivel exigido de 2 → `TECHO_AUTONOMIA_INSUFICIENTE`, sin efecto.

## 9. Herramientas

**El catálogo de origin tiene 76 herramientas, no 69.** Las siete nuevas se clasificaron con la regla más restrictiva y se agregaron a la matriz:

| Nueva | Clase | Nivel | Decisión |
|---|---|---|---|
| `consultar_caso_crm`, `consultar_asignados_caso_crm`, `consultar_perfiles_crm`, `consultar_topologia_ont` | R0 | 0 | lecturas |
| `asignar_caso_crm` | R2 | 2 | CRM propio, aditiva e idempotente. **No tiene DELETE**: desasignar es manual (`cases/assignee_views.py:24-35`) |
| `cerrar_ticket_operativo_estado` | R2 | INDETERMINADA | `aprobacion_humana: true`, igual que su familia |
| `registrar_promesa_y_reactivar` | R4 | 3 | **irreversible**: puerta crítica con sello |

Estado final del catálogo:
- **7 irreversibles:** las 3 R3, las 3 R4 y `cancelar_solicitud_servicio`.
- **14 con aprobación humana.**
- **Ninguna con `nivel_autonomia`.**
- Clases: R1=3, R2=21, R3=3, R4=3.
- `ping_cliente` y `sondear_api` siguen fuera de toda ruta sin persona.
- Las 4 indeterminadas de M06-D siguen bloqueadas para la autonomía, y no se probaron contra ningún sistema real.

## 10. Rutas (bypass)

- **Núcleo:** ninguna escritura HTTP fuera de `http.py` y `whatsapp.py` (verificado por AST).
- **Django:** no llama a WispHub ni a SmartOLT.
- **CLI:**
  - `prueba_reinicio_con_ping.py` sigue restringido al laboratorio;
  - `aplicar_sn_onu.py` es una herramienta documentada del operador;
  - `bateria_tv.py` habla con `/chat`, así que pasa por el motor.
- **Nuevo en origin, cubierto:** el botón de reinicio (§4).
- **Nuevo en origin, bloqueado (fail-closed):** el reconciliador T20 (`worker_reconciliador.py`) escribe llamando al ejecutor sin tenant, así que la frontera lo frena con `SIN_TENANT`. Hoy está apagado en producción (`RECONCILIADOR_HABILITADO`). Para encenderlo hay que pasarlo por una puerta, y eso es un bloque aparte.

## 11. Pruebas

La línea base es origin intacto (worktree `crm-origin`) con el mismo runner y el mismo entorno.

| Batería | Resultado |
|---|---|
| **M06-F en Postgres real** (`test_m06f_integracion_postgres.py`) | **34/34**. Mutaciones: sin comparar el sello, **el sello copiado de otra aprobación ejecutaba**; sin sello en la reserva, el trigger lo rechaza; sin la rama irreversible, la frontera la bloquea; con el estado viejo, no se ejecuta nada. Las cuatro mutaciones se detectaron y cada archivo se restauró con sha256 idéntico |
| M06-A gate crítico | 136 ok |
| M06-A frontera | 77 ok |
| M06-B techo | 96 ok |
| M06-C promesa y aislamiento | 37 ok |
| M06-D matriz | 27 ok |
| M06-E consolidación | 31 ok |
| M10-A | 23 ok |
| Frontera externa / adversarial | 18 / 35 ok |
| Ciclo de origin contra PG (`b5_acciones`, `g3`, `b6`, `b4`, `d28`, `t6`, …) | en verde; `b5_acciones` 62 ok |
| Suite del motor (134, aislada, sin `.env` en ningún directorio padre) | **11 fallas = las 11 de origin intacto, con idénticas líneas de falla** |
| Pruebas con base (17) | 5 fallas = las 5 de origin (scheduler/programador: esperan un catálogo de jobs sembrado) |
| Regresión Django (PG descartable) | **2 failed, 4604 passed, 43 skipped**: las 2 preexistentes (`test_docs_environment_variables`, `test_portal_rls`) |
| `makemigrations --check` | No changes detected |

Fallas nuevas encontradas y corregidas durante la integración:
- `herramienta.irreversible` sobre sustitutos de prueba → `getattr`.
- 4 respuestas HTTP que exponían el texto de la excepción → `fallo`/`registrar`, que es la regla de origin.
- 18 `print` del código de gobierno → `registrar()`, sin PII.
- La prueba D25 de origin esperaba que `cancelar_solicitud_servicio` saliera directo; desde M06-E se propone. Se adaptó a esa conducta.
- Sustitutos de prueba con firmas viejas: `guardar_accion_propuesta` ahora devuelve `(id, ya_existia)`, y `origen`/`evento_id` son parámetros nuevos.

## 12. Estado para el despliegue, que no es parte de este PR

**Desplegar esta rama cambia la conducta de producción, a propósito y fail-closed:**
1. **El kill switch de Rapilink está `detenido` en producción** (lo sembró la `151710`), y el código de origin hoy no lo lee. Con esta rama, **toda escritura autónoma del modelo se frena**: tickets, visitas, escalada. La vuelve a habilitar solo `cli/autonomia.py`.
2. **Las 7 irreversibles no salen ni aprobadas por una persona**, incluido el botón de reinicio. La puerta crítica exige etapa Autonomía 2 + B-7 cerrado (hoy responde `B7_REQUERIDO`), techo y autorización, y producción no tiene las migraciones `2210xx`. Esto es el diseño de M06-A. Si se quiere que una persona pueda aprobar una R3/R4 sin Autonomía 2 encendida, es una decisión de negocio aparte.
3. Las novedades históricas quedan `abierta` con `0007` (ver M04-M06 §4).
4. Antes de aplicar, correr `cli/migrar_asistente.py --estado` contra producción en solo lectura. El estado del ledger de producción para las migraciones de origin posteriores a `151720` no se consultó en este bloque.
