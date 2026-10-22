# Objetivo · La bandeja como WhatsApp: una sola ventana por número

> Abierto el 21/10/2026. Estado: **abierto**.

## Qué significa terminado

Cada número tiene **una sola ventana** en la bandeja, con todos sus mensajes
anteriores separados por una marca de cierre y lo nuevo debajo; y el equipo
puede escribirle a ese número aunque su última conversación esté cerrada.
Por dentro, cerrar sigue siendo cerrar: el relevo, el desenlace, las métricas,
el Supervisor y el resumen que recibe la IA no cambian.

### Por qué existe

Reportado por el usuario el 21/10/2026: *"cuando uno escribe desde el mismo
numero de telefono se crea una nueva conversacion como si fuera otro numero
nuevo"*. Medido en el código ese día: no es una carrera ni un formato de número
distinto. `nucleo/persistencia/db.py::registrar_mensaje` reutiliza solo una
conversación en estado `'abierta'`, y cuatro caminos la cierran (T15b la IA por
confirmación, T16 el plazo, T17 el operador, T18 la inactividad de 24 h). Lo
siguiente que escribe el número abre una conversación nueva, y la bandeja
—que lista **conversaciones**— la muestra como una ventana nueva. Es la conducta
que el contrato define (E3 «Terminada»; T18 «lo que responda la IA en la
conversación nueva»). Lo que se pide es que se VEA como WhatsApp.

Decisiones del usuario (21/10/2026):
1. *"el sistema puede cerrar la conversacion pero debe mostrar los mensajes
   anteriores como whatsapp"* — aplica a todos los cierres.
2. *"no la entiendo del funcionamiento de la IA, esta bien"* — la IA no cambia.
3. El equipo **sí** puede escribirle a un chat cuya última conversación está
   cerrada.

## Decisiones de diseño tomadas al encuadrar

Deducidas de las tres anteriores y del contrato. Si alguna no le sirve al
usuario, se cambia acá antes de construir.

| # | Decisión | Por qué |
|---|---|---|
| D1 | La ventana es por `(canal, usuario_externo)` dentro de la empresa. | Contrato S8: el mismo número simulado es una sesión distinta del real. |
| D2 | Representa al número la conversación **abierta** más reciente por `creado_en`; si no hay abierta, la última cerrada. Nunca por `actualizado_en`, que lo mueve el propio cierre (`db.py`, comentario medido). | |
| D3 | Si un número tiene **dos o más abiertas** (no hay índice único que lo impida, y `guardar_resumen` se traga su excepción), ninguna queda escondida: la fila del número toma la banda **más urgente** de sus abiertas, y el chat muestra todas. | Regla de fallar hacia lo visible (§4.2). |
| D4 | El separador dice la hora del cierre y el motivo **solo si quedó registrado** (`cerrada_por_tipo`); si no, solo «Conversación cerrada». No se infiere. | T18 no escribe `cerrada_por_tipo` ni evento: dato que no existe no se inventa. |
| D5 | Escribir en un chat cerrado **no reabre** nada: crea una conversación nueva iniciada por el operador, con `control = humano` y asignada a quien escribe. La cerrada queda cerrada con su desenlace. Fuera de la ventana de 24 h, solo plantilla (la ruta que ya existe). | E3 sigue siendo terminal; el desenlace y las métricas de la cerrada no se tocan. |
| D6 | La agrupación la calcula el **motor** una vez, no la pantalla. | Contrato §4: las proyecciones viven en el backend. |
| D7 | La bandeja cuenta **chats** (números) y lo dice; el Centro de mando sigue contando conversaciones y lo dice. | Dos números distintos para «lo mismo» sin rótulo ya pasó (07/09: 41 contra 44). |
| D8 | Un enlace viejo a `/conversaciones/<id>` abre la ventana del número posicionada en ese tramo, con un aviso si hay una conversación más reciente. | `/manual`, `tickets/[id]`, `despacho.py` y el simulador enlazan por id. |
| D9 | La vista de simulación **no** agrupa. | Los números de batería se reutilizan: fusionaría corridas viejas. |
| D10 | Es conducta de la plataforma, no un ajuste por empresa. No toca `tenant_config`. | Ninguna empresa quiere un chat partido. |

## Criterios de aceptación

Cada uno, con su comando y la salida pegada en la conversación.

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | `py -3.13 tests/test_nucleo_sin_tenants.py` | `[OK] El nucleo no conoce a ningun cliente.` |
| 2 | Prueba NUEVA contra PostgreSQL real (base efímera de `cli/base_desde_cero.py`): un mismo número con una cerrada T17, una cerrada T18, una abierta escalada vieja y una abierta nueva; afirma qué conversación representa al número, en qué banda y vista cae, que ninguna abierta queda escondida, que otro canal y otra empresa no se mezclan | salida `[OK]` pegada |
| 3 | Mutaciones sobre la prueba 2: elegir por `actualizado_en`, esconder una abierta, agrupar sin `canal`, agrupar sin empresa | las cuatro `MUERE`, árbol intacto |
| 4 | Prueba NUEVA de D5 contra PostgreSQL real: escribir en un chat cerrado crea una conversación con `control = humano` y asignada; la cerrada conserva `estado`, `cerrada_por_tipo` y desenlace; fuera de 24 h el texto libre se rechaza y la plantilla pasa; la respuesta del cliente cae en la conversación que abrió el operador | salida `[OK]` pegada |
| 5 | Guardas existentes iguales que en `origin` (sin base): `test_cola_bandeja`, `test_bandeja_config_falla_cerrado`, `test_origen_en_el_hilo`, `test_historial_unico`, `test_contexto_anterior`, `test_cierre_inactivas_ia`, `test_registro_sin_pii`, `test_errores_http`, `test_relevo_efectos` | tabla prueba → exit en `origin` → exit con el cambio |
| 6 | Guardas con PostgreSQL real, sobre la base efímera: `test_relevo_transiciones_base`, `test_b6_cierre_desenlace`, `test_chat_historial` | salida pegada |
| 7 | `vitest run src/lib/conversaciones src/lib/server/v2/bandeja-config.test.js src/lib/observabilidad/privacidad.test.js` con pruebas nuevas de la agrupación y de `lib/conversaciones/estado.js` | mismos rojos que `origin` o menos, comparado contra `origin` |
| 8 | `docker exec <frontend> pnpm check` | errores ≤ 161 (línea base del 19/10) |
| 9 | `git diff --name-only origin/fix/integracion-wisphub` no incluye `nucleo/modelo/motor.py`, `nucleo/relevo/historial.py`, ni cambia `resumen_anterior` o `conversacion_vencida`; si los incluye, `py -3.13 cli/evaluar.py rapilink --humo` | lista pegada |
| 10 | `SPEC/CONTRATO_RELEVO_IA_HUMANO.md`: §4.5 enmendada (vistas por chat) y la transición nueva de D5, fechadas el 21/10/2026 con su motivo; `PRD.md` con la decisión | `git diff --stat` pegado |
| 11 | `auditor-de-frontera`, `revisor-de-pii` y `auditor-independiente` corrieron; hallazgos resueltos o anotados con motivo en `SPEC/auditorias/bandeja-como-whatsapp.md` | archivo en el diff |
| 12 | Entorno local reconstruido desde el worktree de este trabajo, con conversaciones INVENTADAS sembradas por un script (canal `whatsapp`): `py -3.13 cli/entorno_local.py verificar` | `[OK] El entorno local no puede producir efectos afuera.` |
| 13 | El usuario lo revisa en http://dexter.localhost:3300/conversaciones | el usuario escribe «confirmado en local» |
| 14 | `guardia-de-release` corrió | su checklist pegado |

## Restricciones

- **NO push**: push a `fix/integracion-wisphub` es deploy a producción. Se
  pide «haz push» al usuario al final, fuera del `/goal`.
- **NO escribir `tenant_config`**, no cargar config ni migrar contra producción.
- **NO correr los 56 casos dorados**; si hace falta, `--humo`.
- Stage por rutas explícitas; nunca `git add .`, `-A` ni un directorio entero.
- Trabajo en un worktree NUEVO sobre `origin/fix/integracion-wisphub`, no en
  `C:/wt-area` ni en `C:/dexter-local`: los dos tienen sin commitear el freno
  `SIN_EFECTOS_EXTERNOS` (`nucleo/seguridad/entorno.py`, `http.py`,
  `whatsapp.py`, su prueba), que es otra línea y no se mezcla.
- **No cambia cómo se cierra**: T15b, T16, T17 y T18 quedan como están.
  `persistencia.ultima_actividad` no cambia (la usa `cli/detectar_seguimientos.py`).
- Ninguna conexión a producción. Ningún envío real: la base local no tiene
  credenciales de WhatsApp (lo comprueba `verificar`).
- `marioth727` escribió casi toda la bandeja: el usuario le avisa antes de que
  se toque `[id]/+page.svelte`.

## Qué NO hacer

- **Corregir T18** para que deje `cerrada_por_tipo` y su evento: cambia el
  cierre, y el usuario decidió que por dentro no cambie. La divergencia
  contrato↔código de T18 (D13: no aplica las guardas del contrato) la anota el
  auditor; no se arregla acá.
- **Reabrir una conversación cerrada**: D5 lo resuelve sin tocar E3.
- **Agrupar la vista de simulación** (D9).
- **Un índice único** que impida dos abiertas por número: cambiaría cómo se
  crean conversaciones; D3 las muestra en vez de prohibirlas.
- **Cambiar el Centro de mando** más allá de su rótulo (D7).

## Agentes involucrados

Plan del `orquestador` (21/10/2026).

| Agente | Para qué | Estado |
|---|---|---|
| arquitecto-dexter | Confirmar que no existe; ruta nueva o parámetro; dónde se agrupa; redactar la enmienda §4.5 y la transición de D5 | pendiente, corre primero |
| verificador-de-api | — | se saltea: no toca WispHub, SmartOLT, BottleCRM ni Meta |
| auditor-de-frontera | A qué conversación apuntan los botones con efecto en la ventana unificada; que el MOTOR rechace un efecto sobre un tramo viejo (hoy solo lo impide la pantalla: `[id]/+page.svelte:1672`); el envío de D5 | pendiente |
| revisor-de-pii | Ruta nueva sin teléfono en la URL; `registrar()` sin contenido; número reasignado entre tramos; huecos por la purga; `conservar` y «marcar ejemplo» por tramo | pendiente |
| corredor-de-evaluacion | — | se saltea: no cambia prompt, catálogo ni modelo; se activa si se cumple la condición del criterio 9 |
| auditor-independiente | La abierta que la agrupación esconde; conteos que dejan de coincidir entre pantallas | pendiente |
| guardia-de-config | — | se saltea: no hay `tenant_config` (D10) |
| guardia-de-release | Motor y frontend salen juntos; sin migración esperada (`conversations_usuario_idx` ya existe) | pendiente, al final |

## Bloqueos

Ninguno abierto. Los tres de producto quedaron resueltos el 21/10/2026 (ver
«Por qué existe»). Medición recomendada, no bloqueante: el script de solo
lectura `conv_repetidas.py` en el contenedor del motor dice cuántos números
tienen dos abiertas a la vez (D3).

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 21/10/2026 | Encuadre: diagnóstico del código, tres decisiones del usuario, plan del orquestador, esta ficha | Todo lo de construir | — |
