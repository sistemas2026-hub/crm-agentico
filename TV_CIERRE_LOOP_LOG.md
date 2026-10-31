# Cierre del bloque TV — bitácora del loop

Una fila por iteración. Se registra lo que se encontró, lo que se tocó y con
qué se comprobó. No se borran pruebas ni se debilitan aserciones para llegar a
verde: si algo queda rojo, queda escrito.

Estado de producción durante todo el loop: **intacta**. Sin push, sin
despliegue, sin migraciones.

---

## Iteración 1 — barrido documental del límite de televisores

**Problema.** La decisión vigente es 5 televisores. Había que confirmar que
ninguna regla vigente siguiera diciendo 4.

**Búsqueda.** Los seis términos de la especificación (`4 televisores`,
`hasta 4`, `máximo 4`, `más de 4`, `cuatro TV`, `TV/TDT`) sobre `.py`,
`.yaml`, `.md`, `.svelte`, `.js`, más los dos `.docx` del repo.

**Clasificación de lo encontrado.**

| Referencia | Clase | Decisión |
|---|---|---|
| `nucleo/seguimiento/supervisor.py:19` — «el maximo de TV son 4» | **A. regla vigente** (documentación en docstring) | Corregido a 5 |
| `corpus/rapilink/MANUAL.docx` §5.9, §5.10, §5.11 — «hasta 4 TV/TDT», «mas de 4», «maximo de 4» (×4) | **A. regla vigente** (documento controlado del cliente) | **No modificado** — ver iteración 2 |
| `nucleo/canales/api.py:5025` — «hasta 42 s» / «4.7-12 s» | D. falso positivo (latencias) | Sin tocar |
| `PRD.md:406` — «más de 4 caracteres» | D. falso positivo (enmascaramiento) | Sin tocar |
| `evaluacion/rapilink.casos.yaml:540` — «tengo dos equipos…» | C. ejemplo de prueba | Sin tocar — no declara cifra |
| `tests/test_tuteo.py:39` — «ya pasas el límite de televisores» | C. ejemplo de prueba | Sin tocar — no declara cifra |
| `conectores/wisphub.yaml:311`, `tenants/rapilink.config.yaml:2726` | B. puntero a §5.11 del manual | Sin tocar — no repiten la cifra |

**Ya coherentes con 5, verificado:** `escalamiento.py:886`
(`if cantidad > 5`, el umbral que se ejecuta), `rapilink.config.yaml:584`
y `:1161` (las dos apariciones en el prompt), `test_guias_tv.py` §25
(con 6 avisa, con 5 no).

**Cambio.** `nucleo/seguimiento/supervisor.py:19`, 4 → 5. Es un ejemplo dentro
del docstring; no altera comportamiento.

**Resultado.** Suite 58/58. Sin referencias vigentes a 4 fuera del manual.

---

## Iteración 2 — MANUAL.docx: el documento controlado

**Hallazgo.** `corpus/rapilink/MANUAL.docx` es **MANUAL-001 v01**, fecha
2026-08-11, dirigido al rol `cliente_final`. Su registro de cambios interno va
por la entrada **5** (Agosto 12 de 2026, §5.12) aunque el campo `version` de la
cabecera sigue en `01`.

Dice 4 en cuatro lugares, todos regla vigente de negocio:

- §5.9 — «Lo recomendado es hasta **4** TV/TDT por instalacion (limite tecnico
  del splitter, no depende del plan contratado).»
- §5.9 — «Con mas de **4** puede fallar en algunos casos — si el cliente tiene
  mas de **4**, dejarle siempre esa recomendacion…»
- §5.11 — «…cantidad de TV/TDT conectados sobre el maximo de **4**, origen del
  cableado, y conexion fisica.»
- §5.11 — «Revisar cantidad de TV/TDT conectados sobre el maximo de **4** — el
  exceso tambien causa pixelacion…»

**Estado de ingestión: NUNCA se ingirió.** `MANUAL-001` no existe en
`asistente.documents` (19 documentos cargados, ninguno con ese código). El
`GUIA-ATENCION-01` que sí está cargado es otro documento.

**Consecuencia, y es la que importa:** el «4» **no es alcanzable hoy** por el
agente vía RAG — pero *ingerir este archivo tal como está inyectaría la regla
equivocada en el corpus del rol `cliente_final`*. La corrección del documento
es **prerrequisito** de la ingesta, no una tarea paralela.

**Decisión: DETENIDO, reportado, no modificado.** El repo tiene flujo
establecido para *ingerir* documentos (`cli/ingerir.py` → `cli/cargar_corpus.py`
→ aprobación desde /manual, versionado por hash), pero **no para redactar** el
`.docx`. Cambiar el texto exige número de versión, fila nueva en el registro de
cambios y las firmas de ELABORADO/REVISADO/APROBADO que el propio documento
declara. Eso es decisión humana; inventar el procedimiento estaba prohibido.

---

## Iteración 3 — estado del RAG

| Dato | Valor |
|---|---|
| Documento | `corpus/rapilink/MANUAL.docx` |
| Código / versión | `MANUAL-001` / `01` (registro de cambios en la entrada 5) |
| Rol destino | `cliente_final` |
| Estado de ingestión | **No ingerido** |
| Fragmentos que produciría | **39**, 0 defectos (`cli/ingerir.py rapilink`, que no escribe) |
| Fragmentos TV en el corpus actual | 32 mencionan TV/TDT/sintonización, repartidos en 8 documentos; **ninguno** enuncia el límite de televisores |
| Referencias 4/5 en el corpus cargado | Ninguna |

**Pendiente (requiere producción, no ejecutado):** corregir el manual a 5 →
`cli/ingerir.py rapilink` para revisar → `cli/cargar_corpus.py` → aprobar desde
/manual. En ese orden.

---

## Iteración 4 — resolución de guías sobre las 21 marcas

**Comprobado** con las 17 marcas que llevan guía propia, las 4 que no, y 8
erratas reales, contra `_ejecutar_consulta_guia_tv`:

- 17/17 resuelven a su guía específica.
- Panasonic, Iffalcon, Indurama y Simply → **general**, ninguna capturada por
  parecido. Vale la pena el detalle: `Iffalcon` es submarca de TCL en el mundo
  real y aun así no se le asigna la guía de TCL — como strings están lejos, que
  es lo correcto aquí.
- Erratas que caen en su marca y no en la general: `Sansung`→Samsung,
  `hisence`→Hisense, `sonny`→Sony, `phillips`→Philips, `Xiomi`→Xiaomi,
  `toshiva`→Toshiba, `chalenger`→Challenger, `kaley`→Kalley.
- TDT devuelve `tipo_guia='tdt'` para las 21 marcas y para marca vacía.

**Resultado.** Sin cambios de código: la resolución ya cumple la regla.

---

## Iteración 5 — auditoría de cobertura: `url_video` sin validar

**Problema.** `url_video` viaja **sin tocar** del catálogo al mensaje del
cliente (`_sirve` en `motor.py`: si está cargado, se entrega). Nada comprobaba
que fuera una dirección. Quien administra podía escribir `pendiente` o
`ver drive de calidad` y eso le llegaba al cliente como si fuera un video.

**Clase.** Bug dentro de las reglas aprobadas (sección 7 pide verificar la URL).

**Cambio.** `nucleo/config/schema.py`, validador de `GuiaTV`: exige esquema
`http://`/`https://`, rechaza espacios internos, y **recorta** el espacio
sobrante en vez de rechazarlo (pegar de más es un descuido de copiado, no un
enlace malo). El mensaje de error viaja tal cual a la pantalla, que ya lo
muestra sin resumir.

**Prueba.** `test_guias_tv.py` COBERTURA 29 — 8 aserciones.

**Resultado.** 8/8.

---

## Iteración 6 — auditoría de cobertura: el cliente que no sabe cómo está conectado

**Problema.** Sin `tipo_conexion` la herramienta manda a preguntar «¿entra
directo o pasa por una cajita?». Mucha gente no sabe contestar eso, y ahí el
agente se quedaba repitiendo la misma pregunta. Adivinar no es opción: los dos
procedimientos no se parecen y el equivocado manda al cliente a buscar
opciones que su equipo no tiene.

**Clase.** Hueco de cobertura sobre una regla aprobada (conexión ambigua).

**Cambio.** `nucleo/modelo/motor.py`, `instruccion_interna` del caso sin
conexión: se agrega la salida por **algo que se mira**, no que se sabe — ficha
redonda que se enrosca = `directo`; HDMI plano desde un aparatito = `tdt`.

**Prueba.** `test_guias_tv.py` COBERTURA 30 — 4 aserciones.

**Resultado.** 4/4.

---

## Iteración 7 — auditoría de cobertura: la casa con dos conexiones

**Problema.** Un TV moderno con el coaxial enroscado y otro analógico detrás
de un TDT es una casa **normal** — el propio `MANUAL-VENTAS-02` del corpus dice
que un televisor análogo necesita un TDT adaptado. La herramienta resuelve bien
las dos (no tiene límite por conversación, verificado), pero `sesion.tv_guia`
se **sobrescribía**: la ficha del escalamiento mostraba una sola conexión, y
quien iba a la casa se encontraba con un televisor del que nadie le había
hablado, y encima con el procedimiento del otro.

**Clase.** Bug contra una regla aprobada (el resumen de escalamiento debe
llevar el contexto correcto).

**Cambios.**
- `nucleo/seguridad/verificacion.py`: `Sesion.tv_guias` (lista).
- `nucleo/modelo/motor.py`: `_anotar` acumula además de sobrescribir, con
  deduplicación por conexión+marca (repetir la consulta no es otro televisor).
- `nucleo/seguimiento/escalamiento.py`: `_una_conexion()` y una rama en
  `ficha_tv` para más de una. La marca va **pegada a su conexión**: con dos
  televisores, «Marca: Samsung» en un renglón suelto no dice a cuál pertenece.

La ficha de una sola conexión **queda idéntica** — el 99% de los casos no ve
ningún cambio, y hay una aserción que lo fija.

**Prueba.** `test_guias_tv.py` COBERTURA 31 — 7 aserciones.

**Resultado.** 7/7.

---

## Iteración 8 — C3 y C4

Estado del laboratorio leído en vivo (solo lectura, sin escribir nada):
`Mario 5832` y `PRUEBA 6555`, ambas `status='Online'`, `catv='Enabled'`.

- **C4 — «CATV ya activado, no reintentar»: EJECUTABLE y EJECUTADO.**
  `Enabled` es justamente el estado que el caso necesita. Verificado 2/2 como
  sonda y convertido en **caso dorado permanente**: «con la TV ya habilitada en
  el equipo no se reintenta activarla», que afirma con `no_usa: [activar_catv]`
  — la única forma de afirmar que la escritura NO le ocurrió al equipo de
  nadie. El caso no escribe en ningún sistema, precisamente porque eso es lo
  que afirma.

- **C3 — «activar_catv con CATV realmente Disabled»: BLOQUEADO.**
  Ninguna ONU de laboratorio está en `Disabled`. Crear esa condición exige
  apagar el CATV de un equipo real, que es una escritura contra hardware fuera
  del alcance de este loop. **No se simuló.**

---

## Iteración 9 — contenido de las guías

`guias_tv` está **vacío en los dos lados**: 0 en la semilla
(`tenants/rapilink.config.yaml`) y 0 en producción (`config_version=138`).

La resolución funciona para las 21 marcas (iteración 4), pero **no hay una sola
guía cargada**. Redactar las 17 exige el paso a paso real de cada televisor y
las URLs de video, que son contenido del negocio. `GUDDI` no aparece en ninguna
parte del repo, así que la guía de TDT tampoco tiene texto de dónde salir.

**DETENIDO por decisión/insumo humano.** Escribir de memoria rutas de menú para
Olimpo, Caixun, Challenger o Daewoo sería exactamente lo que este bloque entero
existe para impedir — y el candado del motor terminaría protegiendo contenido
inventado. La regla «no inventar instrucciones» se aplica igual a las 17 que a
las 4 sin guía.

---

## Iteración 10 — matriz de la auditoría de cobertura

Los 22 escenarios de la sección 9, uno por uno.

| Escenario | Estado | Dónde |
|---|---|---|
| TV + TDT + splitter combinados | **Cerrado en esta iteración** | COBERTURA 31 |
| Varios TV | Cubierto | prompt (checklist), ficha `tv_cantidad_televisores` |
| Splitter con exceso de TV | Cubierto | `escalamiento.py:886` (`> 5`), §25 |
| Canales faltantes / ningún canal | Cubierto | casos dorados #55 y #56 (parrilla) |
| Sintonización sin resultado | Cubierto | #13, #14; ficha «siguió la guía y NO aparecieron» |
| Guía inexistente | Cubierto | §11 fail-closed, `_sin_guia` |
| Guía inactiva | Cubierto | §10 |
| **URL inválida** | **Cerrado en esta iteración** | COBERTURA 29 |
| Instrucciones incompletas | Parcial — ver decisión abierta 3 | §3 (vacía se rechaza) |
| Marca mal escrita | Cubierto | §7, 8 erratas verificadas |
| Marca desconocida | Cubierto | §8, §17-20 |
| **Conexión ambigua / no sabe si tiene TDT** | **Cerrado en esta iteración** | COBERTURA 30 |
| Cliente modifica cableado | Cubierto | ficha `tv_cableado_del_cliente` |
| Guía usada pero el problema persiste | Cubierto | #13, #14 |
| CATV sano pero TV sin canales | Cubierto | prompt rama «Todo sano» + C4 |
| Acciones CATV previas | Cubierto | prompt (Disabled → activar → sintonizar) |
| Cambio de estado tras acciones | Parcial | `reiniciar_ont` tiene `verificacion`; el veredicto de `activar_catv` sigue pendiente **por decisión previa, no se tocó** |
| Escalamiento | Cubierto | #12, #13, #14 |
| Evidencia fotográfica | Cubierto | §26, `_evidencias_de` |
| **Un TV funciona y otro no** | **Hueco — decisión abierta 1** | — |
| Guía entregada con video | Cubierto | §7, §14 |
| Marca que el resolutor ya identifica | Cubierto | §17 (`Sansung` no se anota como nueva) |

### Decisiones abiertas (no se inventó ninguna)

1. **«Un TV funciona y otro no.»** Ninguna regla aprobada dice qué hacer. El
   dato es fuerte —si uno anda, la señal llega bien a la casa y el problema es
   de ese televisor o de su tramo de cable— pero convertirlo en una rama del
   diagnóstico es una decisión de negocio, no una deducción del código.

2. **Casa con dos conexiones: qué se le ofrece primero.** La trazabilidad ya
   quedó completa (iteración 7), pero el orden en que el agente atiende un TV
   directo y un TDT en la misma casa no está definido.

3. **«Instrucciones incompletas».** El schema rechaza la guía activa vacía. Una
   guía con texto insuficiente pero no vacío (`"ok"`) no la puede detectar el
   código sin inventar un mínimo arbitrario. Se deja como está a propósito.

4. **Contenido de las 17 guías + la de TDT/GUDDI.** Ver iteración 9.

5. **Corrección del MANUAL.docx a 5 y su reingesta.** Ver iteraciones 2 y 3.

---

## Iteración 11 — carga inicial de las guías

**Fuentes usadas, en el orden que pide la especificación.**

`MANUAL-001 §5.12` («Orientación para Sintonizar el TV o TDT», del propio
corpus) resultó ser la fuente verificada del negocio, y decide todo:

- «La señal llega por coaxial pero se sintoniza como **ANTENA**, no como
  "Cable" — confirmado con el área técnica.» Un televisor puesto en Cable no
  encuentra nada.
- «Si el TV tiene una sola entrada combinada ("Antena/Cable"), esa misma alcanza.»
- **«No hay un paso a paso exacto verificado por marca de TV ni del TDT.»**
- Da seis rutas como **orientativas**: Samsung, LG, y el grupo Android/Google TV
  (Sony, TCL, Hisense, Philips).
- «Nunca insistir en el nombre exacto de un menú si el cliente no lo encuentra.»
- «Avisarle que la búsqueda puede tardar varios minutos.»

**Consecuencia sobre qué se escribió.** Las seis marcas con ruta llevan su ruta;
las once restantes llevan la orientación genérica aprobada — que es lo que el
manual manda usar cuando no se conoce el menú. **Ninguna guía afirma una ruta
que nadie verificó.** Lo específico de esas once es el video.

**GUDDI.** No hay manual de pasos. Verificado: es marca colombiana, decodificador
**DVB-T/T2**, con salida HDMI, menú en pantalla y búsqueda automática/manual
(ficha de producto de Agaval). Esto además explica el «Antena, no Cable»: la
señal que Rapilink entrega por el coaxial es de norma terrestre.

Los pasos salen de `G-GO-07` del corpus (procedimiento de decodificador),
**adaptados**: ese documento describe **TDT aéreo** —«conecta la antena TDT»,
«orientación de la antena», «línea de vista»— y esos pasos **se dejaron fuera a
propósito**. En Rapilink el coaxial viene de la salida CATV de la ONU.

**Un hallazgo de la carga: los 17 videos no llegaban al cliente.** Con el
catálogo ya cargado, cuatro conversaciones seguidas contra el motor real
entregaron los pasos y **ningún enlace**. No era desobediencia: el prompt pide
mensajes de una o dos líneas, y al recortar el enlace es lo primero que sobra.
Se agregó una frase a `instruccion_interna` **solo cuando hay video** — nombrar
un enlace inexistente es justo lo que invita a inventarlo. Verificado después:
Samsung y Olimpo entregan el suyo; Panasonic, que cae en la general, no inventa
ninguno.

**Prueba.** `test_guias_tv.py` COBERTURA 32 — 4 aserciones.

---

## Iteración 12 — las tres decisiones de negocio, ya resueltas

### 33. Un televisor anda y otro no → visita técnica

Era la decisión abierta 1. Implementada en código:

- `escalamiento.py`, esquema de evaluación: campo **opcional**
  `tv_algunos_televisores_con_senal`. Opcional a propósito — una conversación
  de facturación no lo contesta.
- `ficha_tv`: la observación va **arriba de todo**, no entre los demás datos.
  Sepultada entre «televisores conectados: 3» y «tiene splitter» se lee como un
  detalle más, y es lo primero que necesita quien va a la casa.
- Prompt del rol: ese caso corresponde visita técnica y no se sigue intentando
  por chat.

El porqué, que la ficha explica: **si un televisor tiene canales, la señal
llega a la casa.** La ONU, el puerto CATV y la acometida quedan descartados de
una, y lo que falla está de la derivación hacia adentro. Sin decirlo, quien
recibe el caso lee «no tiene señal de TV» y sale a revisar la acometida — justo
lo único que ya sabemos que está bien.

### 34. Casa con varias conexiones → sin prioridad

Era la decisión abierta 2. El mecanismo ya estaba (iteración 7); lo que faltaba
era **fijar que no hay jerarquía**. Se agregó al prompt que se llame a la
herramienta una vez por conexión y se atienda de a uno sin mezclar los pasos, y
pruebas que exigen que la ficha no diga «principal», «primero», «prioridad» ni
«secundaria»: lo que hay es un orden de conversación, no una jerarquía.

### 35. Texto corto pero no vacío → responsabilidad del humano

Decisión de **no implementar**, y por eso lleva prueba igual. Un umbral de
longitud rechazaría guías legítimas —`Menu > Canales > Auto > Antena` son 30
caracteres y está completa— y no atajaría la que de verdad importa: una guía
larga y equivocada. Lo único que se sigue rechazando es la **vacía**, que sí es
medible.

La prueba incluye una guarda que lee `class GuiaTV` y falla si aparece un
`len(self.instrucciones)`. Existe para que el próximo que lea «instrucciones
insuficientes» en la lista de huecos no agregue el mínimo.

### Verificación

Las tres decisiones se comprobaron **apagando la implementación**: con la
observación de la 33 desactivada caen 3 aserciones. Restaurado y confirmado que
no quedó ningún `if False:` en el archivo.

`test_guias_tv.py` pasa de 171 a **191 aserciones**.
