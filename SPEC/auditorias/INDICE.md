# AUDITORÍAS — ÍNDICE

Un archivo por gate. El agente lee sólo los que el prompt le nombre.

| Gate | Archivo | Veredicto | Qué dejó |
|---|---|---|---|
| 1.4C.0-B | — | A (**ANULADO**) | Resolvió `enviado` = Meta devolvió wamid. Su clasificación A se cayó: auditaba código no commiteado. |
| 1.4C.0-C | — | D (**corregido a C+B**) | Invariante T6 verificado. B2 irrecuperable. Descubrió el worktree sucio. |
| 1.4C.0-D | — | STOP, C+B provisional | Proveniencia del draft. `db.py` no parseaba. Bloque ③ identificado. |
| 1.4C.0-D1 | — | STOP | El defecto de sintaxis era triple, no único. Sin tocar nada. |
| 1.4C.0-D1b | — | Aprobado | 3 comillas reparadas. Parse + imports verdes. `test_entrega_registrada` falla. |
| 1.4C.0-D1c | [1.4C-D1c.md](1.4C-D1c.md) | H3 | Clasificación por función y hunks a separar. |
| **1.4C.0-D2** | [1.4C-D2.md](1.4C-D2.md) | **implementado** | Separación del hot path, recovery B1/B2, 4 defectos del draft, 20 tests nuevos. **Pendiente de auditoría externa.** |
| **1.4C-D3** | [1.4C-D3.md](1.4C-D3.md) | **criterio de cierre cumplido** | PostgreSQL real: migración aplica y el ledger la anota sola; 6 hallazgos que los dobles no veían; concurrencia y aislamiento medidos. **Entrada del próximo gate.** |
| **1.4C-UI** | [1.4C-UI.md](1.4C-UI.md) | **aprobado** | El botón y sus cuatro estados, failed vs unknown, idempotencia de punta a punta. 3 defectos del draft corregidos. **Cierra la Fase 1.4C.** |
| **1.5** | [1.5-CASE-TOOLS.md](1.5-CASE-TOOLS.md) | **aprobado** | Case + Tools. D28 en pantalla sin fingir identidad; los cuatro semánticos resueltos en `context/`. |
| **1.6** | [1.6-ACTIVITY.md](1.6-ACTIVITY.md) | **aprobado** | Activity. Los eventos del relevo existían sin vía de lectura; se agregó solo lectura + panel, con refresco por hecho y no por reloj. |
| **1.7** | [1.7-CUSTOMER.md](1.7-CUSTOMER.md) | **aprobado** | Customer. La referencia marcaba sus campos como MOCK; se muestra lo que Dexter guarda y se dice por qué el resto no está. |
| **1.8** | [1.8-NETWORK.md](1.8-NETWORK.md) | **aprobado** | Network. Sin telemetría en vivo y sin botones de ping/reinicio, con las razones medidas; se muestra el veredicto de las acciones. |
| **1.9** | [1.9-CIERRE-VISUAL.md](1.9-CIERRE-VISUAL.md) | **aprobado** | Cierre visual: utilidades de panel duplicadas cuatro veces y una de ellas distinta. Branding fuera de la fase; el smoke visual, no ejecutable. |
| **B4 · Q2** | [B4-Q2-WISPHUB.md](B4-Q2-WISPHUB.md) | **ROJO** | `crear_ticket` no es reintentable: ninguna de las tres vías del contrato existe. Cerrado por documentación, sin tocar producción. |
| **B4** | [B4-IMPLEMENTACION.md](B4-IMPLEMENTACION.md) | **implementado** | La cola de efectos externos, T20 con cadencia propia y el panel de sincronización. T20 sin enganchar: G7. |
| **G3** | [G3-ACCIONES-LEGACY.md](G3-ACCIONES-LEGACY.md) | ROJO → cerrado | Las 36 acciones de legado. El endpoint de aprobar las ejecutaba: el bloqueo 1 no podía esperar a B5. |
| **G3** | [G3-CIERRE.md](G3-CIERRE.md) | **VERDE** | Aprobar rechaza con 409 sin ejecutar, `cancelada` es estado declarado con evento, y hay pantalla para revisar. Las 36 siguen `pendiente`: cancelarlas es trabajo de una persona. B5 desbloqueado. |
| **B5** | [B5-ACCIONES.md](B5-ACCIONES.md) | **CERRADO EN CÓDIGO** | Aprobar es reservar, revalidar, ejecutar y resolver. La revalidación tiene tres desenlaces: «no se pudo comprobar» no ejecuta. Validador en modo advertencia hasta que cierre la medición (Q3). |
| — | [1.4C-hotpath-diferido.md](1.4C-hotpath-diferido.md) | diferido | Los hunks de ③a/③c retirados, recuperables con `git apply -R`. |

Los gates sin archivo viven sólo en la transcripción; sus conclusiones vigentes
están recogidas en `SPEC/DEXTER_ESTADO_ACTUAL.md`. No hace falta releerlos.

## Formato de un informe

Corto. El auditor abre el repo por su cuenta: no se le describe código que puede
leer, se le dan punteros `archivo:línea`.

```
VEREDICTO · HALLAZGOS · BASE (hash) · ARCHIVOS TOCADOS · TESTS · DUDAS
```
