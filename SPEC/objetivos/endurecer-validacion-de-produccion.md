# Objetivo · Endurecer la validación de producción

> Abierto el 23/09/2026. Estado: **abierto**.

## Qué significa terminado

Cada guarda que el motor ejecuta tiene una prueba que la ejercita por el camino
real, y el set de casos dorados no tiene ninguno cuyo resultado sea una moneda
al aire.

## Por qué existe

Hoy (23/09/2026) se construyeron y desplegaron cuatro guardas —reencauzamiento
de identidad, embudo de identidad, privacidad de observabilidad, recarga de
chunks viejos— y **ninguna tenía prueba de punta a punta**: `cli/evaluar.py`
llama a `motor.responder()` directo y no pasa por `atender_turno`, que es donde
todas viven. `cli/bateria_flujos.py` (commit `b66dba9`) cerró ese hueco y en su
primera corrida encontró tres cosas que ninguna prueba veía.

Y en el mismo día, un caso dorado inestable costó horas: `cliente actual
pidiendo otro servicio si se verifica` dio **3/4, 0/3, 1/11, 5/6, 1/5, 4/8 y
2/4** según la corrida. Encadena tres decisiones que el contrato deja abiertas
y culpa a una sola. Una prueba así no es una prueba: enseña a ignorar el rojo,
y hoy hizo perder tiempo distinguiéndola de una regresión real.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | `docker exec <contenedor-motor> python cli/bateria_flujos.py rapilink --todos` → **20/20**, con `[entorno: CONTENEDOR]` en el pie | salida real pegada, no resumida. Es el único modo que ejercita escalada→ticket: 17 herramientas del catálogo viven en `http://backend:8000` |
| 2 | `py -3.13 cli/bateria_flujos.py rapilink` → **18/18**, con `[entorno: LOCAL]` | la evidencia reproducible sin VPS; si difiere de (1), el informe dice por qué |
| 3 | El caso `cliente actual pidiendo otro servicio si se verifica` **ya no existe**; en su lugar hay dos, cada uno con **una** afirmación | `git diff` sobre `evaluacion/rapilink.casos.yaml` lo muestra |
| 4 | Cada caso nuevo del punto 3 corre **10 veces** y da **≥ 9/10** | las 10 salidas pegadas, no el promedio |
| 4b | Los números del criterio 2 y 6 se leen del set real, no de este documento | el set de humo creció a 10 casos y la batería a 21 el 23/09; los topes de abajo quedaron viejos el mismo día en que se escribieron |
| 5 | `sin el serial cargado no se le pide la cedula a quien ya verifico` deja de afirmar sobre la redacción (`responde_sin`) y pasa a afirmar sobre la traza | `git diff` + 10 corridas ≥ 9/10 |
| 6 | `py -3.13 cli/evaluar.py rapilink --humo --base` → **8/8** | `--base` no es opcional: hoy se aplicó config (v154) |
| 7 | `py -3.13 cli/diferencias_config.py rapilink` → **exit 0** | |
| 8 | Ninguna acción queda en estado distinto de `pendiente` tras una corrida completa | la batería ya lo afirma sola; la salida lo muestra |
| 9 | `auditor-independiente` corrió; hallazgos resueltos o anotados en `SPEC/auditorias/` con motivo | |
| 10 | `SPEC/DEXTER_ESTADO_ACTUAL.md` refleja el cierre **y** lo desplegado el 23/09 | hoy dice "Última actualización 19/09" y "Nada pusheado", con seis commits en producción |

## Restricciones

Las permanentes de este repositorio:

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF.
- **NO cargar config ni migrar contra producción.**
- **NO correr los 56 casos dorados** — `--humo` (~3 min); los 56 tardan ~23.
- **Stage por rutas explícitas** — nunca `git add .`, `-A`, ni `git add SPEC/`.

Las propias de este objetivo:

- **NO subir el techo de autonomía ni encender `AUTONOMIA_2_ACTIVA`.** Esto no
  es un criterio, es una restricción: "no aumentar autonomía" no se puede
  terminar, sólo sostener. Encenderla exige antes el prerequisito B-7, que
  `nucleo/seguridad/autonomia2.py` **mide** contra la base — no es poner una
  variable.
- **NO aprobar ninguna acción que deje la batería.** `reiniciar_ont` corta el
  servicio seis minutos y el equipo de laboratorio es uno solo.
- **NO tocar `SPEC/CONTRATO_RELEVO_IA_HUMANO.md`** — arrastre ajeno, queda
  fuera de todo commit.
- **NO cambiar prompts ni descripciones de herramientas.** El 23/09 tres
  cambios a texto compartido rompieron otra cosa y dos hubo que revertirlos.
  Si un caso exige cambiar conducta, se anota y se saca de este objetivo.

## Qué NO hacer

- **No construir la Fase 2 del Identity Engine.** El 33 % de pérdida que
  justificaba esa fase era del canal `api` (tráfico de prueba); en el canal
  real son 6 de 35 y ninguno fue bloqueo de identidad. Se decide con datos de
  BSUID reales, que todavía no existen.
- **No conseguir tráfico real acá.** Es el problema más importante de Dexter
  —11 conversaciones nuevas en 14 días— pero no es código y no se cierra con
  un comando. Va aparte.
- **No arreglar `ConnectionTimeout` ni el pool de conexiones.** Aparecieron dos
  durante la primera tanda; queda como dato para cuando se retome la Fase 2 de
  concurrencia, no como trabajo de acá.
- **No perseguir el falso positivo de `frustracion_detectada`.** Se vio una vez
  y no se repitió en 18 conversaciones. Cambiar la taxonomía sobre n=1 es el
  error que este proyecto ya cometió tres veces hoy.

## Agentes involucrados

> El `orquestador` **no se pudo invocar**: sus definiciones llegaron con el
> rebase de hoy y la sesión cargó su lista de agentes al arrancar. El plan de
> abajo se armó a mano siguiendo `.claude/agents/orquestador.md` y §11.2, y hay
> que rehacerlo con el agente en la próxima sesión.

**Clasificación: parcialmente relevante.** No toca `nucleo/`, ni una API
externa, ni qué dato llega al modelo. Sí toca el catálogo de casos dorados, que
es lo que juzga todo lo demás.

| Agente | Para qué | Estado |
|---|---|---|
| `corredor-de-evaluacion` | Partir el caso inestable y medir 10 corridas por caso nuevo | pendiente |
| `auditor-de-frontera` | Comprobar que "ninguna acción fuera de `pendiente`" cubre los caminos con efecto, no sólo `reiniciar_ont` | pendiente |
| `auditor-independiente` | Cierre del bloque antes de integrarlo | pendiente |
| `arquitecto-dexter` | — | **se saltea**: no se agrega capacidad nueva; `bateria_flujos.py` ya existe y esto la endurece |
| `verificador-de-api` | — | **se saltea**: no toca ninguna API externa ni un filtro/endpoint nuevo |
| `revisor-de-pii` | — | **se saltea**: no cambia qué dato llega al modelo, a un log ni a un tercero |
| `guardia-de-config` | — | **se saltea**: no se carga config en este objetivo |
| `guardia-de-release` | — | **se saltea**: este objetivo no despliega. Si se decide desplegar la batería, vuelve a entrar |

## Bloqueos

1. **Acceso al contenedor del motor en el VPS.** El criterio 1 exige
   `docker exec`, y desde una máquina de desarrollo `backend` no resuelve. Sin
   ese acceso el objetivo **no se puede cerrar**, aunque todo lo demás esté
   verde. Hay que resolver quién lo corre.
2. **Los casos del criterio 1 dejan casos reales en BottleCRM.** Son de
   laboratorio y hay que borrarlos después; conviene acordar cómo antes de
   correrlos, no después.

## Hallazgos de la medición

Lo que apareció al medir, y no se arregla en este objetivo porque exige cambiar
conducta (restricción: no se tocan prompts ni descripciones de herramientas).

**El router nunca deriva con «quiero agregar otro servicio a mi cuenta».**
Medido **0 de 10**, determinista — no inestable. Siempre hace su pregunta
aclaratoria («¿internet o televisión?») y se queda esperando. Es defendible: el
parámetro `servicio` de `derivar_a_area` es obligatorio y su descripción está
escrita para fallas, no para altas. Pero significa que el caso no podía afirmar
la derivación en el primer mensaje.

Eso también explica de dónde venía la inestabilidad del caso viejo: **no era
azar en la primera decisión, era una falla determinista encadenada con una
segunda decisión variable**. El caso viejo mandaba un número como segundo
mensaje, y ahí el router a veces derivaba y a veces no.

Se intentó arreglar el 23/09 ampliando la descripción del parámetro `servicio`
(«si el tema NO es una falla, va `no_lo_dijo` y derivás igual»): dio **1/6 y
1/4**, sin beneficio medible, y se revirtió. Queda para un objetivo aparte, con
su propia medición pareada.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 23/09/2026 | Batería creada; 18/18 local tras corregir una expectativa mal escrita. Bandera de entorno medida por resolución de nombre. | Criterios 1, 3, 4, 5, 9, 10 | `b66dba9` |
| 23/09/2026 | Criterios 3, 4, 5, 6, 7, 10. Caso inestable partido en dos (10/10 y 10/10). `responde_sin: [cedula]` reemplazado por `bloquea_con: [DATO_DEL_EQUIPO_NO_CARGADO]` + `no_bloquea_con: [IDENTIDAD_NO_RESUELTA]`, para lo cual `cli/evaluar.py` ganó esas dos afirmaciones. `DEXTER_ESTADO_ACTUAL.md` ya no dice «nada pusheado». | Criterios 1 (bloqueado por VPS), 2, 9 | pendiente |
