# M04–M06 — Cierre de la fase de gobierno

Fecha: 22/09/2026 · Rama local: `fix/integracion-wisphub` (sin commit) · Veredicto: **NO GO PARA PR** (ver §13)

---

## 1. Alcance

Este documento consolida M04 (señales SLA), M05 (ciclo de incidencia y escalamiento), M06-A (gate crítico R3/R4 con aprobación vinculante), M06-B (techo de autonomía por niveles), M06-C (RLS de las tablas de autonomía, sello de aprobación y R4 `agregar_promesa_pago`), M06-D (matriz de las 69 herramientas) y M06-E (las excepciones conservadoras, la auditoría de rutas y esta consolidación).

No se rediseñó nada. M06-E solo aplicó las reglas conservadoras de la sección 3 del bloque, cerró un bypass real y agregó dos guardas de prueba.

Límites que se respetaron:
- No hubo deploy, commit, push ni PR.
- No se aplicó ninguna migración en producción.
- No se llamó a WispHub ni a SmartOLT reales.
- No se ejecutó ninguna acción sobre clientes.

Hubo un contacto con producción desde la suite de pruebas. Está en §13.1.

## 2. Arquitectura del gobierno

Toda escritura externa pasa por `nucleo/herramientas/http.py::ejecutar`. Esa función llama a `frontera.exigir(herramienta, tenant, argumentos)`, el último medidor, que exige un permiso abierto por una de tres puertas:

| Puerta | Quién la abre | Cadena de controles |
|---|---|---|
| `autonoma` | El sistema (scheduler, importador, agente sin persona) | tenant → kill switch → **techo** → etapa Autonomía 2 (+B-7) → autorización granular → bitácora → permiso |
| `humana` | Una persona identificada (actor + evidencia) | actor + evidencia → permiso. No consulta el kill switch ni el techo: el humano decide |
| `critica` | La aprobación de una acción R3/R4 o de una excepción | tenant → kill switch → techo → etapa → autorización → **aprobación vinculante con sello** → bitácora → permiso atado a la herramienta y al hash de sus argumentos |

`exigir` agrega tres reglas que ninguna puerta puede saltarse:
1. Una herramienta `irreversible` solo sale con un permiso `critica` de la misma herramienta y con el mismo hash de argumentos. Si no, devuelve `IRREVERSIBLE_SIN_APROBACION` o `PERMISO_DE_OTRA_ACCION`.
2. Una herramienta con `aprobacion_humana` nunca sale con un permiso `autonoma`. Devuelve `APROBACION_REQUERIDA`.
3. Un permiso `critica` no se reutiliza para otra herramienta ni para otros argumentos.

Módulos: `nucleo/seguridad/{frontera, techo, aprobacion, autorizacion, autonomia2, interruptor, idempotencia}.py`.

## 3. M04 — señales SLA

- `operaciones/0006_m04a_senales_sla`: amplía `choices` de `propuestasupervisor.tipo_senal`. No toca la base.
- `sla.py` calcula las señales y **no escribe `Case`**.
- `cases/` y `business_hours/` quedan sin modificar.
- Regresión de Django en verde, salvo las dos fallas preexistentes (§12).

## 4. M05 — ciclo de incidencia y escalamiento

- `0007_m05a_lifecycle_incidencia`: agrega a `novedadoperativa` los campos `estado` (default `'abierta'`), `impacto`, `resolucion`, `resuelta_en` y `resuelta_por`.
- `0008_m05b_escalamiento`: agrega a `actividadoperativa` los campos `escalado_a`, `escalado_en` y `nivel_escalamiento`.
- Riesgo operativo que hay que conocer antes de aplicar: **todas las novedades existentes quedan `'abierta'`** y pueden aparecer como `INCIDENCIA_SIN_RESOLVER` en el supervisor el primer día. Decidir antes del deploy si se cierran en lote las históricas.

## 5. M06 — gobierno de la autonomía

| Sub-bloque | Qué quedó |
|---|---|
| M06-A | Las R3 (`reiniciar_ont`, `activar_catv`, `cambiar_tipo_onu`) y las R4 (`registrar_pago`, `agregar_promesa_pago`) son `irreversible` + `aprobacion_humana`. El agente **propone**; la propuesta guarda hash, origen y contexto; se ejecuta solo al aprobar, por la puerta crítica, con previas frescas, idempotencia y medición del efecto. |
| M06-B | Techo 0..3 por tenant (`TECHO_MAXIMO_POLITICA = 3`), fail-closed con 7 códigos. Solo se cambia desde `cli/autonomia.py --techo N --desde M` (origen `cli:`), con compare-and-set bajo advisory lock, y nunca con un permiso abierto. Cada intento queda en `techo_autonomia_intentos`. |
| M06-C | RLS forzada en `autorizacion_herramienta` y `ejecucion_autonoma`. Sello `sello_de(tenant, org, herramienta, origen, huella, aprobador)`, escrito al aprobar y recalculado al ejecutar (`APROBACION_SIN_SELLO`, `APROBACION_ALTERADA`). `agregar_promesa_pago` queda atada. |
| M06-D | Matriz formal de las 69 herramientas (`M06-D_MATRIZ_AUTONOMIA.yaml`): 41 en L0, 3 en L1, 7 en L2, 14 en L3 y 4 INDETERMINADA. Es una **propuesta de clasificación**, no un cambio de runtime. |
| M06-E | Excepciones conservadoras (§8, §9), cierre de un bypass real por CLI y la guarda contra escritura en base real (§6). |

## 6. Controles vigentes y hallazgos de la auditoría de rutas

Rutas auditadas y resultado:

| Ruta | Paso por la frontera |
|---|---|
| Conversación / agente | `_ejecutar_tool` → `ejecutor_http` → `exigir` |
| Scheduler / reloj (`cerrar_vencidas`) | `operativo.puerta` sin actor → puerta autónoma |
| Importador (`importacion_io._puerta`) | puerta autónoma |
| Agendamiento | `_ejecutar_tool` |
| `operativo.responder` | puerta humana (actor = autor humano) |
| Aprobación (`/acciones/.../aprobar`) | puerta crítica |
| `/interno/herramienta/` (Django → motor) | `ejecutar_para_servicio`: solo `invocable_por_servicio` + frontera |
| Django | No llama a WispHub ni a SmartOLT (único GET: un PDF público sin credenciales en `avisos.wisphub.io/media`). Al motor solo le pide lecturas o herramientas invocables por servicio |
| Núcleo | Ningún `requests/httpx.post/put/patch/delete` fuera de `http.py` y `whatsapp.py` (verificado por AST) |

**Bypass real encontrado y cerrado:** `cli/prueba_reinicio_con_ping.py` reiniciaba una ONU (R3) llamando directo a SmartOLT, sin frontera. Ahora exige `--confirmo-reinicio-de-laboratorio=CDTC505AE4AB` y que el SN sea la ONU de laboratorio. Si no, termina con exit 2 y "NO se reinicia nada". Está verificado y cubierto por `test_m06e_consolidacion`.

**No es bypass, documentado:** `cli/aplicar_sn_onu.py` es una herramienta de migración de datos del operador, que se corre a mano y está documentada. Queda como está.

**Guarda nueva de prueba:** `tests/test_aprobacion_documentos.py` escribía en la base que dijera el `.env`, que apunta a producción. Ahora se niega (OMITIDA, exit 0) contra cualquier host no local, salvo `PERMITIR_PRUEBA_EN_BASE_REAL=1`.

## 7. Herramientas críticas

| Herramienta | Clase | irreversible | aprobación | Cómo sale |
|---|---|---|---|---|
| `reiniciar_ont` | R3 | sí | sí | solo por la puerta crítica, con sello |
| `activar_catv` | R3 | sí | sí | ídem |
| `cambiar_tipo_onu` | R3 | sí | sí | ídem |
| `registrar_pago` | R4 | sí | sí | ídem |
| `agregar_promesa_pago` | R4 | sí | sí | ídem |
| `cancelar_solicitud_servicio` | R2 (sin cambio) | sí | sí | ídem (excepción, §8) |

Estado del catálogo semilla: 6 irreversibles, 12 con aprobación humana y **ninguna** con `nivel_autonomia` declarado. Los niveles efectivos siguen siendo 0 para las lecturas y 2 para las escrituras, así que el runtime no se relajó.

## 8. Excepciones aplicadas

| Regla | Aplicación |
|---|---|
| 3.A Lecturas | No pasan por la frontera y no tienen efecto autónomo. Las únicas lecturas por POST son `ping_cliente` y `consultar_solicitud_por_cedula`, ya identificadas. |
| 3.C `cancelar_solicitud_servicio` | Queda fuera de la autonomía con aprobación humana atada: `irreversible` + `aprobacion_humana` + plantilla. **Su clase histórica R2 no se cambió.** La cubre toda la batería de M06-A (sin/con aprobación, sello, kill switch, bypass). |
| 3.D `ping_cliente` | Se trata como efecto externo. No es invocable por servicio y ningún módulo sin persona lo nombra. No tiene autonomía automática. |
| 3.E R1 | **No se bajó a nivel 1.** M06-D lo proponía, pero no se aplicó: las R1 siguen exigiendo 2. |

## 9. Indeterminadas

| Herramienta | Tratamiento |
|---|---|
| `responder_ticket_operativo` | `aprobacion_humana: true`. No sale por la puerta autónoma ni por la ruta de servicio (`APROBACION_REQUERIDA`, 0 llamadas). Por la puerta humana, con una persona en pantalla, sigue saliendo. |
| `cerrar_ticket_operativo` | Ídem. |
| `completar_ticket_instalacion` | Ídem. |
| `sondear_api` | Solo el rol `configuracion_guiada` (un ADMIN en pantalla). No es invocable por servicio y ninguna ruta sin persona la alcanza. |

Por la regla 3.B, ninguna se probó contra un sistema real.

**Efecto a vigilar:** el scheduler cerraba tickets operativos vencidos por la puerta autónoma (`operativo.cerrar_vencidas`). Con esta excepción, ese cierre automático **queda bloqueado** con `APROBACION_REQUERIDA` hasta que se clasifiquen. Es la opción más restrictiva y la que exige el bloque, pero es un cambio de conducta visible.

## 10. Migraciones

Ninguna está aplicada en producción.

| Migración | Objetivo | Tablas | Columnas | RLS | Triggers | Riesgo | Probada en PG |
|---|---|---|---|---|---|---|---|
| Django `operaciones/0006_m04a_senales_sla` | choices de `tipo_senal` | `propuestasupervisor` | — (AlterField) | — | — | bajo | sí (regresión) |
| Django `operaciones/0007_m05a_lifecycle_incidencia` | ciclo de incidencia | `novedadoperativa` | estado, impacto, resolucion, resuelta_en, resuelta_por | — | — | **medio**: históricas quedan `'abierta'` | sí |
| Django `operaciones/0008_m05b_escalamiento` | escalamiento | `actividadoperativa` | escalado_a, escalado_en, nivel_escalamiento | — | — | bajo | sí |
| Django `common/0041` | choices de `entity_type` | `activity` | — (AlterField) | — | — | bajo | sí |
| Motor `202609191430` | Autonomía 2 (prerrequisito) | autorizacion/ejecución autónoma | — | — | — | — (previa) | sí |
| Motor `202609211800` (M06-A) | aprobación vinculante | `acciones_propuestas` | hash_argumentos, origen, contexto, conversation_id | — | inmutabilidad | **alto frente a origin** (§13.2) | sí |
| Motor `202609211900` (M06-B) | techo | `nivel_autonomia`, `techo_autonomia_intentos` | origen; check 0..3 NOT VALID | forzada | — | bajo | sí (20/20) |
| Motor `202609212000` (M06-C) | aislamiento y sello | `autorizacion_herramienta`, `ejecucion_autonoma`, `acciones_propuestas` | sello_aprobacion | forzada | trigger extendido | **alto frente a origin** | sí (34/34, las 5 en orden) |

Las migraciones Django no tienen RunPython ni RunSQL. `makemigrations --check` da "No changes detected" (RC=0). No hay colisión de numeración con origin (origin llega a `0005` en operaciones y `0040` en common).

## 11. Pruebas

| Batería | Resultado |
|---|---|
| `test_m06a_gate_critico` | 123 ok |
| `test_m06b_techo_autonomia` | 95 ok |
| `test_m06b_techo_postgres` (PG descartable) | 20/20 |
| `test_m06c_promesa_y_aislamiento` | 37 ok |
| `test_m06c_postgres` (PG descartable) | 34/34 |
| `test_m06d_matriz_autonomia` | 28 ok |
| `test_m06e_consolidacion` | 31 ok |
| Suite del motor aislada (98 archivos, sin credenciales ni `.env`) | 91 pasan, 2 fallas preexistentes, 5 OMITIDAS (cargan `.env`) |
| Regresión Django (PG descartable) | **2 failed, 4585 passed, 43 skipped** (las 2 preexistentes) |
| `makemigrations --check` | sin cambios |

Las 5 OMITIDAS de la suite del motor son `test_aprobacion_documentos`, `test_configuracion_guiada`, `test_frontera_de_dia`, `test_sondeo` y `test_token_servicio`. Se omiten a propósito porque su `.env` apunta a producción.

Los casos dorados (`cli/evaluar.py`) **no se corrieron**: van contra el motor real y el modelo real, y este bloque prohibía producción. Hay que correrlos tras integrar con origin (§14).

## 12. Fallas preexistentes

Se confirmó que ya fallaban antes de M04 y que no guardan relación con este trabajo:

- Motor: `test_p2_inerte` y `test_reloj`.
- Django: `test_docs_environment_variables::test_no_documented_variable_is_read_nowhere` y `test_portal_rls::test_resolution_reads_estimate_that_empty_context_hides`.

No apareció ninguna falla nueva.

## 13. Estado de producción e integración

### 13.1 Incidente: la suite de pruebas tocó producción

Las pruebas que cargan `.env` con `override=True` se conectaron a producción (`crm.rapilinksas.co`, config v146) durante las corridas de la suite del motor en M06-A-corr, B, C y D.

- **Escritura:** `test_aprobacion_documentos` escribió en 5 corridas. En cada una creó el documento `ZZ-TEST-APROBACION` para rapilink, lo aprobó (quedó vigente y recuperable por el asistente durante unos segundos), lo retiró y lo borró. Las 5 salidas muestran "(documento de prueba borrado)". Solo toca `asistente.documents` y `asistente.document_chunks`. **No se verificó en producción que no quedara residuo**, porque no se volvió a conectar.
- **Lectura:** `test_frontera_de_dia` leyó (solo SELECT) y `test_token_servicio` leyó la config. En la 6ª corrida (M06-E), `test_aprobacion_documentos` leyó la config de producción y falló al validarla, antes de escribir.
- **Sin contacto con WispHub:** `test_sondeo` omitió WispHub en todas las corridas por falta de clave. Solo resolvió DNS.

**Las afirmaciones "producción no tocada" de los informes de M06-A-corr, B, C y D eran falsas.** Mitigación aplicada: un runner aislado sin credenciales y la guarda en la prueba que escribe. Pendiente: verificar en producción que no hay filas con `codigo = 'ZZ-TEST-APROBACION'`.

### 13.2 Integración con origin (motivo del NO GO)

Después de `git fetch`:
- `HEAD` está **181 commits detrás** de `origin/fix/integracion-wisphub` (`a0e4d8b`) y 2 delante.
- Origin cambió 319 archivos y **36 se solapan** con este trabajo: `motor.py`, `api.py`, `db.py`, `schema.py`, `http.py`, `forzado.py`, `operativo.py`, `reloj.py`, `coordinador.py`, `importacion_io.py`, los modelos, vistas y serializers de `operaciones`, el YAML del tenant, PRD, CLAUDE.md, DESPLIEGUE.md, `cli/evaluar.py`, la pantalla de conversaciones, entre otros.
- **Los módulos de seguridad de este trabajo nunca se commitearon.** `frontera`, `interruptor`, `idempotencia`, `autonomia2`, `autorizacion`, `techo` y `aprobacion` están sin seguimiento en git. Origin no los tiene, y su `motor.py` no los referencia.
- **Ciclo de aprobación incompatible.** Origin rediseñó `acciones_propuestas` (`202609201400_acciones_legado.sql`, `202609201800_acciones_b5.sql`) con `vence_en`, `clave_equivalencia`, la tabla `acciones_eventos` y una máquina de estados (`pendiente, ejecutando, ejecutada_ok, ejecutada_fallo, aprobada, rechazada, vencida, cancelada, desconocida`). Eso choca con el trigger de inmutabilidad, el sello y el CAS de aprobación de M06-A y M06-C.
- **La config de producción no carga con esta rama.** Producción (v146) ya trae campos que esta rama no conoce (`lee_caso`, `politica`, `aprobacion`, `busca_caso`…), lo que da 840 errores de validación.

Conclusión: el trabajo es internamente consistente y está probado, pero **las migraciones y el ciclo de aprobación son inconsistentes con la rama destino**. Un PR desde este estado rompería el código o las migraciones de origin.

## 14. Pasos para GO y para la habilitación futura

**Para llegar a GO PARA PR:**
1. Crear un worktree o rama nueva desde `origin/fix/integracion-wisphub`. No tocar esta copia.
2. Portar `nucleo/seguridad/*` y los tests M06, y reconciliar la frontera con el ciclo B5 de origin. La aprobación vinculante y el sello se montan sobre `acciones_eventos` y su máquina de estados; no se reemplazan.
3. Renumerar y reescribir las migraciones de M06-A/C sobre el esquema B5. Probarlas en PG descartable junto con las de origin, en orden.
4. Reaplicar las excepciones de M06-E sobre el YAML de origin y correr `cli/diferencias_config.py rapilink` en solo lectura.
5. Correr de nuevo las baterías A–F, la suite del motor aislada, la regresión Django, `makemigrations --check` y los casos dorados `--humo` (con autorización, porque usan el modelo real).
6. Verificar en producción que no quedó residuo de `ZZ-TEST-APROBACION`.

**Después del PR, sin habilitar nada:**
- Decidir antes del deploy de `0007` qué pasa con las novedades históricas.
- Clasificar las 3 escrituras INDETERMINADAS con evidencia. Hasta entonces, el cierre automático de tickets vencidos queda bloqueado.
- Aplicar las migraciones en producción en el orden `202609191430 → 211800 → 211900 → 212000` (o sus equivalentes renumeradas), con `diferencias_config` antes y después.
- La autonomía 2/3 sigue apagada. Subir el techo solo por `cli/autonomia.py --techo N --desde M`, por tenant y con registro.
- Separar los `.env` de desarrollo y de producción para que ninguna prueba pueda volver a alcanzar la base real.
