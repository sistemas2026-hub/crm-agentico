# M10-A — Gobierno, seguridad y frontera de ejecución

**Fecha:** 2026-09-19
**Veredicto:** **M10-A = GO** — con **1 brecha que es decisión de negocio**, no defecto técnico

---

## 1. GO / NO-GO

# GO

| # | Criterio (§M) | |
|:--:|---|:--:|
| 1 | Los 27 tools están clasificados | **SÍ** — R1–R4, con criterio documentado y guarda contra deriva |
| 2 | La frontera de ejecución está identificada | **SÍ** — `nucleo/seguridad/frontera.py`, y ya existía |
| 3 | Propuesta / autorización / ejecución separadas | **SÍ** — y la separación está **impuesta**, no solo afirmada |
| 4 | Kill switch validado | **SÍ** — 5 suites, todas en verde |
| 5 | Guards reales identificados | **SÍ** — 6 capas, medidas |
| 6 | Brechas documentadas | **SÍ** — §17 |
| 7 | No se inventan permisos | **SÍ** — 0 permisos, 0 tablas, 0 GRANT |
| 8 | M09 continúa sin ejecución | **SÍ** — `ejecutar_propuesta` levanta siempre |
| 9 | B-7 continúa congelado | **SÍ** — runtime sigue siendo `postgres` |
| 10 | Pruebas propias pasan | **SÍ** |
| 11 | Regresión ejecutada | **SÍ** |
| 12 | Producción intacta | **SÍ** |

```
Codigo de produccion modificado ....  0
Archivos creados ...................  1 (una prueba)
Migraciones ... 0   Modelos ... 0   Tablas ... 0   Rutas ... 0   Permisos ... 0
Regresion Django ...................  4437 passed / 1 failed / 19 skipped
Pruebas del motor ..................  6 suites, todas OK
Produccion .........................  SIN CAMBIOS · kill switch DETENIDO
Commit .............................  no
```

**M10-A no cambió una sola línea de código de producción.** Es una auditoría, y
su único artefacto es una prueba que fija la clasificación para que no se
mueva sin que alguien lo decida.

---

## 2. Matriz de los 27 tools

**Primera corrección al punto de partida:** producción tiene **69 herramientas**
(config v146), no 27. Las 27 son las de **escritura**; las otras 42 son solo
lectura.

| # | Herramienta | Tipo | Método | Sistema | Clase | `aprob.` | `previas` |
|:--:|---|---|---|---|:--:|:--:|:--:|
| 1 | `registrar_pedido_wifi` | interno | — | motor | **R1** | no | no |
| 2 | `reportar_comprobante_pago` | interno | — | motor | **R1** | no | no |
| 3 | `proponer_herramienta` | interno | — | motor | **R1** | no | no |
| 4 | `crear_ticket` | http | POST | WispHub | **R2** | **SÍ** | no |
| 5 | `responder_ticket` | http | POST | WispHub | **R2** | **SÍ** | no |
| 6 | `actualizar_estado_ticket` | http | PUT | WispHub | **R2** | **SÍ** | no |
| 7 | `crear_ticket_caso` | http | POST | WispHub | **R2** | no | no |
| 8 | `crear_ticket_instalacion` | http | POST | WispHub | **R2** | no | no |
| 9 | `completar_ticket_instalacion` | http | PATCH | WispHub | **R2** | no | no |
| 10 | `reasignar_ticket_instalacion` | http | PUT | WispHub | **R2** | no | no |
| 11 | `agendar_visita_tecnica` | http | POST | WispHub | **R2** | no | no |
| 12 | `agendar_visita_internet` | http | POST | WispHub | **R2** | no | no |
| 13 | `responder_ticket_operativo` | http | POST | WispHub | **R2** | no | no |
| 14 | `cerrar_ticket_operativo` | http | POST | WispHub | **R2** | no | no |
| 15 | `crear_caso_soporte` | http | POST | BottleCRM | **R2** | no | no |
| 16 | `cerrar_caso_crm` | http | PATCH | BottleCRM | **R2** | no | no |
| 17 | `crear_tag_crm` | http | POST | BottleCRM | **R2** | no | no |
| 18 | `registrar_solicitud_servicio` | http | POST | BottleCRM | **R2** | no | no |
| 19 | `cancelar_solicitud_servicio` | http | POST | BottleCRM | **R2** | no | no |
| 20 | `importar_caso_externo` | http | POST | Importación | **R2** | no | no |
| 21 | `reconciliar_caso_externo` | http | POST | Importación | **R2** | no | no |
| 22 | `sincronizar_respuestas_externas` | http | POST | Importación | **R2** | no | no |
| 23 | **`reiniciar_ont`** | http | POST | SmartOLT | **R3** | no | **SÍ** |
| 24 | **`cambiar_tipo_onu`** | http | POST | SmartOLT | **R3** | no | **SÍ** |
| 25 | **`activar_catv`** | http | POST | SmartOLT | **R3** | no | **SÍ** |
| 26 | **`agregar_promesa_pago`** | http | POST | WispHub | **R4** | **SÍ** | no |
| 27 | **`registrar_pago`** | http | POST | WispHub | **R4** | **no** | **no** |

**Ninguna declara `DELETE`** — verificado. Importa: la API de WispHub **sí**
permite borrar un cliente (`DELETE /api/clientes/{id}/perfil/`, comprobado
end-to-end en su día). La única protección es que el catálogo es **lista
blanca** y borrar no está en ella. Ahora hay una prueba que lo afirma.

---

## 3. Clasificación R0–R4

**El criterio es el EFECTO REAL, no el nombre.** Documentado en el encabezado
de la prueba:

| Clase | Criterio | n |
|:--:|---|:--:|
| **R0** | `solo_lectura=True`. No cambia nada | **42** |
| **R1** | Escribe, pero `tipo=interno`: el motor lo resuelve sin salir a ninguna API | **3** |
| **R2** | Crea o modifica un **registro** externo. Se deshace con otra operación de registro | **19** |
| **R3** | Actúa sobre el **equipo en casa del cliente**. **No se deshace**: un reinicio no se des-reinicia, y mientras tanto el cliente no tiene servicio | **3** |
| **R4** | Altera la **cuenta** del cliente. Revertir un pago no es una llamada de API, es una operación contable | **2** |

**R3 y R4 no están arriba por ser "importantes" en abstracto**: están arriba
porque **su efecto no lo puede deshacer el mismo sistema que lo produjo.** Ese
es el criterio entero.

---

## 4. Guards actuales — las seis capas reales

| # | Capa | Qué controla | Dónde | ¿Conectada al punto de ejecución? |
|:--:|---|---|---|:--:|
| 1 | **`roles_permitidos`** | quién puede pedirla | config por herramienta | sí, en el motor |
| 2 | **Listas blancas de campos** | qué datos salen | `nucleo/seguridad/listas_blancas.py` | sí |
| 3 | **`exige_previas`** | condiciones técnicas antes de actuar | 3 herramientas R3 | sí |
| 4 | **`aprobacion_humana`** | la escritura **no se ejecuta**: se guarda en `acciones_propuestas` | 4 herramientas | sí |
| 5 | **Interruptor de autonomía** | apaga todo lo autónomo, por tenant | `asistente.interruptor_autonomia` | sí |
| 6 | **Frontera de efecto externo** | **el último metro** antes del POST/PUT/PATCH | `nucleo/seguridad/frontera.py` | **sí — es el punto mismo** |

**La capa 6 es la que hace que las demás no sean lo único.** Su propio
encabezado explica por qué existe:

> *"El paso 10.14 midió CINCO caminos que llegaban a escribir en WispHub o en
> el CRM sin pasar por [motor.py]. Ninguno era un descuido grande; todos eran
> código razonable escrito en otro archivo, que simplemente no sabía que
> existía un gate. Agregar el interruptor a esas cinco funciones habría cerrado
> esas cinco. **La sexta la escribe alguien el mes que viene.**"*

Por eso el control vive **donde ocurre el efecto** y lo comprueba el propio
ejecutor (`nucleo/herramientas/http.py:176-177`). Un módulo nuevo que quiera
escribir afuera pasa por ahí **aunque no sepa que existe**.

**Y el diseño declara su propio límite, sin adornarlo:**

> *"LÍMITE HONESTO: Python no tiene fronteras de verdad. Quien escriba
> `frontera._PERMISO.set(...)` se salta esto. Lo que el diseño impide es el
> bypass ACCIDENTAL —el único que ocurre en la práctica— y deja el deliberado a
> la vista de cualquiera que lea el diff."*

---

## 5. Guards faltantes

| # | Falta | Consecuencia hoy | Consecuencia si se activa autonomía |
|:--:|---|---|---|
| 1 | **Autorización granular por herramienta** | ninguna: el interruptor está detenido | **crítica** — nivel 3 habilitaría las 27 a la vez |
| 2 | **Gate propio en `registrar_pago`** (R4) | ninguna | **crítica** — dinero sin aprobación por operación |
| 3 | **Gate propio en las 3 R3** | ninguna | **alta** — equipo del cliente sin aprobación |
| 4 | **Niveles en el interruptor** | ninguna: hoy es binario | media — no se puede permitir R2 y frenar R4 |
| 5 | **Segregación de identidad runtime (B-7)** | media — el CRM corre como `postgres` | **crítica** |

---

## 6. Aprobación humana — números revalidados

§C pedía revalidar sobre el código actual. **Dos de los cuatro números
cambiaron:**

| | Auditoría previa | **Medido hoy (v146)** |
|---|---:|---:|
| Tools con `aprobacion_humana` | 4/27 | **4/27** ✓ |
| Tools con `exige_previas` | 3/27 | **3/27** ✓ |
| Tools "críticos" | 12 | **5** (3 R3 + 2 R4), con el criterio de §3 |
| **Escrituras sin ninguna de las dos** | **8** | **20** |

**20, no 8.** El catálogo creció y las barreras no.

### El hallazgo que M10-A existe para dejar por escrito

**Las barreras declaradas no están alineadas con el riesgo:**

```
clase   n   aprobacion_humana   exige_previas   sin ninguna
R1      3           0                 0              3
R2     19           4                 0             15
R3      3           0                 3              0
R4      2           1                 0              1   <--
```

Las **4** con `aprobacion_humana` son **todas R2** — operaciones de ticket. Y
`registrar_pago`, la única herramienta que mueve **dinero** sin barrera propia,
no la tiene.

**Esto no es un defecto de diseño.** `aprobacion_humana` es **opt-in** y nació
de un caso concreto el 18/08/2026 (crear/responder/actualizar tickets de
WispHub): quedó donde ese caso la pidió. Así crece un gate opt-in. Lo que M10-A
aporta es **medirlo y nombrarlo**, no repararlo por cuenta propia — §C prohíbe
expresamente convertir esto en *"todos los críticos necesitan
aprobacion_humana=True"*.

### `requiere_confirmacion` NO es una barrera

**Las 27 escrituras lo declaran.** El validador lo exige para poder guardarse y
**nunca se evalúa en ejecución** — lo dice el schema y lo confirma
`interruptor.es_accion_autonoma`, que mira `solo_lectura` a propósito. Un campo
que está en el 100% de las escrituras no distingue nada. **Hay una prueba que
lo afirma**, para que nadie lo confunda con autorización.

---

## 7. Autonomía mínima / máxima

**`autonomy_level` = TECHO, no autorización.** Verificado en código:

| Clase | Nivel mínimo compatible | Nivel máximo recomendado hoy |
|:--:|---|---|
| **R0** | 0 · Observar | 4 |
| **R1** | 1 · Recomendar | 2 · Coordinar |
| **R2** | 2 · Coordinar | 2 — con aprobación humana por operación |
| **R3** | 3 · Ejecutar reversible | **1** hasta que exista autorización granular |
| **R4** | 4 · Crítico, siempre humano | **1** — nunca autónoma |

**El agente no puede elevarse de nivel ni concederse permisos**: el estado vive
en `asistente.interruptor_autonomia`, se lee **sin caché** antes de cada
escritura y **falla cerrado**. No hay ruta en el código que lo escriba desde el
lado del agente.

**Y una propuesta aprobada no se convierte en ejecución**: la única ruta
declarada, `supervisor.ejecutar_propuesta`, **levanta siempre**.

---

## 8. Kill switch

**No se tocó.** Se validó con las 5 suites que ya existían — **todas en verde**:

| §F | Comprobación | Resultado |
|:--:|---|---|
| 1 | Estado detenido | **detenido** desde 2026-09-17, actor `migracion` |
| 2 | Fail-closed | **sí** — *"la ausencia de control nunca es autorización"* |
| 3 | Consulta antes del efecto autónomo | **sí** — `frontera.autonoma()` lo consulta |
| 4 | Sin ejecución cuando está detenido | **sí** — `test_interruptor_autonomia` |
| 5 | Lo manual sigue | **sí** — `frontera.humana()` **no** lo consulta, a propósito |
| 6 | Auditoría del cambio | **sí** — actor y motivo obligatorios, sin default |
| 7 | Aislamiento por tenant | **sí** — por slug y por `organization_id` |
| 8 | DB caída / timeout | **sí** — `test_timeout_interruptor`: *"con la base caída decide que no"* |
| 9 | Scheduler / reintentos | **sí** — `programador/puerta.py` usa `veredicto_de_organizacion`, y sus 3 roles **no tienen GRANT sobre tablas** |
| 10 | Independiente de `max cost` | **sí** — son gates distintos |

**No se encontró ningún defecto. Queda intacto.**

---

## 9. PropuestaSupervisor — y las DOS colas que no se deben mezclar

**[MEDIDO] En producción hay dos colas, con semánticas opuestas:**

| | `asistente.acciones_propuestas` | `operaciones_propuesta_supervisor` |
|---|---|---|
| **Dueño** | motor (Fase 1) | M09 (Django) |
| **Filas** | **40** — 36 pendientes, 4 aprobadas | **0** |
| **Qué contiene** | **acciones esperando ejecutarse** | **recomendaciones esperando revisarse** |
| **Al aprobar** | **SE EJECUTA** contra WispHub | **NO se ejecuta nada** |
| **Gate** | `aprobacion_humana=True` | revisión del Jefe de Operaciones |

**Aprobar una `accion_propuesta` ejecuta. Aceptar una `PropuestaSupervisor` no.**
Fusionarlas convertiría una recomendación en una orden de ejecución — y es
exactamente lo que §E y §I prohíben.

`PropuestaSupervisor` auditada: evidencia obligatoria (servicio **+** CHECK en
base), `propuesta_original`, deduplicación por huella, expiración, revisión
humana, 6 estados, concurrencia serializada por organización (M09-L),
trazabilidad en `common.Activity` con `actor=None` para distinguir a la IA.

```
PROPUESTA  !=  AUTORIZACION  !=  EJECUCION
```

Los tres están separados **y la separación está impuesta**, no solo escrita.

---

## 10. Autorización granular

**[MEDIDO] No existe.** El esquema `asistente` tiene 37 tablas; **ninguna** es
de autorización (`%autoriz%` → 0).

Lo que existe hoy y hace un trabajo parcial: `roles_permitidos` (por rol, no
por sujeto), `aprobacion_humana` (por herramienta, binario, 4 de 27),
`interruptor_autonomia` (por tenant, binario).

**No se implementó nada** — §G dice documentar el diseño antes de implementarlo,
y M10-A no lo necesita para cerrar. **El diseño exacto, para cuando se
autorice:**

```sql
-- APPEND-ONLY. Una autorizacion no se edita: se revoca con otra fila.
CREATE TABLE asistente.autorizaciones_herramienta (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant          text        NOT NULL,
    herramienta     text        NOT NULL,
    sujeto_tipo     text        NOT NULL,   -- 'rol' | 'usuario' | 'agente'
    sujeto          text        NOT NULL,
    nivel_maximo    smallint    NOT NULL,   -- techo, no autorizacion
    estado          text        NOT NULL,   -- 'vigente' | 'revocada'
    vigente_desde   timestamptz NOT NULL DEFAULT now(),
    vigente_hasta   timestamptz,            -- null = sin vencimiento
    otorgada_por    text        NOT NULL,   -- sin default: nadie anonimo
    motivo          text        NOT NULL,
    creado_en       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON asistente.autorizaciones_herramienta
    (tenant, herramienta, estado, vigente_hasta);
```

**Tres decisiones del diseño, con su razón:**

1. **Append-only**: revocar es insertar, no actualizar. Así el historial no se
   puede perder por un `UPDATE` mal escrito — mismo criterio que
   `interruptor_autonomia`.
2. **`SECURITY DEFINER` + sin `GRANT` sobre la tabla**: el runtime lee por
   función, nunca por SQL directo — el patrón que `programador/puerta.py` ya
   usa y explica.
3. **Se consulta en `frontera.autonoma()`**, junto al interruptor. Ponerla en
   los llamadores repetiría el error que la frontera existe para no repetir.

**No se usó `tenant_config.requiere_confirmacion` como sustituto** (§G lo
prohíbe, y §6 explica por qué no serviría).

---

## 11. Frontera de efecto externo

```
Supervisor  ->  propuesta      (PropuestaSupervisor, NO ejecuta)
                    |
                    v
             revision humana   (Jefe de Operaciones)
                    |
                    v
               [ AUTORIZACION -- hoy: interruptor + aprobacion_humana ]
                    |
                    v
                  tool         (motor)
                    |
                    v
         +-----------------------+
         |  frontera.exigir()    |   <-- el ultimo metro
         +-----------------------+
                    |
              POST / PUT / PATCH
```

**La llamada externa es imposible sin un permiso vigente en el contexto**, y el
único modo de ponerlo ahí es entrar por una de las dos puertas:

- **`autonoma()`** — nadie la pidió. **Consulta el interruptor.** Sin tenant
  válido, o con el interruptor detenido, o si no se pudo leer: **no abre**.
- **`humana()`** — una persona concreta la decidió. **No** consulta el
  interruptor —detener la autonomía no puede impedirle trabajar a un operador—
  pero **exige actor y evidencia**. Sin las dos, no abre.

*"La diferencia no es de confianza: es que en `humana()` hay un responsable con
nombre, y queda anotado."*

**Verificado en vivo** (`test_frontera_externa`, `test_frontera_adversarial`):
**0 llamadas externas reales**; los intentos por hilos, async, pools, permisos
falsificados y kwargs públicos **quedaron todos bloqueados**.

---

## 12. Auditoría

Para una futura ejecución autónoma, ya se puede reconstruir:

| §I pide | Dónde está |
|---|---|
| tenant · actor · tool · timestamp | `asistente.audit_log`, `tool_calls` |
| argumentos sin secretos | `tool_calls` guarda **metadatos**, no respuestas crudas |
| autorización | `interruptor_autonomia` (transiciones) + `acciones_propuestas` |
| propuesta · aprobación | `PropuestaSupervisor` + `common.Activity` |
| resultado · error | `tool_calls`, `job_run`, `job_attempt` |
| idempotency key · origen | `asistente.operaciones_externas` (clave = `origen\|herramienta\|hash(args resueltos)`) |
| estado anterior/posterior | `common.Activity.metadata` |

**No se almacenan secretos** — decisión ya tomada: las respuestas crudas de
WispHub **no se persisten** porque traen contraseñas, GPS y cédula.

**No se duplicó `common.Activity`**: el motor ya tiene `audit_log` y
`tool_calls`, cada uno en su dominio.

---

## 13. Pruebas propias

**Creado: 1 archivo, 315 líneas** — `tests/test_m10a_gobierno_frontera.py`,
en el estilo de las pruebas del motor. **10 secciones, todas en verde.**

No agrega un control nuevo: **fija la clasificación y comprueba que el catálogo
no se mueva sin que alguien lo decida** — el mismo mecanismo que el inventario
de rutas de M09-F, que ya cazó cuatro rutas nuevas en los últimos pasos.

| Sección | Qué afirma |
|:--:|---|
| 1 | Toda escritura está clasificada, y la clasificación no nombra fantasmas |
| 2 | Ninguna lectura aparece como escritura, y la frontera coincide |
| 3 | La frontera cubre **las 27** |
| 4 | **Ninguna herramienta declara `DELETE`** |
| 5 | Ninguna R3/R4 es invocable por la ruta interna de servicio |
| 6 | Las 3 R3 conservan sus previas; la brecha R4 se **reporta sin romper** |
| 7 | `requiere_confirmacion` está en el 100% → no puede ser autorización |
| 8 | Autonomía es techo: una escritura cuenta como autónoma, y deja de serlo con humano detrás |
| 9 | La frontera **no se abre sola**: sin actor, sin evidencia o sin tenant, no abre |
| 10 | La matriz completa |

**La prueba corre sin base de datos** — es reproducible y no toca producción.

### Cobertura de los 24 escenarios de §K

| §K | Cubierto por |
|:--:|---|
| 1, 2, 7, 19 | `test_frontera_externa` · `test_frontera_adversarial` · §9 de M10-A |
| 3, 4 | `test_interruptor_autonomia` (cola `acciones_propuestas`) |
| 5 | `test_interruptor_autonomia` (previas de R3) |
| 6, 14 | §8 de M10-A + `interruptor.es_accion_autonoma` |
| 8, 9 | `test_interruptor_autonomia` · `test_timeout_interruptor` |
| 10 | `test_frontera_adversarial` (tenant distinto) |
| 11, 12, 13 | M09-L `test_7`, `test_9_10_11` · M09-M `test_10`, `test_11` |
| 15 | `nucleo/seguridad/idempotencia.py` + `test_interruptor_autonomia` |
| 16 | M09-L `test_23` · M09-M `test_habilidades` |
| 17, 18 | `test_timeout_interruptor` · `job_attempt` |
| 20 | M09-M `test_14` (AST) + `ejecutar_propuesta` levanta |
| 21–24 | Regresión Django completa |

---

## 14. Regresión

```
Motor   6 suites, todas OK:
        test_interruptor_autonomia · test_frontera_externa
        test_frontera_adversarial  · test_timeout_interruptor
        test_frontera_de_dia       · test_nucleo_sin_tenants
        + test_m10a_gobierno_frontera (nueva)

Django  4437 passed · 1 failed · 19 skipped      (22m 23s)
```

**Idéntica a M11**, como corresponde: M10-A **no modificó código de
producción**. El único fallo es `test_portal_rls`, categoría entorno, ya
reproducida y clasificada cuatro veces.

**Atribuibles a M10-A: 0.**

---

## 15. Producción

# SIN CAMBIOS

Solo `SELECT`, `read_only = True`. **18 claves → DIFERENCIAS: NINGUNA.**

**Estado de gobierno, medido hoy:**

```
kill switch ................. DETENIDO  (desde 2026-09-17, actor 'migracion')
identidad runtime del CRM ... postgres            <-- dependencia de B-7
operaciones_externas ........ 0    (ningun efecto externo ejecutado nunca)
acciones_propuestas ......... 40   (36 pendientes, 4 aprobadas)
PropuestaSupervisor ......... 0
revisiones_supervisor ....... 16
tablas de autorizacion ...... 0
tenant_config ............... v146  (69 herramientas: 42 lectura + 27 escritura)
```

**Lo que se comprobó en entorno aislado:** la regresión Django completa (4437
pruebas) en contenedores sin credenciales de producción.

**Lo que se comprobó contra producción:** únicamente lecturas — el catálogo de
herramientas, el estado del interruptor, los conteos de las colas y la
identidad de runtime.

**[HALLAZGO COLATERAL]** `cli/diferencias_config.py` reporta **1 divergencia**
en la dirección peligrosa: `importacion_tickets.cada_horas` — el repo declara
**0** y producción tiene **1**. Es un trabajo programado corriendo cada hora que
el repo cree apagado. **Está gobernado**: el scheduler pasa por
`veredicto_de_organizacion` y sus roles no tienen `GRANT` sobre tablas. Es
preexistente y no de M10-A, pero queda anotado porque es exactamente la clase
de deriva que este bloque existe para ver.

---

## 16. B-7

**NO se ejecutó. NO se tocó. Sigue congelado.**

```
CRM backend (Django) ...... postgres      <-- medido hoy
Motor ..................... motor_user
```

**Como dependencia, sin más:** para autonomía 2+ la identidad de runtime del
CRM debe quedar segregada de `postgres`. Mientras el CRM corra como `postgres`,
atraviesa RLS por `BYPASSRLS` y cualquier control de base es decorativo para
él.

No se cambió `DBUSER`, no se creó `crm_migrator`, no se modificaron permisos.

---

## 17. Brechas

| # | Brecha | Gravedad **hoy** | Gravedad **con autonomía 2+** |
|:--:|---|:--:|:--:|
| 1 | **`registrar_pago` (R4) sin barrera propia** | **ninguna** | **crítica** |
| 2 | **Las 3 R3 sin aprobación humana** (tienen previas técnicas, que no son autorización) | ninguna | **alta** |
| 3 | **No existe autorización granular** | ninguna | **crítica** |
| 4 | **Interruptor binario**, sin niveles | ninguna | media |
| 5 | **B-7**: runtime = `postgres` | media | **crítica** |
| 6 | **36 `acciones_propuestas` pendientes** sin revisar | baja | media |
| 7 | **20 de 27 escrituras sin barrera propia** | ninguna | **alta** |
| 8 | `importacion_tickets.cada_horas`: repo 0, producción 1 | baja | media |

**Las siete primeras dicen "ninguna" hoy por una sola razón: el interruptor
está detenido y la frontera cubre las 27.** Eso es una defensa real, y es
también la razón por la que activar autonomía sin cerrar las brechas 1–3 sería
un salto, no un paso.

---

## 18. Decisiones pendientes

Ninguna bloqueó este bloque. **Tres son de negocio y no las tomo:**

1. **¿Quién autoriza un `registrar_pago`?** Es la brecha 1. Poner
   `aprobacion_humana=True` es un cambio de config de una línea; **decidir que
   el dinero exige aprobación por operación es del negocio.**
2. **¿Las 3 R3 exigen aprobación humana además de sus previas?** Reiniciar la
   ONU de un cliente le corta el servicio 1–2 minutos. Hoy basta con que se
   cumplan las condiciones técnicas.
3. **¿Se implementa la autorización granular (§10) antes de subir de nivel?**
   El diseño está escrito; implementarlo es un bloque propio.

Y dos técnicas, ya identificadas antes: **B-7** y los **niveles del
interruptor**.

---

## 19. Recomendación técnica del siguiente bloque

**No recomiendo avanzar a autonomía 2+ todavía**, y la razón es concreta: hoy
el interruptor es lo único que separa "27 herramientas gateadas" de "27
herramientas ejecutables". Subir de nivel sin autorización granular convertiría
un interruptor binario en la única decisión entre un `registrar_pago`
automático y ninguno.

**El orden que propongo, con su porqué:**

1. **M10-B — autorización granular.** Es la única de las tres brechas críticas
   que no depende de una decisión de negocio: el diseño está en §10, es
   append-only, no toca ninguna tabla existente y se consulta en el mismo sitio
   que el interruptor. Sin ella, las decisiones 1 y 2 de §18 no tienen dónde
   expresarse más que como un booleano por herramienta.

2. **Las decisiones de negocio de §18.1 y §18.2** — en paralelo, porque no
   requieren código.

3. **B-7** — antes de cualquier nivel 2+, no después. Mientras el CRM corra
   como `postgres`, todo control en base es decorativo para él.

4. **Niveles en el interruptor** — solo tiene sentido cuando exista
   autorización por herramienta que los use.

**Lo que NO recomiendo:** poner `aprobacion_humana=True` a las 20 escrituras
sin barrera. Sería el reflejo obvio y el error que §A advierte —*"NO agregar
guards indiscriminadamente"*—: 20 colas de aprobación que nadie revisa
producen exactamente lo que ya se ve en producción, **36 acciones pendientes
sin mirar**, y un gate que nadie atiende termina desactivándose.

---

```
codigo de produccion ..... 0 archivos     pruebas ... 1 creada (315 lineas)
migraciones 0 · modelos 0 · tablas 0 · rutas 0 · permisos 0 · GRANT 0
kill switch .............. NO tocado (validado con 5 suites, todas OK)
frontera ................. NO tocada (ya existia y cubre las 27)
B-7 ...................... CONGELADO     autonomia ... DETENIDA
produccion ............... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado .......... eliminado
commit ... no     despliegue ... no     B-7 / autonomia 2+ ... no
```
