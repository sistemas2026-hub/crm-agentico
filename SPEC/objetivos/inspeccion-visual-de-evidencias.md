# Inspección visual de las fotos de evidencia

**Estado:** etapa 1 en construcción · **Abierto:** 31/10/2026

## Qué pidió el usuario

Que las fotos que el técnico sube como evidencia se analicen con IA:
identificar equipos, detectar cableado suelto o mal instalado, evaluar la
calidad de la instalación, leer LEDs, y validar si la foto sirve como
evidencia de la actividad. Que el supervisor lo revise. Y acumular todo como
dataset para entrenar modelos después.

Su pregunta literal fue si se podía hacer desde `/agentes`.

## La respuesta, y por qué importa

**No se puede desde `/agentes`,** por tres razones independientes: esa
pantalla solo elige del catálogo que ya existe (`editor._aplicar_herramientas`
recorre las herramientas existentes, no hay rama que cree una); ninguna
herramienta del catálogo puede recibir una foto (el bucle de tool calling pasa
argumentos JSON); y `/agentes` escribe un rol **conversacional**, y una
inspección visual no tiene turno del que colgarse.

**Pero entre el 60% y el 70% ya estaba construido**, repartido en dos sitios
que no se hablaban: `nucleo/canales/vision.py` (analiza fotos de clientes por
WhatsApp, en producción, con seis garantías puestas) y
`campo/revision_del_cierre.py` (el supervisor revisa la evidencia de una orden
y da un veredicto con puntos, desplegado el 31/10/2026).

Lo que faltaba era el puente.

## Decisiones tomadas antes de la primera línea

| # | Decisión | Por qué |
|---|---|---|
| 1 | **El punto de IA solo puede valer `True` o `None`, nunca `False`** | `revision_del_cierre.py` convierte cualquier `False` en `NO_CERRAR`, y ese veredicto alimenta el cierre autónomo del Supervisor. Una opinión no verificada de un modelo no puede frenar el trabajo de un técnico. `None` ya significa REVISAR, que es todo el alcance que corresponde: la IA pide atención, nunca niega un cierre (CLAUDE.md §4). **La guarda está en los dos lados** — en quien produce el punto y en quien lo consume |
| 2 | **Interruptor propio (`vision_evidencias_campo`), no se reusa `vision_habilitada`** | Las dos mandan una imagen al mismo proveedor, pero no las respalda el mismo consentimiento: una es la foto que un cliente **decide** mandar, la otra la que un técnico toma **dentro de la casa** del cliente. Con un solo campo una empresa no podría autorizar una y no la otra |
| 3 | **La instrucción es un parámetro de `vision.analizar`, no un módulo nuevo** | Un segundo módulo que le hable al proveedor sería la historia del reloj escrito dos veces (CLAUDE.md §6). Hay **un** sitio que manda imágenes, con sus garantías, y lo que cambia es qué se le pide |
| 4 | **El análisis se guarda en tabla propia, append-only** | La corrección de una persona tiene que ser una **fila nueva**, nunca un `UPDATE`: sin el par (lo que dijo la IA, lo que dijo la persona) no hay con qué medir si acierta, y medir eso es el único motivo por el que la etapa 1 existe |
| 5 | **Qué tiene que mostrar cada foto sale de `evidencias[].instrucciones`** | Ya existía: texto libre, por requisito, por empresa, editable desde `/supervisor-noc/plantillas`. Cero superficie de config nueva |

## Lo que la etapa 1 NO hace, y no es que falte

- **No extrae estructura.** El proveedor no puede devolver JSON: medido contra
  la API real el 02/10/2026 — `json_schema` da HTTP 400 (*"This response_format
  type is unavailable now"*) y `json_object` triplicó la latencia para devolver
  listas vacías. Extraer del texto libre es la etapa 2, y se decide con el
  número que ésta produce. **No reabrir sin una medición nueva** (§10).
- **No arma dataset de entrenamiento.** Acumular el análisis como registro
  *operativo* es legítimo con la autorización vigente; declararlo dataset es
  una **finalidad nueva** sobre fotos de casas de clientes (CLAUDE.md §5). El
  usuario decidió el 31/10/2026 entrenar con fotos de internet, lo que evita
  esa pregunta para el entrenamiento — pero el **conjunto de evaluación** sí
  tiene que ser de campo, o el número de acierto no significa nada.
- **No tiene pantalla propia.** Va última: recién entonces hay algo que
  mostrar, y la decisión D5 (una instalación por ISP vs. plataforma) habrá
  tenido tiempo de tomarse. Cada pantalla nueva suma una aparición más de
  `PRIVATE_ASISTENTE_TENANT`.

## Qué se mide con la etapa 1

1. De N fotos del día, cuántas produjeron análisis y cuántas fallaron **por
   formato**. El storage acepta HEIC y WebP; el analizador solo JPEG y PNG.
   Una foto de iPhone se sube bien y el análisis la rechaza. También 25 MB de
   storage contra 8 MB del analizador.
2. Segundos y tokens por foto. El evento `VISION` ya los agrega por tenant, así
   que el costo sale de `/consumo`, que ya existe.
3. **La que decide todo: en cuántas el supervisor dice que el análisis acertó.**
   Sin ese número, construir salida estructurada es adivinar.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 31/10/2026 | **Encuadre.** El arquitecto ubicó lo que ya existía y las tres razones por las que no es configuración. Hallazgo que ahorró el módulo entero: `evidencias[].instrucciones` ya es el prompt de inspección, por empresa. Y un hueco de documentación: `vision.py`, `vision_habilitada` y `nota_vision.py` **no figuran en `PRD.md` ni en `ARQUITECTURA.md`** (`grep -ni "vision" ARQUITECTURA.md` → 0), que es por qué la pregunta llegó como «¿se puede desde /agentes?» | informe del arquitecto | — |
| 31/10/2026 | **Etapa 1 construida.** `vision.analizar` acepta `instruccion`; `INSTRUCCION_EVIDENCIA` pide lo que la de WhatsApp prohíbe y sigue sin poder afirmar que el servicio funciona. Ruta `POST /interno/vision/analizar-evidencia` con las cuatro garantías: interruptor propio, tope de gasto **consultado antes de pagar** (el gate del turno no cubría esta ruta), topes de `vision` y evento de consumo. `campo/inspeccion_visual.py` lee y decide sin escribir; `AnalisisDeEvidencia` guarda; `campo.tasks.analizar_evidencia` por `on_commit` desde `ConfirmarEvidenciaView`; sexto punto en la revisión | `tests/test_vision_evidencia_campo.py` verde (22 afirmaciones) y **3 mutaciones muertas**. La primera versión de esa prueba era un **falso verde**: quitarle el parámetro a la llamada interna de `analizar()` la dejaba en verde porque solo medía el armador. Se agregó la sección F, que captura lo que llega al modelo | pendiente |
