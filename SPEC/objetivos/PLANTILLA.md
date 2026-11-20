# Objetivos — cómo se usa esta carpeta

Cada archivo de acá es **el contrato de un trabajo grande**: qué significa
terminado, con qué evidencia, y qué no se toca en el camino.

La regla que gobierna todo:

> **`/goal` no es dueño del objetivo. El dueño es el archivo.**

`/goal` es el motor que empuja durante una sesión; su condición se deriva de la
sección "Criterios de aceptación" de acá. Si el archivo y la condición difieren,
manda el archivo — y corregir la condición es parte del trabajo.

Al cerrar un objetivo, la ficha **no se borra**: se poda a su resultado y el
cierre se refleja en [../DEXTER_ESTADO_ACTUAL.md](../DEXTER_ESTADO_ACTUAL.md),
que sigue siendo la autoridad del estado. Un objetivo no está cerrado hasta que
ese archivo lo diga.

Se crea con `/objetivo <qué se quiere lograr>`.

---

# Plantilla

Copiar de acá para abajo a `SPEC/objetivos/<slug>.md`.

---

# Objetivo · <título>

> Abierto el <fecha>. Estado: **abierto** | cerrado | abandonado.

## Qué significa terminado

Una frase. Un estado final, no una actividad. *"La bandeja devuelve el control
a la IA sin perder el acuse"*, no *"trabajar en el relevo"*.

## Criterios de aceptación

La sección que decide si este objetivo sirve. **Comando y salida esperada, no
prosa** — de acá sale literalmente la condición del `/goal`, y el evaluador solo
puede juzgar lo que aparezca en la conversación.

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | `py -3.13 tests/test_x.py` pasa | salida real pegada, no resumida |
| 2 | `py -3.13 cli/evaluar.py rapilink --humo --base` → 8/8 | `--base` no es opcional si se aplicó config |
| 3 | `auditor-independiente` corrió; sus hallazgos resueltos o anotados en `SPEC/auditorias/` con motivo | |
| 4 | `SPEC/DEXTER_ESTADO_ACTUAL.md` refleja el cierre | |

Si un criterio no se puede escribir como comando + salida, no es un criterio:
es un deseo. Buscar cuál sería la evidencia, o sacarlo.

## Restricciones

Lo que no puede cambiar mientras dure. Las tres permanentes de este repositorio
van siempre:

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF.
- **NO correr los 56 casos dorados** — `--humo` (~3 min); los 56 tardan ~23.

Más las propias: qué archivos no se tocan, qué decisión congelada no se reabre.

## Qué NO hacer

Lo que quedó explícitamente fuera del alcance, **con su motivo**. Esta sección
existe para que nadie lo "agregue de paso" ni lo redescubra como pendiente.

## Agentes involucrados

Lo devuelve el `orquestador`, no se escribe a mano. Incluye los que se saltean,
con su motivo — un paso se saltea diciéndolo.

| Agente | Para qué | Estado |
|---|---|---|
| | | pendiente / corrió / se saltea por … |

## Bloqueos

Lo que impide arrancar o avanzar y **no es código**: una decisión de producto
abierta, una credencial, una aprobación de un tercero. Si hay uno, el objetivo
no arranca hasta resolverlo.

## Bitácora

Una línea por sesión. Qué avanzó, qué falta, y el hash si hubo commit.

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
