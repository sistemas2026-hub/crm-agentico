# Paso 10.14 — Integración del código con las barreras de producción

**Fecha:** 17/09/2026

## Resultado: **NO APROBADO. No se desplegó nada.**

La regla de cierre dice que el paso no queda aprobado si **existe cualquier ruta
de acción externa sin kill switch**. La auditoría encontró **cinco**, y no por
lectura: **medidas**, con el ejecutor HTTP sustituido por un contador.

```
PUNTO 12 -- PRUEBA DE BYPASS  (interruptor SIEMPRE detenido)
herramienta de escritura: cancelar_solicitud_servicio (solo_lectura=False)

[ok ]     motor._ejecutar_tool con tenant (con gate)   consultado=1  llamadas=0
[ABIERTA] motor._ejecutar_tool con tenant=None         consultado=0  llamadas=1
[ABIERTA] motor._ejecutar_tool con tenant=''           consultado=0  llamadas=1
[ABIERTA] operativo.responder (comenta el ticket)      consultado=0  llamadas=1
[ABIERTA] operativo.cerrar (cierra el ticket del ISP)  consultado=0  llamadas=1
[ABIERTA] operativo.cerrar_caso_crm (cierra el caso)   consultado=0  llamadas=1

RUTAS ABIERTAS: 5      llamadas externas REALES: 0
```

**Producción intacta:** ledger 50, kill switch **DETENIDO**, autonomía **NO
OPERATIVA**, ningún código desplegado, `DBUSER` sin cambios, **cero llamadas
externas**.

---

## A. Commit — preparado, no desplegado

```
HEAD = 108935f8f8ee1b67eaa65ca84bf08d50a39ed5e0
       108935f  2026-09-15 11:20:57 -0500
rama = fix/integracion-wisphub
```

## B y C. Archivos y diff del alcance

| Archivo | Estado | Cambio |
|---|---|---|
| `nucleo/seguridad/interruptor.py` | **nuevo** | 316 líneas |
| `nucleo/seguridad/idempotencia.py` | **nuevo** | 254 líneas |
| `nucleo/modelo/motor.py` | modificado | +231 |
| `nucleo/persistencia/db.py` | modificado | +447 |
| `nucleo/canales/api.py` | modificado | +117 |
| `nucleo/reloj.py` | modificado | +43 |
| `nucleo/programador/coordinador.py` | modificado | +25 |

Guarda de arquitectura: `test_nucleo_sin_tenants.py` → **OK**.

## D. Call graph — todos los caminos hacia una escritura externa

```
                        ┌─────────────────────────────────────────┐
  responder()  ────────►│ motor._ejecutar_tool                    │
  api /interno ────────►│   F1.1 interruptor.veredicto  ◄── GATE  │──► ejecutor_http
  agendamiento ────────►│   F1.2 idempotencia.ejecutar  ◄── GATE  │
  verificacion ────────►└─────────────────────────────────────────┘
  api candidatos ──────►

  coordinador ─────────► interruptor.veredicto_de_organizacion ◄── GATE ──► claim
  reloj ───────────────► interruptor.veredicto                 ◄── GATE ──► trabajos

  accion aprobada ─────► idempotencia.ejecutar ──► ejecutor_http
                         (sin gate A PROPOSITO: la aprobo un humano)

  api.py:4177 ─────────► operativo.responder ──────────────────────► ejecutor_http
  api.py:967  ─────────► operativo.cerrar_todo ──► cerrar ─────────► ejecutor_http
  api.py:1956 ─────────►                       └─► cerrar_caso_crm ─► ejecutor_http
  api.py:4058 ─────────► operativo.cerrar_vencidas ──► cerrar_todo ─► ejecutor_http
                         ▲
                         └── SIN NINGUN GATE   ◄── LAS RUTAS ABIERTAS
```

**Puntos de llamada de `idempotencia.ejecutar()`: tres, los tres en `motor.py`**
(1522, 1631, 2016). Ningún otro módulo lo importa.

**Llamadas directas a `ejecutor_http` fuera de `motor.py`:**
`api.py` (3033, 3718, 3878), `seguimiento/operativo.py` (88, 118),
`seguimiento/importacion_io.py` (114, 142, 166, 192, 239, 366, 397, 440).

## E. El gate del kill switch — donde SÍ está

| Camino | Dónde | Comportamiento |
|---|---|---|
| `motor._ejecutar_tool` | F1.1, línea 1982 | `raise AutonomiaDetenida` antes de resolver argumentos |
| Ruta de servicio `/interno` | línea 1592 | `raise AutonomiaDetenida` |
| Coordinador del scheduler | `coordinador.py:157` | **antes del claim**; excepción ⇒ `permitido=False` |
| Reloj | `reloj.py:317` | fail-closed; excepción ⇒ no trabaja |

`interruptor.py` es fail-closed por construcción: el **único** camino que
permite es una fila real con `estado='activo'`. Tabla ausente, base caída,
timeout, permiso denegado y «sin fila» **bloquean todos**, cada uno con su
estado propio. No hay caché: cada evaluación va a la base.

## F. El gate de idempotencia

`idempotencia.ejecutar()` es fail-closed ante fallo de base
(`OPERACION_SIN_REGISTRO`) y ante tabla ausente (`REGISTRO_NO_INSTALADO`): en
los dos casos **no llama a `hacer()`**.

> **Pero no consulta el interruptor.** Si otro módulo la invocara directamente,
> ejecutaría la mutación sin pasar por el gate. Hoy **no ocurre** —sus tres
> llamadores están en `motor.py`, los tres detrás del gate o en el camino
> aprobado por un humano—, pero la garantía la sostiene la disciplina de los
> llamadores, no el código. Es lo que el punto 2 pedía documentar.

## G. Pruebas fail-closed — las cuatro suites pasan

| Suite | Resultado |
|---|---|
| `tests/test_interruptor_autonomia.py` | **OK** — detiene lo autónomo, deja pasar lo que se consulta |
| `tests/test_idempotencia_externa.py` | **OK** — una mutación sale una vez |
| `tests/test_timeout_interruptor.py` | **OK** — decide rápido, y con la base caída decide que no |
| `tests/test_alta_tenant_autonomia.py` | **OK** — un tenant nuevo nace detenido, sin duplicar |

Cubren, sobre los caminos con gate, los puntos 3 a 7: acción bloqueada con
`hacer()` = 0 llamadas, tabla ausente, base caída, timeout y permisos.

## H, I, J. Tabla ausente · base caída · timeout

Verificado por esas suites y por el código: `_leer()` atrapa
`BaseException` y devuelve `Veredicto(False, …)` en **todos** los casos —
`sin_instalar`, `desconocido`— sin un solo camino que devuelva `permitido=True`.
Lo mismo en `idempotencia.ejecutar()`.

## K. Permisos — ya verificado contra producción en el Paso 10.13D

`app_backend`: `SELECT` permitido; `INSERT`/`UPDATE`/`DELETE` denegados;
`SET ROLE autonomia_operador` denegado. Medido con `session_user=motor_user`.

## L. Prueba productiva DETENIDO — **no ejecutada**

Los puntos 8, 17 y 18 exigen leer el kill switch contra la tabla real con el
runtime desplegado. **Requieren el deploy, que no ocurrió.** No los simulé ni
los di por buenos.

## M. Idempotencia local — validada en el Paso 10.13D

5/5 casos sobre una copia exacta de producción, con acción local: primera
ejecución 1 llamada, repetida 0, colisión rechazada, concurrencia 1 sola,
reintento sólo explícito. **0 llamadas externas reales.**

## N. Prueba de bypass — **el hallazgo**

| Ruta | Estado | ¿Alcanzable hoy? |
|---|---|---|
| **A** · API → herramienta externa sin gate | **ABIERTA** | **sí** — `api.py:967`, `1956`, `4058`, `4177` |
| **B** · scheduler → externa sin gate | cerrada | gate antes del claim |
| **C** · idempotencia → herramienta sin gate | cerrada *de hecho* | sus 3 llamadores están en `motor.py`; no lo impide el código |
| **D** · coordinador → externa sin gate | cerrada | — |
| **E** · llamada directa desde otro módulo | **ABIERTA** | **sí** — `operativo.py` y `importacion_io.py` |
| **F** · `_ejecutar_tool` con `tenant` vacío | **ABIERTA** | **no hoy** — todos los llamadores pasan `identidad.slug` |

### Las tres rutas alcanzables, con su disparador real

1. **`operativo.cerrar_todo`** — `api.py:967` y `api.py:1956`. Cuando el cliente
   confirma que su caso quedó resuelto, el flujo cierra **el ticket de WispHub
   y el caso del CRM**. Nadie del equipo aprueba esa escritura concreta.
2. **`operativo.cerrar_vencidas`** — `api.py:4058`, un endpoint HTTP. Cierra en
   lote las conversaciones escaladas sin respuesta. **`reloj.py` llama a lo
   mismo *con* gate; el endpoint lo llama sin él.**
   Y **está activo**: `cerrar_sin_respuesta_horas = 36` en la config desplegada
   (0 sería «no hace nada»).
3. **`operativo.responder`** — `api.py:4177`. Copia al ticket del ISP la
   respuesta que escribió un agente humano. **Ésta es discutible**: el texto lo
   escribió una persona, así que la escritura es efecto de un acto humano, no
   del agente. La dejo señalada, no la cuento como autónoma.

### Por qué cuentan como autónomas

Por el criterio que el propio código fija en `motor.py:1580`: *«el requisito de
la fase 1 no habla del autor de la intención sino del efecto: detenida la
autonomía, el motor NO inicia operaciones externas»*. Cerrar un ticket en
WispHub es una operación externa iniciada por el motor.

Y `nucleo/seguimiento/operativo.py` **no importa `interruptor` en ninguna
línea**: no es que el gate falle, es que no existe en ese módulo.

## O. Auditoría del bloqueo

`interruptor.anotar_bloqueo()` escribe en `asistente.audit_log` con tenant,
actor, `accion='accion_autonoma_bloqueada'`, `recurso='herramienta:<nombre>'`,
`resultado='denegado'` y el motivo (`estado: motivo`). El timestamp lo pone la
tabla.

Y no se inventa resultado: cuando el gate corta, `_ejecutar_tool` **levanta
`AutonomiaDetenida`**; el bucle del agente lo traduce a
`{"error": "AUTONOMIA_DETENIDA"}` con `codigo_error`, que está en
`CODIGOS_DE_BLOQUEO`. No se fabrica una respuesta de una acción que no salió.

## P. Health checks — situación actual (sin deploy)

| | |
|---|---|
| `https://crm.rapilinksas.co/` | **HTTP 401** |
| `https://agent.rapilinksas.co/login` | **HTTP 200** |
| Ledger de producción | **50** |
| Kill switch | **`detenido`**, 0 filas `activo` |

## Q. Rollback — definido, no necesario

- **Commit anterior:** `108935f8f8ee1b67eaa65ca84bf08d50a39ed5e0` (nada se
  desplegó, así que es también el actual).
- **Procedimiento:** revertir la imagen al commit anterior y reiniciar el
  servicio. **No se toca la base**: las barreras de la base son independientes
  del código y quedan como están.
- **Criterio de abortar:** cualquier ruta abierta (se cumplió), error de
  importación, health check en rojo.

## R. Incidentes

**Ninguno en producción.** Cero llamadas a WispHub, SmartOLT o cualquier
servicio externo: la prueba de bypass sustituye el ejecutor HTTP por un
contador, y las cuatro suites corren sin base y sin red.

## S. Estado final

| | |
|---|---|
| Código desplegado | **ninguno** |
| Kill switch | **DETENIDO** |
| Autonomía | **NO OPERATIVA** |
| Llamadas externas | **0** |
| `DBUSER` | sin cambios |
| M02 / M03 / M09 | sin cambios |
| WispHub / SmartOLT | sin cambios |
| Producción | estable — ledger 50, servicios respondiendo |

---

## Por qué no desplegué

Desplegar ahora habría instalado una barrera que **parece** cubrir todo y no lo
hace: el motor, el coordinador y el reloj quedarían protegidos, pero el flujo de
conversación seguiría cerrando tickets en WispHub y casos en el CRM con el
interruptor tirado. Un control de seguridad que cubre el 70 % de los caminos y
se anuncia como completo es peor que no tenerlo, porque nadie vuelve a mirarlo.

Estrictamente, desplegar no empeoraría nada —hoy ningún camino consulta el
interruptor—, pero la regla de cierre que usted fijó es explícita y la
demostración que el paso pedía («el código no tiene ningún camino que permita
saltarse la barrera») **falla**.

## Lo que propongo para un paso 10.14A

1. **Hacer incondicional el gate de `_ejecutar_tool`** (ruta F): si la
   herramienta escribe y no hay `tenant`, **bloquear** en vez de ejecutar. Hoy
   no es alcanzable, pero es un fail-open latente de una sola línea.
2. **Meter `operativo.py` detrás del gate** (rutas A y E): `responder`,
   `cerrar`, `cerrar_caso_crm` y `cerrar_vencidas`. Decidir además si el copiado
   de una respuesta humana al ticket cuenta como autónomo — yo diría que no, y
   conviene dejarlo escrito.
3. **Revisar `importacion_io.py`** con el mismo criterio: hoy sólo lo llama el
   reloj (con gate), pero las escrituras están fuera de él.
4. **Cerrar la ruta C por diseño**: que `idempotencia.ejecutar()` exija una
   prueba de que el gate ya corrió, en vez de confiar en que el llamador lo
   hizo.
5. Reauditar, volver a correr esta misma prueba de bypass, y **entonces**
   desplegar.

**Me detengo. No continúo a autonomía 0–1.**
