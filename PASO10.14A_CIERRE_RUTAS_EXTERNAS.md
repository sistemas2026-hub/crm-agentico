# Paso 10.14A — Cierre de todas las rutas de acción externa

**Fecha:** 17/09/2026 · **Producción: NO se desplegó nada.**
Ledger 50 · kill switch **DETENIDO** · 1 fila (la semilla), **0 `activo`** ·
`operaciones_externas` vacía · `DBUSER` sin cambios · **0 llamadas externas**.

## Resultado: **GO técnico**, condicionado a autorización de despliegue.

Las cinco rutas del Paso 10.14 están cerradas, y no una por una: se movió el
control al sitio donde ocurre el efecto.

---

## A. Inventario de efectos externos

Todo el HTTP que sale de `nucleo/` — **24 llamadas, 18 funciones**:

| Módulo · función | Método | Clase |
|---|---|---|
| **`herramientas/http.py::ejecutar` / `_pedir`** | **POST/PUT/PATCH/DELETE + GET** | **el embudo** |
| `herramientas/http.py::ejecutar_asincrono` | GET (sondea la tarea) | C |
| `herramientas/agregado.py::_contar` | GET | C |
| `herramientas/estabilidad.py::resumir` | GET | C |
| `herramientas/incidentes.py::_caidas_simultaneas` · `detectar` · `_detalle_de` | GET | C |
| `herramientas/localidades.py::sincronizar` | GET | C |
| `herramientas/sondeo.py::_pedir` | GET | C |
| `canales/api.py::diagnostico_smartolt` · `_inventario_onu` | GET (SmartOLT) | C |
| `observabilidad/consumo.py::consultar_saldo` | GET | C |
| `seguimiento/escalamiento.py::caso_sigue_abierto` | GET | C |
| `canales/whatsapp.py::plantillas_aprobadas` · `descargar_media` | GET | C |
| `canales/whatsapp.py::_post` · `subir_media` | **POST** | **C — el canal** |

### El hallazgo que define el diseño

**Todas las escrituras de herramientas embudan en un solo sitio:**
`nucleo/herramientas/http.py`, línea 200/202. Los demás `requests.*` del núcleo
son `GET`, salvo WhatsApp — que es el canal, no una acción.

Por eso la frontera no se puso en cinco funciones: se puso en el embudo.
**Un módulo nuevo que escriba afuera pasa por ella aunque no sepa que existe.**

> **WhatsApp queda fuera a propósito.** Mandarle el mensaje al cliente no es una
> acción autónoma: con la autonomía detenida el asistente **sigue atendiendo**,
> y eso es diseño explícito (ver el encabezado de `interruptor.py`). Está en la
> lista permitida con ese motivo escrito; si algún día se decide lo contrario,
> se saca de la lista y la prueba de cobertura lo exige.

## B. Call graph

```
  responder() ─────┐
  api /interno ────┤
  agendamiento ────┼──► motor._ejecutar_tool
  verificacion ────┤      ├─ F1.1 interruptor.veredicto      ◄── gate (se conserva)
  api candidatos ──┘      └─ frontera.autonoma() ──► idempotencia ──┐
                                                                    │
  accion aprobada ──────► frontera.humana(actor, evidencia) ────────┤
                                                                    │
  operativo.responder ──► frontera.puerta(actor?) ──────────────────┤
  operativo.cerrar ─────► frontera.puerta("") = autonoma ───────────┤
  operativo.cerrar_caso_crm ─► autonoma ────────────────────────────┤
  importacion_io (3 escrituras) ─► frontera.puerta(actor?) ─────────┤
                                                                    ▼
                                            ┌──────────────────────────────┐
  cualquier modulo futuro ──────────────────►│ http.ejecutar                │
                                             │  _exigir_frontera()  ◄── LA │
                                             │  frontera.exigir()   FRONTERA│
                                             └──────────┬───────────────────┘
                                                        ▼
                                                  efecto externo

  coordinador ──► interruptor.veredicto_de_organizacion ◄── gate ──► claim
  reloj ────────► interruptor.veredicto                ◄── gate ──► trabajos
```

## C. Clasificación de cada efecto externo

| Camino | Clase | Prueba de autoría |
|---|---|---|
| `motor._ejecutar_tool` (modelo) | **B · autónoma** | ninguna: la decide el agente |
| `/interno/herramienta/<n>` | **B · autónoma** | el servicio no es una persona |
| `ejecutar_accion_aprobada` | **A · humana** | **fuerte** — id de la propuesta que alguien aprobó |
| `operativo.responder` con `autor` | **A · humana** | **media** — el agente escribió el texto; evidencia = el ticket |
| `operativo.responder` sin `autor` | **B · autónoma** | no hay a quién atribuirla |
| `operativo.cerrar` / `cerrar_caso_crm` | **B · autónoma** | las dispara `cerrar_todo`, nadie las aprueba |
| `operativo.cerrar_vencidas` | **D · sistema** | barrido por tiempo |
| `importacion_io` (3) desde el reloj | **D · sistema** | — |
| `importacion_io` (3) desde el CLI | **E · administrativa** | **débil** — el usuario del SO (ver §K) |
| Lecturas (GET) | **C · no es acción** | — |
| WhatsApp | **C · el canal** | — |

## D. La frontera común — `nucleo/seguridad/frontera.py`

Dos puertas, y la diferencia **no es de confianza**: es que en una hay un
responsable con nombre.

| | `autonoma()` | `humana()` |
|---|---|---|
| Consulta el interruptor | **sí** | no |
| Exige tenant válido | **sí** | **sí** |
| Exige actor | no | **sí** |
| Exige evidencia | no | **sí** |

`exigir()` es el último metro, y lo llama el **ejecutor**: una herramienta de
lectura pasa sin preguntar; una de escritura sin permiso vigente **no sale**.

### Cómo se prueba que la autorización ocurrió (punto 5)

Un `ContextVar` **privado** que guarda un `_Permiso` que **solo ese módulo
construye**. No existe un parámetro `autorizado=True`.

Un módulo que haga `idempotencia.ejecutar(...)` por su cuenta recibe:

```
[idempotencia] rapilink: 'reiniciar_ont' llego sin permiso de la frontera. NO se ejecuta.
  -> ejecutada=False  codigo=ACCION_EXTERNA_SIN_AUTORIZAR
  -> ni siquiera se reclamo la operacion en el registro
```

> **Límite, dicho y no escondido:** Python no tiene fronteras reales. Quien
> escriba `frontera._PERMISO.set(frontera._Permiso(...))` se la salta. Lo que el
> diseño impide es el bypass **accidental** —el único que ocurre— y deja el
> deliberado a la vista en el diff: no hay forma de escribirlo que parezca
> inocente.

> **Y un efecto secundario que resultó deseable:** un `ContextVar` **no se
> hereda en un hilo nuevo**. Un trabajo que se manda a un `Thread` no arrastra
> la autorización de quien lo mandó — es fail-closed, y así quedó documentado en
> la prueba de concurrencia.

## E. Cambios

| Archivo | Qué |
|---|---|
| **`nucleo/seguridad/frontera.py`** | **nuevo** — la frontera común |
| `nucleo/herramientas/http.py` | `_exigir_frontera()` al entrar a `ejecutar()` |
| `nucleo/seguridad/idempotencia.py` | exige permiso vigente antes de reclamar |
| `nucleo/modelo/motor.py` | cierra el fail-open de `tenant`; abre la frontera; 3 códigos nuevos |
| `nucleo/seguimiento/operativo.py` | `_permiso()` delega en `frontera.puerta()` |
| `nucleo/seguimiento/importacion_io.py` | `_puerta()` + `actor` en las 3 escrituras |
| `nucleo/seguimiento/forzado.py` | **4** códigos a `CODIGOS_MOTOR_GUARD` |
| `cli/importar_tickets.py` | atribuye la importación a quien la corre |
| `…/conversaciones/[id]/+page.svelte` | 4 motivos en palabras |
| **`tests/test_frontera_externa.py`** | **nuevo** — cobertura + bypass |
| `tests/test_idempotencia_externa.py` | sección 15 nueva; el banco abre permiso |
| `tests/test_escalada_forzada.py` | los gates pasan de 12 a 16 |

### Un defecto viejo que salió al tirar del hilo

`REGISTRO_NO_INSTALADO` (paso 10.10) **faltaba en `forzado.py`** — y también en
la lista del test, así que **las dos coincidían y nadie lo vio**. Lo destapó
`test_bloqueos_en_traza.py` al comparar la lista de `motor.py` contra la de
`forzado.py`, que es exactamente para lo que existe. Sin ese arreglo, ese
bloqueo se contaba como fallo de la herramienta y forzaba una escalada
diciéndole al cliente que se rompió algo que no se rompió.

## F. Tenant obligatorio

```python
# ANTES:  if not (autonoma and tenant): return _despachar()   <- fail-open
# AHORA:  lectura -> pasa;  escritura -> frontera, que exige tenant valido
```

| Caso | Resultado |
|---|---|
| `tenant=None` | **`ACCION_EXTERNA_SIN_TENANT`** — 0 llamadas |
| `tenant=''` | **`ACCION_EXTERNA_SIN_TENANT`** — 0 llamadas |
| `tenant` inexistente | **`AUTONOMIA_DETENIDA (sin_registro)`** — 0 llamadas |
| permiso de otra empresa | **`ACCION_EXTERNA_TENANT_DISTINTO`** — 0 llamadas |

## G · H · I · J · K · L · M — por área

**G · Idempotencia:** ya no es una puerta independiente (§D). Sigue siendo
fail-closed ante base caída y tabla ausente.

**H · Operativo:** las cinco clasificadas (§C). `responder` con actor → humana;
sin actor → autónoma. `cerrar`, `cerrar_caso_crm`, `cerrar_todo` y
`cerrar_vencidas` → autónomas. **`cerrar_vencidas` queda protegida por el mismo
control entre en por el reloj o por el endpoint HTTP**: la protección no está en
el punto de entrada, está en la salida.

**I · API:** todos los endpoints que alcanzan una escritura pasan por el
ejecutor, y el ejecutor exige permiso. No hace falta enumerarlos para
protegerlos — es la propiedad que da poner el control en el embudo.

**J · Scheduler:** el registro de trabajos de producción está **vacío**
(`_PRODUCCION = {}` en `programador/registro.py`): hoy **ningún job puede
producir un efecto externo**. `cerrar_vencidas` está bloqueado ahí a propósito
por no ser idempotente. El gate del coordinador se conserva igualmente.

**K · Importación:** 3 escrituras (`importar_caso_externo`,
`reconciliar_caso_externo`, `sincronizar_respuestas_externas`), todas al CRM.
Desde el reloj → autónomas. Desde `cli/importar_tickets.py` → humanas, con
`actor = "cli:<usuario>"`.
> **Evidencia débil, y lo digo:** el usuario del sistema operativo dice *quién*
> corrió el comando, no *prueba* que fuera una persona — un cron que invoque el
> CLI entraría igual. Lo que queda garantizado es la **atribución**.

**L · Coordinador:** su gate ya no es el único control — converge en la frontera
porque cualquier trabajo que escriba pasa por el ejecutor.

**M · Motor:** el gate F1.1 **se conserva**. Defense-in-depth real: con el
interruptor detenido, el motor corta en F1.1 (`AutonomiaDetenida`) y, si alguien
quitara ese gate, la frontera cortaría igual en el ejecutor.

## N. Pruebas — 83 en verde

Las cuatro suites de barreras siguen pasando, más las nuevas.

## O. Bypass — los diez caminos, medidos

Interruptor **DETENIDO**, `requests` sustituido dentro del ejecutor (corre el
código real, incluida la comprobación):

```
A · ejecutor directo, sin permiso ............ 0 llamadas  ACCION_EXTERNA_SIN_AUTORIZAR
B · motor._ejecutar_tool ..................... 0 llamadas  AutonomiaDetenida
C · motor.ejecutar_para_servicio (/interno) .. 0 llamadas  AutonomiaDetenida
D · operativo.responder sin actor ............ 0 llamadas  AUTONOMIA_DETENIDA
E · operativo.cerrar ......................... 0 llamadas  AUTONOMIA_DETENIDA
F · operativo.cerrar_caso_crm ................ 0 llamadas  AUTONOMIA_DETENIDA
G · idempotencia como puerta suelta .......... 0 llamadas  ACCION_EXTERNA_SIN_AUTORIZAR
H · tenant=None .............................. 0 llamadas  ACCION_EXTERNA_SIN_TENANT
I · tenant='' ................................ 0 llamadas  ACCION_EXTERNA_SIN_TENANT
J · tenant inexistente ....................... 0 llamadas  AutonomiaDetenida

lo que NO debe bloquearse:
  las LECTURAS siguen pasando ................ 1 llamada   (correcto)
  la puerta humana con actor + evidencia ..... 1 llamada   (correcto)
  la puerta humana SIN actor ................. 0 llamadas
  la puerta humana SIN evidencia ............. 0 llamadas
  permiso de 'rapilink' sobre 'otra_isp' ..... 0 llamadas
  al salir del 'with', el permiso caduca ..... 0 llamadas

llamadas externas REALES: 0
```

## P. Cobertura automática

`tests/test_frontera_externa.py` recorre el AST de todo `nucleo/` y **falla si
aparece una llamada HTTP en una función que no esté en la lista permitida** — y
también si la lista tiene entradas muertas, para que no se llene de restos.

> **Límites del método, dichos:** el AST ve lo escrito. **No** ve despacho
> dinámico (`getattr(requests, metodo)`), una librería nueva que nadie declare
> (`httpx`, `aiohttp`, `urllib3`), un subproceso que llame a `curl`, ni código
> fuera de `nucleo/`. Por eso la prueba dinámica existe aparte: **la estática
> dice «no hay caminos nuevos escritos», la dinámica dice «los que hay, frenan»**.

## Q. Pruebas contra base real (réplica) — 9 de 9

Réplica del respaldo **`20260917_163739`** (el estado 50 de producción).
**Es el único sitio donde se puso `ACTIVO`.**

| Escenario | Resultado |
|---|---|
| DETENIDO | **bloquea** — 0 llamadas |
| **ACTIVO** (solo réplica) | **la escritura SÍ sale** — 1 llamada |
| Idempotencia contra la tabla real | primera ejecuta, segunda `repetida` |
| Concurrencia (2 hilos) | **una sola ejecución** |
| Tabla del interruptor ausente | **bloquea** (`sin_instalar`) |
| Tabla de operaciones ausente | **bloquea** (`control_ausente`) |
| Base caída | **bloquea** (`desconocido`) |
| `SELECT` revocado sobre el interruptor | **bloquea** (`desconocido`) |
| Vuelta a DETENIDO | **bloquea** |

**0 llamadas externas reales.**

## R. Restore

El respaldo `20260917_163739` se restauró para construir la réplica: código 0,
ledger 50, rol y segregación intactos. Los tres respaldos se conservan.

## S. Riesgos

1. **Nada de esto está desplegado.** Producción sigue sin consultar la frontera:
   las rutas de `operativo` siguen escribiendo sin gate **hasta que se
   despliegue**. Hoy es tolerable porque `cerrar_sin_respuesta_horas = 36` solo
   actúa sobre conversaciones escaladas sin respuesta, pero es el riesgo vivo.
2. **Al desplegar, el comportamiento cambia con la autonomía DETENIDA**: dejarán
   de cerrarse tickets y casos automáticamente. **Es lo pedido**, pero hay que
   saberlo antes, no descubrirlo.
3. **El CLI de importación quedará bloqueado** si se corre sin actor y la
   autonomía está detenida. Con actor entra por la puerta humana.
4. **La evidencia humana del CLI es débil** (§K).
5. **La frontera no es infalsificable** (§D) — protege del accidente, no del
   sabotaje.
6. **Dos pruebas quedan en rojo, y son previas a este paso**: `test_p2_inerte`
   (nombra `verificar_restauracion.py` y la migración 1705, de los pasos B.7 y
   10.5) y `test_reloj`. **Lo verifiqué midiendo**, no suponiendo: con la
   versión HEAD de `importacion_io.py` `test_reloj` falla **exactamente igual**.

---

# GO / NO-GO

## **GO** para desplegar, cuando usted lo autorice.

| Regla de cierre | Estado |
|---|---|
| Ruta externa autónoma sin autorización | **ninguna** — 10/10 bloqueadas |
| `tenant=None` permite ejecutar | **no** |
| `tenant=''` permite ejecutar | **no** |
| Idempotencia usable como bypass | **no** |
| Endpoint que escriba sin clasificación | **no** — todos pasan por el embudo |
| Scheduler que escriba sin autorización | **no** — 0 jobs registrados, y gate |
| Helper directo al ejecutor | **no** — el ejecutor exige permiso |
| Fallback fail-open | **ninguno** |

**Estado final:** producción intacta · ledger 50 · kill switch **DETENIDO** ·
autonomía **NO OPERATIVA** · ningún código desplegado · `DBUSER` sin cambios ·
M02/M03/M09 sin tocar · WispHub y SmartOLT sin una sola llamada · CRM 401 y
frontend 200.

**Me detengo y espero revisión.**
