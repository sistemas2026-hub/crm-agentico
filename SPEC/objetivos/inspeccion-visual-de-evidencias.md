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

## Cuánto vive el registro, y por qué

**Decidido el 31/10/2026, a raíz del revisor de PII (H4).** La ficha no lo
decía, y es el tipo de decisión que no se deja implícita.

Las dos puntas de este camino son permanentes y no era obvio: la foto no se
borra nunca (`storage.py`: *"Una evidencia NO se borra --es la prueba de un
trabajo--"*) y `AnalisisDeEvidencia` es append-only sin purga. El camino de
WhatsApp no tiene esa forma: ahí la foto se borra a los
`retencion_multimedia_dias` y lo que queda es el texto.

Lo que `redactar()` cubre es cédula, teléfono, email, URL y coordenadas
decimales. **No cubre, y no puede sin NLP:** nombres propios, direcciones en
prosa, placas, ni la descripción de una persona. Escenario concreto: el
técnico fotografía el router sobre la mesa del comedor y en el encuadre entra
la hija del cliente y un recibo con nombre y dirección.

**Mitigación puesta hoy:** la instrucción recuperó la regla que acota la foto
fuera de tema —se había perdido al escribirla— y además prohíbe describir
personas, leer direcciones, placas y papeles del encuadre. Es prompt, o sea
guía y no garantía (PRD §7.4), y por eso se declara como mitigación y no como
solución. Dos afirmaciones de `tests/test_vision_evidencia_campo.py` existen
para que esas reglas no se pierdan otra vez.

**Lo que queda ABIERTO y es decisión del usuario:** ponerle una ventana de
retención a `AnalisisDeEvidencia.texto`. Operativamente no se pierde nada
después de que la orden se aprueba — `revision_del_cierre.guardar_foto` ya
deja los conteos y el motivo en `EventoTrabajo.datos`, sin el texto del
modelo. Lo que se perdería al borrarlo es el conjunto de evaluación que la
etapa 1 quiere medir, y eso se resuelve con una ventana (90 días es un punto
de partida razonable), no con «para siempre». **No se implementó ninguna
ventana todavía: hoy el texto vive indefinidamente.**

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
| 31/10/2026 | **Revisor de PII: seis hallazgos, cuatro cerrados en código.** **H1 — apagado NO estaba apagado.** La tarea corría igual: mandaba los bytes al motor (que los rechazaba sin llamar al proveedor, eso sí andaba) y después escribía una fila con `motivo` y sin `texto`. Con esa fila, `punto_de_la_revision` veía «ninguna se pudo mirar», devolvía el punto en «no se sabe» y el veredicto pasaba a REVISAR — **o sea que la función apagada, que es el default y lo que va a producción, habría frenado el cierre autónomo del Supervisor en toda orden con evidencia**, y contradecía lo que el propio `schema.py` declaraba. **Cerrado:** el consentimiento se pregunta ANTES de mover los bytes (`GET /interno/vision/evidencias-habilitada`, que falla CERRADO en los tres frentes), y apagado no escribe fila. La prueba vieja modelaba «apagado» como «no hay filas», que es otra cosa: mismo tipo de falso verde que ya se había cazado en la sección F | **H2 — la empresa salía de `MOTOR_TENANT`**, una variable por instalación, que es justo lo que la guarda `common/tests/test_motor_tenant_falla_cerrado.py` existe para prohibir desde el 31/10/2026. Con dos empresas en la misma instalación, la foto tomada dentro de la casa de un cliente de la B se habría mandado al proveedor porque **la A** tiene el interruptor encendido, y la factura habría caído en la A: el interruptor que este módulo justifica con «no es el mismo consentimiento» se evaluaba contra el consentimiento de otra empresa. Ese commit dejó la guarda en ROJO con un único culpable, el archivo nuevo. **Cerrado:** `tenant_de(evidencia.org)`. **H5 — el pie se le atribuía al cliente:** al proveedor le llegaba «El cliente escribió junto a la foto: Esta foto tenía que mostrar…», que es falso y además mueve el análisis. **Cerrado:** el rótulo es parámetro, como la instrucción. **H3 — EXIF:** el archivo de campo llega crudo del disco y nunca se recodificó, así que puede llevar GPS de la vivienda adentro de los bytes; el de WhatsApp pasa por `media.preparar`, que lo tira. **No está medido** que las fotos de hoy lo traigan (la app recodifica en el teléfono); se recodifica igual antes de mandarla porque es una línea y cuesta menos. **H6, anotado para después:** el camino `origen=persona` todavía no tiene escritor, y cuando se construya, el texto va a venir de un formulario sin pasar por `redactar()` — y es justo donde un supervisor escribiría el nombre del cliente | 3 mutaciones muertas (apagado vuelve a escribir fila, el interruptor falla abierto, vuelve `MOTOR_TENANT`); `pytest campo/tests/test_cierre_por_el_supervisor.py common/tests/test_motor_tenant_falla_cerrado.py` → **66 passed**, con la guarda de `MOTOR_TENANT` de nuevo en verde | este commit |
| 05/11/2026 | **El aviso aparecía en TODAS las fotos, y era un defecto mío.** Medido en producción (OT 100): *«Revisá las fotos: 4 de 4 piden una mirada»*, con los otros cinco puntos en ✓. El detector buscaba `borros`, `no se ve`, `no se puede`, `tapad`, `fuera de cuadro` — y la instrucción **le pide al modelo que diga exactamente eso**: «si algo está borroso, oscuro, tapado o fuera de cuadro, decilo, y decí que no se puede determinar por eso». Se le pedían las frases y después se usaban como alarma, así que era 4 de 4 **siempre**. **El costo no fue el ruido:** el veredicto quedaba en REVISAR, el cierre autónomo exige CERRAR, y desde que se encendió el análisis **ninguna orden con fotos se cerraba sola**. Y un aviso que aparece siempre deja de avisar: en una semana se aprueba sin leerlo, y el día que una foto esté de verdad mal pasa igual. **Arreglado en dos capas:** (1) la instrucción pide terminar con `ATENCION: si` o `ATENCION: no` —el juicio del modelo sobre lo que acaba de describir— y el CRM lee esa marca; (2) la lista de palabras queda como respaldo para cuando el modelo no la escriba, **limpia de todo lo que la instrucción exige**. También salió `suelto`, que es el defecto más común, porque la regla 4 le pide decir si hay cables sueltos y entonces escribe la palabra también cuando **no** los hay. El respaldo queda más flaco a propósito: un cable suelto lo reporta la marca | `tests/test_vision_propositos.py` §F: guarda del **contrato entre los dos servicios** —el motor no importa de Django ni al revés— que lee la tupla del CRM con `ast` y afirma que ninguna de sus palabras está en la parte descriptiva de la instrucción. Encontró sola dos choques que yo no había visto (`suelto`/`sueltos` de la regla 4). Más `campo/tests/` A1–A3, que prueban la **conducta**: la guarda estática no veía que la marca dejara de leerse. **4 mutaciones muertas**; dos de ellas sobrevivían a la primera versión y por eso se agregaron esas piezas. `pytest test_cierre_por_el_supervisor.py` → **40 passed** | este commit |
