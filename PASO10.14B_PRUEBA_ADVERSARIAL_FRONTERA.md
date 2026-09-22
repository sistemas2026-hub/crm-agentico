# Paso 10.14B — Prueba adversarial de la frontera externa

**Fecha:** 17/09/2026 · **Producción intacta.**
Ledger 50 · kill switch **DETENIDO** · 1 fila, **0 `activo`** ·
`operaciones_externas` **0** · `audit_log` bloqueos **0** · `DBUSER` sin
cambios · sin migraciones nuevas · **0 llamadas externas reales**.

## Resultado: **GO. Ningún bypass real.**

**20 rutas autónomas probadas → 0 llamadas externas.**
Prueba reproducible: `py -3.13 tests/test_frontera_adversarial.py`

---

## 1. Inventario adversarial

| Origen | Camino hasta el efecto | Tipo |
|---|---|---|
| Motor (modelo) | `_ejecutar_tool` → frontera → idempotencia → ejecutor | **B** |
| Motor (`/interno`) | `ejecutar_para_servicio` → frontera → ejecutor | **B** |
| Motor (acción aprobada) | `ejecutar_accion_aprobada` → `frontera.humana` → ejecutor | **A** |
| Operativo | `responder`/`cerrar`/`cerrar_caso_crm`/`cerrar_todo`/`cerrar_vencidas` → `puerta()` → ejecutor | **B** (sin actor) / **A** (con actor) |
| Importación | `aplicar`/`aplicar_reconciliacion`/`sincronizar_respuestas` → `_puerta()` → ejecutor | **B** (reloj) / **D** (CLI) |
| Scheduler | coordinador → gate → claim → **0 jobs registrados** | **C** |
| API | toda ruta que escribe desemboca en el ejecutor | según su llamador |
| CLI | `importar_tickets.py` con `actor="cli:<usuario>"` | **D** |
| Herramientas | `agregado`/`incidentes`/`sondeo`/`localidades`/`estabilidad` — `GET` | **C** |
| Ejecutor HTTP | **el embudo**: exige permiso antes de cualquier escritura | — |
| Hilos / pools / async | ver §3 | — |
| WhatsApp | mandar el mensaje al cliente | **C — el canal** |

**No se mezcla actor humano con autorización autónoma:** son dos puertas
distintas (`humana()` / `autonoma()`) y el permiso guarda cuál se usó.

## 2. Pruebas de bypass — la matriz

Interruptor **DETENIDO**. `requests` sustituido **dentro** del ejecutor: corre
el código real, incluida la comprobación; sólo no viaja por la red.

| Ruta | Tipo | ¿Bypass? | Kill switch | Tenant | Idemp. | Ext. | Resultado |
|---|---|---|---|---|---|---|---|
| `ejecutor_http.ejecutar` directo | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| `ejecutor_http.ejecutar_asincrono` directo | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| ejecutor con `tenant=None` | B | **no** | — | (vacío) | — | **0** | BLOQUEADO |
| `motor._ejecutar_tool` (modelo) | B | **no** | detenido | rapilink | sí | **0** | BLOQUEADO |
| `motor._ejecutar_tool` `tenant=None` | B | **no** | — | (vacío) | — | **0** | BLOQUEADO |
| `motor._ejecutar_tool` `tenant=''` | B | **no** | — | (vacío) | — | **0** | BLOQUEADO |
| `motor._ejecutar_tool` tenant inexistente | B | **no** | sin_registro | isp-fantasma | — | **0** | BLOQUEADO |
| `motor.ejecutar_para_servicio` (`/interno`) | B | **no** | detenido | rapilink | sí | **0** | BLOQUEADO |
| `threading.Thread` **fuera** del permiso | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| `threading.Thread` **dentro** del permiso | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| `ThreadPoolExecutor.submit` dentro del permiso | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| `asyncio.run` **fuera** del permiso | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| dict cualquiera puesto donde va el permiso | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| módulo nuevo que ignora la frontera | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| `operativo.responder` SIN actor | B | **no** | detenido | rapilink | — | **0** | BLOQUEADO |
| `operativo.cerrar` | B | **no** | detenido | rapilink | — | **0** | BLOQUEADO |
| `operativo.cerrar_caso_crm` | B | **no** | detenido | rapilink | — | **0** | BLOQUEADO |
| `operativo.cerrar_todo` (los tres lados) | B | **no** | detenido | rapilink | — | **0** | BLOQUEADO |
| `importacion_io.aplicar` SIN actor | B | **no** | detenido | rapilink | — | **0** | BLOQUEADO |
| `idempotencia.ejecutar` como puerta suelta | B | **no** | — | rapilink | — | **0** | BLOQUEADO |
| **lectura** con el interruptor tirado | C | n/a | no aplica | rapilink | — | 1 | ejecutado ✔ |
| `asyncio.run` **dentro** del permiso | A | n/a | no aplica | rapilink | — | 1 | ejecutado ✔ |
| puerta humana con actor + evidencia | A | n/a | no aplica | rapilink | — | 1 | ejecutado ✔ |
| `operativo.responder` CON actor | A | n/a | no aplica | rapilink | — | 1 | ejecutado ✔ |
| `importacion_io.aplicar` CON actor (CLI) | D | n/a | no aplica | rapilink | — | 1 | ejecutado ✔ |
| puerta humana sin actor / sin evidencia / actor en blanco | A | **no** | — | rapilink | — | **0 ×3** | BLOQUEADO |

**Rutas autónomas: 20 · llamadas externas: 0.**

### Lo que se midió sobre el contexto, y no se supuso

| | Resultado |
|---|---|
| `threading.Thread` | **no hereda** el contexto → bloquea |
| `ThreadPoolExecutor` | **no hereda** → bloquea |
| `asyncio.run` | **sí copia** el contexto → la corutina hereda el permiso |

> **`asyncio` es la única que hereda, y hay que decirlo.** No es un agujero —el
> permiso lo abrió alguien legítimamente y la corutina corre dentro de ese
> bloque— pero sí es una diferencia real de comportamiento entre hilos y tareas
> async que conviene conocer antes de escribir código async que escriba afuera.

## 3. Ruta nueva que no conoce la frontera

```python
def modulo_nuevo_ingenuo(config, tenant, servicio):
    """Lo que escribiria alguien que no leyo nada de esto."""
    from nucleo.herramientas import http as ejec
    herr = next(h for h in config.herramientas
                if h.tipo == "http" and not getattr(h, "solo_lectura", True))
    return ejec.ejecutar(herr, {"servicio": servicio}, tenant)
```

No menciona `frontera`, ni `interruptor`, ni `idempotencia`.

**Resultado: `AccionExternaNoAutorizada`, 0 llamadas externas.**

Es la prueba que importa: **la protección está en la frontera, no en los
llamadores conocidos.**

## 4. Ruta humana legítima

| | |
|---|---|
| Puerta humana con actor + evidencia | **ejecuta** |
| `operativo.responder` con actor (agente) | **ejecuta** |
| `importacion_io.aplicar` con actor (CLI) | **ejecuta** |
| Sin actor / sin evidencia / actor en blanco | **bloquea** — 3 de 3 |

Ninguna necesitó simular autonomía. El permiso queda con
`tenant`, `clase=humana`, `actor` y `evidencia`.

## 5. Idempotencia

`tests/test_idempotencia_externa.py` — **15 secciones, todas en verde**:

| | |
|---|---|
| Ejecuta una sola vez | sí |
| Repetición con la misma clave | no vuelve a ejecutar; devuelve lo de la primera |
| Misma clave + argumentos distintos | **`CLAVE_REUTILIZADA`** |
| Concurrencia (2 hilos) | **una sola ejecución** |
| Un fallo no se convierte en éxito | queda `fallida`, la excepción se re-levanta |
| Reintento | **sólo explícito** (`reintentar_fallida=True`) |
| Sin permiso de la frontera (sección 15, nueva) | **no ejecuta, ni siquiera reclama** |

Y contra base real (réplica, 10.14A §Q): la segunda no repite, y dos hilos
producen **una sola** ejecución.

## 6. Call graph

```
caller ──► frontera ──► autorización ──► kill switch ──► tenant ──► idempotencia ──► HTTP
```

| Caller | H/A | Permitido | Razón |
|---|---|---|---|
| motor (modelo) | **A**utónomo | **bloqueado** | interruptor detenido |
| motor `/interno` | autónomo | **bloqueado** | ídem |
| motor acción aprobada | **humano** | permitido | actor + id de la propuesta |
| operativo con actor | **humano** | permitido | lo escribió un agente |
| operativo sin actor | autónomo | **bloqueado** | sin responsable a quien atribuirla |
| importación (reloj) | autónomo | **bloqueado** | interruptor detenido |
| importación (CLI) | administrativo | permitido | `actor="cli:<usuario>"` |
| coordinador | autónomo | **bloqueado** | gate + 0 jobs registrados |
| lecturas | — | permitido | no son acciones |
| módulo desconocido | autónomo | **bloqueado** | sin permiso, no sale |

## 7. ContextVar — se conserva, y estos son sus límites

| Afirmación | Medido |
|---|---|
| No existe `autorizado=True` público | **`TypeError: ejecutar() got an unexpected keyword argument 'autorizado'`** |
| `frontera.exigir` tampoco lo acepta | **`TypeError`** |
| Un dict cualquiera no sirve de permiso | **bloqueado** |
| El contexto **no** se hereda a `Thread`/pool | **bloqueado** |
| No hay vía pública para obtener un permiso | confirmado |
| Manipulación deliberada | **funciona, y se ve** |

```python
frontera._PERMISO.set(frontera._Permiso(...))   # SI funciona
```

**Está declarado, no escondido.** Hacen falta **dos nombres privados en la misma
línea**: no se escribe por accidente ni pasa desapercibido en un diff. Lo que el
diseño impide es el bypass **accidental**, que es el único que ocurre en la
práctica; el deliberado requiere que alguien lo escriba a propósito y lo firme.

## 8. Auditoría — qué queda registrado

**Acción bloqueada** (`asistente.audit_log`):

```
organization_id  8a0a07ac-ab84-4dc5-af30-c50afd8cc1a9
actor            motor
accion           accion_autonoma_bloqueada
recurso          herramienta:cancelar_solicitud_servicio
resultado        denegado
motivo           detenido: Estado inicial al crear el interruptor
creado_en        2026-09-17 22:17:01+00
```

**Acción permitida** (`asistente.operaciones_externas`, réplica con ACTIVO):

```
organization_id  8a0a07ac-…
clave            wamid.AUDIT.10.14B|cancelar_solicitud_servicio|44136fa355b3678a
herramienta      cancelar_solicitud_servicio
origen           wamid.AUDIT.10.14B          <- la SOLICITUD real, no inventada
argumentos_hash  44136fa355b3678a1146ad16f7e8649e94fb4fc21fe7…
estado           exitosa       intentos 1    creado_en 2026-09-17 22:17:01+00
```

**No se fabrican datos:** con el interruptor detenido, `_ejecutar_tool`
**levanta `AutonomiaDetenida`** — no devuelve una respuesta inventada— y **no
queda fila** en `operaciones_externas` para la acción bloqueada (medido: 0).

## Correcciones de método en mis propias pruebas

Tres, y las digo porque dos eran **falsos positivos** que habrían dado por buena
una protección sin probarla:

1. **`importacion_io.aplicar` con lista vacía** no entra al bucle y no llama a
   nada. «0 llamadas externas» decía «bloqueado» cuando lo que pasó es que **no
   había nada que hacer**. Corregido con un candidato real.
2. **Un doble a medias del veredicto** hacía reventar `_cuerpo_de` con
   `AttributeError`, `aplicar` lo contaba como fallido y tampoco llamaba: el
   mismo falso positivo por otra puerta. Corregido usando la **dataclass real**.
3. Tres casos daban `NameError` por usar funciones antes de definirlas —
   bloqueaban por el motivo equivocado. Reordenado.

Y una comprobación que valía la pena: la réplica mostraba una fila de bloqueo
«previa». **No venía de producción** — producción tiene **0** — sino de mi propio
primer intento del script sobre ese mismo contenedor.

## Estado de las pruebas

**84 en verde, 2 en rojo.** Los dos rojos son **previos a este paso** y lo
verifiqué midiendo: con la versión HEAD de `importacion_io.py`, `test_reloj`
falla **exactamente igual**; `test_p2_inerte` nombra `verificar_restauracion.py`
y la migración 1705, de los pasos B.7 y 10.5.

---

# GO / NO-GO

## **GO.** No se encontró ningún bypass real.

| Criterio | Resultado |
|---|---|
| Ruta autónoma con efecto externo | **ninguna** — 20 probadas, 0 llamadas |
| Ejecutor directo sin autorización | bloqueado |
| `tenant` None / `''` / inexistente | bloqueado |
| Kill switch ausente · DB caída · `SELECT` revocado | bloqueado (10.14A §Q) |
| Hilo / pool sin contexto | bloqueado |
| `autorizado=True` fabricado | **no existe** |
| ContextVar manipulable desde fuera | **sólo con dos nombres privados, y se ve** |
| Idempotencia como bypass | bloqueado |
| Misma clave + args distintos | rechazado |
| Concurrencia | una sola ejecución |
| Ruta nueva que ignora la frontera | **bloqueada** |
| Rutas humanas legítimas | **no se bloquean** |
| Auditoría completa | tenant, actor, clave, origen, huella, timestamp |
| Datos ficticios | **ninguno** |

**Lo único que hereda el contexto es `asyncio`** (§2). No es un agujero, pero
queda anotado.

**Estado final:** producción intacta · ledger 50 · kill switch **DETENIDO** ·
0 filas `activo` · `DBUSER` sin cambios · sin migraciones nuevas · ningún código
desplegado · CRM 401 y frontend 200 · **cero llamadas a WispHub, SmartOLT o el
CRM**.

**Me detengo y espero revisión. No avanzo a autonomía 0–1.**
