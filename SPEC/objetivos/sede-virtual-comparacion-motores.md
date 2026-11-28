# Comparación de motores gráficos para la sede virtual

**Estado:** abierto · **Decisión:** NO TOMADA · **Fecha:** 01/11/2026
**Rama:** `spec/sede-virtual` (sin push, sin despliegue)

---

## Por qué existe este documento

El 31/10/2026 se reconstruyó la sede con PixiJS y el resultado **no se aprobó**.
La razón, en palabras del dueño del producto: *«el edificio continúa siendo
demasiado largo, estrecho y lineal respecto a nuestra referencia arquitectónica
aprobada»*, y una instrucción que vale más que la queja:

> No quiero conservar la distribución lineal únicamente porque actualmente
> cumple las pruebas de oclusión.

Esa frase es correcta y conviene no suavizarla: la franja larga **no era una
decisión de diseño**, era el residuo de una restricción técnica que se había
dado por inevitable. Este documento mide si lo era.

El encargo fue explícito: *«Autorizo desarrollar un spike visual aislado
utilizando Three.js con cámara ortográfica. No reemplazar todavía PixiJS»*, y
*«No declares ganador por FPS únicamente»*.

---

## La causa real de la franja, y por qué no es el motor

Conviene decirlo con precisión, porque la respuesta corta —«es que PixiJS es
2D»— es falsa y llevaría a cambiar de motor por el motivo equivocado.

En `nucleo` del prototipo actual ([edificio.js](../../django-crm/frontend/src/lib/centro-mando/edificio.js))
los tres niveles se dibujan **siempre**, ordenados por el algoritmo del pintor.
Con esa estrategia, la losa del nivel de arriba tapa el fondo del de abajo, y
cuánto tapa lo gobierna una desigualdad medida y escrita en ese archivo:

```
H > z_placa + (P − d) / 0,8125
```

Para **una** fila de salas sale `H > 12,75`, de donde los 15 que usa hoy.

> **CORRECCIÓN DEL 01/11/2026, POR LA TARDE.** Acá este documento decía que dos
> filas exigirían `H > 28,7` —un edificio de 86 unidades para 40 de planta— y
> que por eso la planta compacta no cabía en PixiJS. **Era una estimación
> presentada como una medición, y es falsa.** La desigualdad se aplicó a una
> huella entera cuando este motor dibuja **una losa por sala**, no una losa
> corrida: entre dos filas hay un pasillo, y por ese hueco se ve. Medido con la
> inversa de la proyección —la misma de `edificio.test.js`— la planta compacta
> **no tapa ni un puesto a la altura de piso actual**. El detalle, y lo que sí
> resultó ser el límite, está en *La opción B, medida* más abajo.

**La restricción no viene del motor: viene de dibujar siempre todos los pisos.**
Un piso aislado no tiene nada encima, así que su planta puede ser todo lo
profunda que quiera. Lo que Three.js aporta no es «dibujar mejor» —ningún motor
dibuja bonito, dibuja lo que se le modela— sino que **apagar, atravesar y
cortar capas sea correcto por construcción**, con su buffer de profundidad y sus
planos de recorte, en vez de ser una excepción a mano en el orden de pintado.

---

## Qué se construyó

Un prototipo **aislado**, en `/centro-mando/spike-three`, que no toca nada del
prototipo actual. Come de los **mismos datos**: su `+page.server.js` reexporta
el `load` de `/centro-mando/v2` en vez de copiarlo, para que la comparación no
mida dos lecturas distintas y para que no se desincronice en silencio.

| Archivo | Qué es |
|---|---|
| [three/distribucion.js](../../django-crm/frontend/src/lib/centro-mando/three/distribucion.js) | La planta compacta. **Puro, sin Three.js**: la distribución es geometría, no dibujo, y tiene que poder probarse sin lienzo. Si mañana el motor fuera otro, esto se queda |
| [three/escena-three.js](../../django-crm/frontend/src/lib/centro-mando/three/escena-three.js) | El renderizador: cámara ortográfica isométrica, tres modos de ver, selección por rayo, rótulos en HTML |
| `spike-three/+page.svelte` | La pantalla de comparación |

Expone los **mismos cuatro verbos** que la escena de PixiJS —`aplicar`,
`seleccionar`, `metricas`, `destruir`—. No es estética: si los dos prototipos
comparten puerta, cambiar de motor es cambiar un archivo y no reescribir la
pantalla. Eso es parte de lo que había que medir, y se midió construyéndolo.

**Y un módulo se comparte tal cual entre los dos motores**: `escena/rotulos.js`,
que separa los nombres que se pisan. La separación de rótulos es un problema de
pantalla y no depende del motor. Que se pueda compartir es, en sí mismo, un dato.

### Los tres modos de ver

Son las tres salidas que existen al problema de la oclusión, y el prototipo las
implementa todas para poder compararlas:

| Modo | Qué hace | Qué resuelve |
|---|---|---|
| **Corte** | Dos planos de recorte quitan la esquina que mira a la cámara | Se ve dentro de los tres pisos a la vez, como la sección abierta de la referencia |
| **Rayos X** | Las losas superiores se vuelven traslúcidas y la cubierta se apaga | Los tres pisos a la vez, sin perder volumen |
| **Aislamiento** | Un solo piso, con nada encima | Donde se **garantiza** que ningún departamento queda escondido |

---

## La medición que motivó todo

Misma empresa, mismos datos, las dos distribuciones. Medido con
[three/distribucion.test.js](../../django-crm/frontend/src/lib/centro-mando/three/distribucion.test.js),
que construye las salas con `salasDe` —el mismo camino que usa la pantalla— y
no con una maqueta propia:

```
LINEAL    ancho 88,2   fondo 18,2   alto 48,4    esbeltez 4,85
COMPACTO  ancho 40     fondo 38     alto 21      esbeltez 1,05

  P3   2 salas · 1 fila  · 2 columnas
  P2   4 salas · 2 filas · 2 columnas
  P1   5 salas · 3 filas · 2 columnas
```

**La esbeltez baja de 4,85 a 1,05 y la altura se reduce a menos de la mitad.**
Los 15 de altura entre pisos del prototipo lineal no eran estéticos: eran el
mínimo que la desigualdad permitía. Aislando el piso bastan 7.

---

## La opción B, medida: PixiJS con la planta compacta

Esta sección la pidió el dueño del producto después de leer el spike, y la
pregunta era la correcta:

> ¿Podríamos conseguir una distribución compacta en PixiJS si aislamos los pisos
> y cambiamos la composición, sin abandonar su sistema de personajes e
> interacciones?

**Sí se puede, y bastante más fácil de lo que este documento decía.** Lo que no
entra es una sola pieza, y resultó no ser ninguna oficina.

### El experimento

No se construyó una segunda aplicación: se escribió un constructor de geometría
—[edificio-compacto.js](../../django-crm/frontend/src/lib/centro-mando/edificio-compacto.js),
205 líneas— que devuelve **el mismo contrato** que `edificioDe` y reparte las
salas con la misma `repartirPiso` que usa el spike. La pantalla `/centro-mando/v2`
lo dibuja con `?planta=compacta`; sin el parámetro es la de siempre. Así la
misma escena, los mismos personajes y la misma ficha de puesto dibujan las dos
distribuciones, y la comparación no mide dos programas distintos.

De `edificio.js` **no se cambió una línea de conducta**: sólo se exportaron dos
funciones que ya existían (`nucleo` y `circulacion`). Sus 48 pruebas siguen en
verde.

### Lo medido

Con la inversa de la proyección, la misma de `edificio.test.js`, sobre la
empresa del piloto (11 salas, 3 pisos, 33 puestos) y sobre el fixture por
defecto:

| Qué se dibuja | Puestos tapados | Edificio |
|---|---|---|
| A · lineal, como está hoy | **0** de 33 | 88,2 × 18,2 × 48,4 · esbeltez 4,85 |
| B · compacta, **sin** cubierta | **0** de 33 | 40 × 38 × 42 · esbeltez 1,05 |
| B · compacta, **con** cubierta | **9** de 33 | ídem |
| B · compacta, un piso aislado | **0** de 33 | 40 × 38 |
| C · Three.js, con cubierta y con corte | 0 (por construcción) | 40 × 38 × **21** |

**La única pieza que tapa algo es la cubierta.** Ni las salas entre sí, ni el
núcleo apilado, ni el basamento: cero. La prueba lo afirma nombrando al
culpable, no contando víctimas.

Por qué: una cubierta sobre una huella de 39 celdas de fondo tiene que ser
cruzada por la proyección entera. En la distribución lineal el mismo remate no
tapa nada porque esa huella tiene 18 de fondo. **Lo que cambió no es el remate:
es la profundidad que la proyección tiene que atravesar.**

Y para que la cubierta quepa, la altura de piso tendría que subir de 15 a **38**
—barrido completo de 15 a 130, primera altura limpia: 38—, o sea un edificio de
**114 unidades sobre una planta de 39 × 39**. Ese es el número que este
documento le atribuía al caso general; sólo vale para esta pieza.

### Lo que B gana, y lo que cuesta

**Gana todo lo de interacción, que es mucho:** selección por puesto, navegación
edificio → piso → sala, ficha de agente, flujo en vivo, 37 personajes animados.
Nada de eso hay que reconstruirlo, porque el contrato es el mismo.

**Cuesta tres cosas, las tres medidas:**

1. **La cubierta, o el doble de altura.** O el edificio no lleva remate —y un
   edificio sin cubierta no se lee como un edificio—, o mide 114 de alto. En
   tres dimensiones la cubierta se recorta o se apaga y lo de abajo sigue
   siendo correcto sin recalcular nada: es exactamente lo que hace el modo
   «Rayos X» del spike.
2. **La visibilidad de las oficinas es una coincidencia de la rejilla, no una
   propiedad del diseño.** A 15 se ve entera; **entre 16 y 29 se tapan de dos a
   cuatro puestos**; a partir de 30 vuelve a verse. Funciona porque los
   pasillos del piso de arriba caen justo donde están los escritorios del de
   abajo. Cambiar el pasillo, el fondo de una plantilla o agregar una sala
   mueve esa coincidencia, y el síntoma es un puesto que nadie ve, sin error y
   sin aviso. Hay una prueba que falla si alguien sube la altura de piso.
3. **La envolvente no está escrita para una huella en rejilla.** Fachada,
   extremo acristalado y el canto de losa con el nombre al frente se colocan en
   `edificio.js` con una aritmética que supone **una fila** (`frente`,
   `sostiene`, `anchoDeNivel`). El constructor compacto no los dibuja, a
   propósito: rehacerlos es el trabajo que esta comparación tiene que medir, no
   el que tiene que hacer antes de que se decida el motor. **Es el hueco visual
   más grande de B y hay que contarlo al mirar su captura.**

### Qué prueba esto, y qué no

Prueba que **la compacidad no era motivo suficiente para migrar**: se consigue
en PixiJS sin tocar los personajes ni las interacciones. Elimina el argumento
más fuerte que tenía el spike.

No prueba que B y C se vean igual. B paga la oclusión **separando pisos** —42
unidades de alto, o 114 con cubierta— y C la paga **con profundidad real**, 21
de alto, con remate y con corte. Esa diferencia se ve en una captura y todavía
no está capturada: ver *Lo que falta verificar*.

---

## Los ocho criterios de comparación

Los que pidió el dueño del producto, en su orden. **Cumplido / parcial /
incumplido**, con la evidencia al lado.

| # | Criterio | A · PixiJS lineal | B · PixiJS compacto | C · Three.js compacto | Quién gana |
|---|---|---|---|---|---|
| 1 | **Parecido con la referencia** | **Parcial.** Franja de esbeltez 4,85 | **Cumplido en planta**, parcial en volumen: esbeltez 1,05 pero 42 de alto y sin envolvente | **Cumplido.** Esbeltez 1,05, 21 de alto, sección abierta, vidrio, núcleo visible | **C**, y **B queda cerca** |
| 2 | **Compacidad** | **Incumplido.** 88,2 × 18,2 × 48,4 | **Cumplido en huella**, parcial en volumen: 40 × 38 × 42 | **Cumplido.** 40 × 38 × 21 | **C**, medido; **B** resuelve la huella |
| 3 | **Visibilidad de departamentos** | **Cumplido.** Una fila por piso, todas las salas a la vez | **Cumplido sin cubierta**, 0 de 33 tapados. **Con cubierta: 9 tapados** | **Cumplido.** Corte, rayos X y aislamiento; la cubierta se apaga | **C**: en B la visibilidad y el remate no pueden coexistir |
| 4 | **Profundidad arquitectónica** | **Parcial.** Tres caras y un orden de pintado | **Parcial.** La misma, con más filas | **Cumplido.** Volúmenes reales, sombras, buffer de profundidad | **C** |
| 5 | **Iluminación y materiales** | **Parcial.** Luz pintada: tonos fijos por cara | **Parcial.** Idéntica a A | **Cumplido.** Luz calculada, sombras, vidrio | **C**, pero ver «lo que esto cuesta» |
| 6 | **Interacción** | **Cumplido.** Puesto, navegación, ficha, flujo en vivo | **Cumplido.** Lo hereda entero: mismo contrato, misma escena | **Parcial.** Selección por sala, aislamiento, ficha mínima | **A y B**, por madurez y no por capacidad |
| 7 | **Rendimiento** | 90–99 fps, mín 87 · 2.426 objetos | sin medir (falta el navegador) | 131–144 fps, mín 84 · 413 objetos · 554 llamadas · 10.240 tri | **No concluyente** — ver abajo |
| 8 | **Escalabilidad y mantenimiento** | 6 archivos al motor, ~4.000 líneas, 552 pruebas | **+205 líneas y 20 pruebas** sobre lo que ya existe; 2 funciones exportadas | 2 archivos, ~700 líneas, 16 pruebas. Dependencia nueva de 1,2 MB | **B es el más barato con diferencia** |

**Dónde quedó la comparación después de medir B:** C gana los ejes visuales
(1, 2, 4, 5) y la visibilidad con remate (3). B gana interacción (6) y coste
(8) por un margen grande. El eje 7 no decide. **El empate se rompe en el eje
que todavía no está medido: los personajes.**

### El rendimiento NO decide, y conviene explicar por qué

El spike marca más fotogramas, y **esa cifra no significa lo que parece**:

- Las dos escenas **no tienen el mismo contenido**. La de PixiJS dibuja todo el
  mobiliario, los racks, las plantas, los marcadores de presencia y **37
  personajes animados con su reloj propio**. El spike dibuja cajas y figuras
  sentadas que no se mueven.
- El contador está **atado al refresco de la pantalla**. Una página en blanco
  en el mismo navegador y el mismo momento marcó **135 fps**: lo que el número
  mide es si se pierden fotogramas, no la capacidad del motor.
- Los dos están **por encima de 60 sostenidos**, que es el umbral que importa.

**Conclusión del eje 7: ninguno de los dos tiene un problema de rendimiento, y
el rendimiento no debe decidir esta elección.** Era, literalmente, la
instrucción recibida.

---

## Las capturas

En [documentos/sede/capturas/spike-three/](../../documentos/sede/capturas/spike-three/):

| Archivo | Qué muestra |
|---|---|
| `three-0-primera-version-con-niebla.png` | **El primer intento, negro.** Se guarda porque la causa es una lección: con cámara ortográfica la posición se pone a 300 unidades para que el volumen de vista cubra el edificio, así que una niebla pensada para distancias de escena se traga el edificio entero. Parecía un problema de luz |
| `three-1-edificio-corte.png` | La vista de conjunto con el corte: tres pisos, interiores cálidos, cubierta, fachada |
| `three-2-piso-aislado.png` | **La captura que justifica el spike.** P1 con sus cinco departamentos en dos filas, todos visibles, sin oclusión posible |
| `three-3-rayos-x.png` | El modo traslúcido, **con el defecto conocido** de la cubierta opaca |

Y del lado de PixiJS, `documentos/sede/capturas/` conserva la serie del 31/10
más `pixi-rotulos-separados.png`, del arreglo de rótulos de hoy.

---

## Lo que el spike NO demuestra

Esto importa tanto como lo anterior.

1. **No demuestra que Three.js dibuje mejor.** Demuestra que permite una planta
   compacta sin perder visibilidad. La calidad artística depende de modelos,
   materiales, iluminación y animación, que hay que construir igual.
2. **No es comparable en madurez.** El prototipo de PixiJS tiene selección por
   puesto, ficha de agente, flujo de acontecimientos en vivo, demostración,
   bitácora y 552 pruebas. El spike tiene selección de sala y una ficha mínima.
   Migrar significa reconstruir todo eso.
3. **No midió una planta compacta en PixiJS.** Es posible: bastaría aplicar la
   misma estrategia —aislar el piso para la planta profunda— con el compositor
   actual. Sería más frágil, porque cada excepción al orden de pintado abre un
   agujero nuevo, **pero no está medido**, y presentarlo como imposible sería
   repetir el error que este documento corrige.
4. **La dependencia no es gratis.** `three@0.187.0` son ~1,2 MB; habría que
   medir qué llega al navegador con el empaquetado real.

---

## Defectos conocidos del spike

Honestidad sobre el estado real, no sobre el estado deseado:

| # | Qué | Estado |
|---|---|---|
| S1 | En «Corte», los rótulos de salas tapadas se dibujaban **sobre la cubierta**, nombrando algo que no se ve | **Corregido en código, SIN VERIFICAR.** El motor de Docker se cayó antes de la comprobación |
| S2 | En «Rayos X» la cubierta seguía opaca: el botón respondía y la vista no cambiaba | **Corregido en código, SIN VERIFICAR**, mismo motivo |
| S3 | La planta compartida hace que un piso con pocas salas tenga mucho suelo vacío | Abierto. Es el precio de un volumen único; el prototipo lineal lo resolvía escalonando |
| S4 | Los personajes son cápsulas sin animación | A propósito: el spike compara arquitectura |

**Tres defectos propios se cazaron midiendo, y los tres tenían el mecanismo
puesto y el efecto ausente** —que es justo lo que §6 de `CLAUDE.md` llama
*una prueba que dice que algo existe no prueba que funcione*:

- La niebla, que dejaba la escena negra con toda la luz correcta.
- Las lámparas cálidas a intensidad 46 con decaimiento cuadrático: a diez
  unidades del foco eso son 0,46 y no ilumina nada. Estaban puestas y no se
  veían.
- El encuadre medía la **explanada** y no el edificio, así que la sede entraba
  ocupando un tercio de la pantalla.

Y uno más, de método: el trazador de rayos **no conoce los planos de recorte**,
así que chocaba con la esquina que ya no se dibuja y ocultaba todos los
rótulos. En cámara ortográfica, además, los rayos son paralelos: lanzarlos
desde la posición de la cámara es un rayo de perspectiva que no corresponde a
lo que la pantalla muestra.

---

## Los personajes: qué haría falta en cada alternativa

Pedido explícito: *«No reconstruir todavía el sistema de personajes. Documentar
qué necesitaríamos para implementar locomoción ambiental, animaciones naturales
y selección de personajes en cada alternativa.»* Esto es ese documento. **No se
construyó nada de esto.**

### Qué hay hoy, y cuánto de eso sobrevive a una migración

| Pieza | Qué es | ¿Depende del motor? |
|---|---|---|
| [pose.ts](../../django-crm/frontend/src/lib/centro-mando/escena/pose.ts) · 304 líneas | La animación entera **como números**: desplazamientos, giros, intensidades, y la transición por interpolación | **No.** Ni un gráfico, 22 pruebas en Node. **Sobrevive intacto a cualquier migración** |
| [personaje.ts](../../django-crm/frontend/src/lib/centro-mando/escena/personaje.ts) · 349 líneas | La figura: primitivas `Graphics` articuladas por piezas con nombre | **Sí, del todo.** Se reescribe |
| Los cinco estados | `reposo`, `teclear`, `alerta`, `despachar`, `incognito` — todos **sentados** | No |

Ese corte es la mejor noticia de toda la comparación: **la lógica de animación
no está acoplada al motor.** Lo que una migración cuesta en personajes son las
349 líneas de la figura, no las 304 de cómo se mueve. Y `pose.ts` está escrito
para que agregar estados sea barato por construcción —cada estado declara su
pose y la transición se interpola—, así que las tres poses nuevas que pide
caminar (`levantarse`, `caminar`, `sentarse`) son el trabajo más chico de los
tres que siguen.

### Lo que falta, en cualquiera de las tres opciones

1. **Una figura de pie.** Las cinco poses actuales son de alguien sentado:
   `piernas` existe pero dobladas bajo el escritorio. Caminar necesita un
   dibujo distinto, no una pose distinta.
2. **Un recorrido.** El dato ya está: cada planta declara su `pasillo` como un
   rango, y el núcleo es el nexo entre pisos. No hace falta inventar un mapa.
3. **Procedencia `ambiente`.** Decidido el 01/11/2026 y congelado: un
   movimiento ambiental **nunca** entra al historial ni se cuenta como
   actividad. Es una regla de datos y no cambia con el motor. Ver
   [sede-virtual-reconstruccion.md](sede-virtual-reconstruccion.md).

### Y lo que cambia según el motor

**En 2.5D (A y B) el costo verdadero no es la animación: es el orden de
pintado.** Hoy cada personaje cuelga del contenedor de su sala y el orden se
calcula **una vez**, al montar, con `gz·1000 + gx + gy`. Un personaje que
camina cambia su `gx + gy` en cada fotograma, así que **cambia de lugar en el
orden en cada fotograma**: tiene que pasar por delante de la mesa que acaba de
dejar y por detrás de la que va a cruzar. Eso significa reordenar por
fotograma, y cada excepción a mano en ese orden es exactamente la clase de
agujero que este documento viene midiendo. **Es trabajo nuevo y no tiene
atajo.**

**En 3D (C) ese problema no existe.** El buffer de profundidad lo resuelve por
geometría: un personaje que camina es una posición que cambia. Lo que C no
tiene es **la figura**: el spike dibuja cajas. Hay dos caminos y conviene no
confundirlos de coste:

- **Mallas simples articuladas a mano**, como el personaje de PixiJS pero en
  tres dimensiones. Mismo trabajo que las 349 líneas actuales, con `pose.ts`
  manejándolas igual.
- **Modelos con esqueleto** (glTF + `AnimationMixer`), que es el camino por el
  que un personaje se ve *natural* y no articulado. Esto **no es código**: es
  una canalización de activos —modelar, riguear, animar, versionar— y es la
  inversión más grande de todo lo que este documento discute. Si lo que se
  busca es «buenos personajes y movimientos naturales», **este es el renglón
  que decide, y no la geometría del edificio.**

### Selección de un personaje

| | A y B | C |
|---|---|---|
| Hoy | **Funciona.** Selección por puesto, ficha con agente, área y motivo | **No existe.** Selección por sala con trazador de rayos |
| Lo que falta para un personaje que camina | Que la zona sensible siga al personaje en vez de al puesto | Lo mismo, más construir la selección por personaje |

En las dos, una vez que alguien camina, **la ficha deja de poder anclarse al
puesto**. Es el mismo trabajo en los dos motores.

---

## Lo verificado en navegador, y lo que encontró

El motor de Docker siguió caído toda la sesión —`com.docker.backend` ausente, el
*named pipe* inexistente, el reenvío de puertos del laboratorio muerto con él— y
**no se reinició**, por restricción explícita. El laboratorio no volvió.

Se verificó igual, por otro camino: **un banco de capturas que sirve los módulos
de la sede directamente del árbol de trabajo**, con Node despojando los tipos de
TypeScript (`stripTypeScriptTypes`) y un mapa de importación para `three` y
`pixi.js`. Los datos salen del fixture del repositorio, no de la base.

**Qué NO es esto.** No es el laboratorio: no hay backend, ni sesión, ni empresa
real, ni la pantalla de `/centro-mando/v2` con su cabecera, su ficha y su flujo
en vivo. Mide **el dibujo**, que es justo lo que esta comparación necesita. Y el
contador de fotogramas de un navegador sin ventana está limitado a 60: los
números de rendimiento del eje 7 **no se midieron acá** y siguen siendo los del
laboratorio.

### Lo que la verificación encontró, que es el motivo de hacerla

**El arreglo de los rótulos estaba puesto y no servía: se veía UN nombre de
once.** Y el trazador de rayos tenía razón —el ancla estaba en el centro de la
sala, que está bajo la cubierta— así que la prueba era correcta y la pregunta
estaba mal: no es *«¿se ve el centro?»* sino *«¿se ve algo de esta sala, y
dónde?»*. Ahora cada rótulo prueba seis anclajes, de la esquina que mira a la
cámara hacia adentro, y se ancla al primero visible: **8 de 11**, y los tres
que faltan están de verdad detrás del edificio.

**Y apareció un tercer caso de la misma familia, que ninguna prueba sin pantalla
iba a encontrar: el trazador de rayos tampoco sabe que un objeto está APAGADO.**
En «Rayos X» la cubierta se apaga —el botón funciona, el techo desaparece— y aun
así era ella la que bloqueaba **27 de 40 rayos**, así que el modo que existe
para ver los pisos de arriba era justo el que se quedaba sin sus nombres. Las
tres cosas que el rayo ignora están ahora en una sola regla, `noTapa`: la
esquina recortada, lo apagado y lo traslúcido.

Es exactamente lo que CLAUDE.md §6 llama *el mecanismo puesto y el efecto
ausente*, dos veces más, y las dos sólo se veían mirando.

### El estado de cada pendiente

| # | Qué | Estado |
|---|---|---|
| 1 | Los rótulos de salas tapadas | **verificado, y estaba mal**: 1 de 11 → 8 de 11 |
| 2 | «Rayos X» apaga la cubierta | **verificado**: se ve el piso 3 desde arriba |
| 3 | Captura de A, B y C en condiciones equivalentes | **hecha**, ocho capturas |
| 4 | Errores de consola | **cero**, en las tres opciones y en los tres modos |
| 5 | Oclusión y navegación en B | **medidas**: ver la captura con cubierta |
| 6 | Rendimiento de B (eje 7) | **sin medir**: el banco limita a 60 fps |
| 7 | Las suites | **413 verdes, 0 rojas** en 14 archivos, con el arnés de Node |

Lo que sigue **sin** verificarse, y conviene decirlo: la pantalla completa de
`/centro-mando/v2` con `?planta=compacta` —cabecera, ficha de puesto, flujo en
vivo, bitácora— no se abrió nunca. El banco monta la escena, no la pantalla.

### Lo que las capturas muestran

En [documentos/sede/capturas/comparacion/](../../documentos/sede/capturas/comparacion/).

- **A · lineal.** 95,2 × 18,2, esbeltez 5,23. Las once salas se ven, con todo el
  mobiliario y los personajes. Se entiende de un vistazo por qué no se aprobó.
- **B · compacto, con cubierta.** 39 × 39, esbeltez 1,00 — y **la cubierta borra
  el piso de arriba entero**: «NOC y Redes» queda rotulado sobre un techo
  vacío. Es el defecto que la aritmética había contado como «9 puestos
  tapados», visto.
- **B · compacto, sin cubierta.** Las once salas a la vista, dos filas por piso,
  y el edificio se lee como **tres bandejas flotando** con el núcleo asomando:
  justo lo que `edificio.js` escribió que había que evitar.
- **B · piso 1 aislado.** La mejor imagen de B, y la que defiende su caso: cinco
  salas en dos filas, mobiliario completo, personajes con su placa de nombre.
- **C · corte, rayos X y piso 1.** El volumen compacto con remate, los tres
  pisos abiertos desde arriba, y la planta de dos filas con sus cinco nombres.
- **C · el defecto encontrado**, guardado a propósito: un solo rótulo de once.

**La comparación honesta está entre `B-pixi-compacto-piso1.png` y
`C-three-piso1.png`**: la misma planta, la misma empresa, el mismo encuadre. B
tiene mobiliario y gente; C tiene volumen, luz y remate.

---

## Recomendación

**La decisión NO está tomada, y después de medir la opción B lo está menos que
antes** — que es el resultado correcto de una comparación honesta: el argumento
más fuerte que tenía Three.js se cayó.

Lo que está medido y no depende de opinión:

- La compacidad **es alcanzable en los dos motores**: 4,85 → 1,05 en C y
  4,85 → 1,05 en B, con la misma empresa y el mismo reparto.
- La causa de la franja **no era el motor** sino dibujar siempre todos los
  pisos, y **mi estimación de lo que eso costaba en PixiJS estaba mal**: no hace
  falta una torre de 86, hace falta renunciar a la cubierta o subir la altura de
  piso a 38.
- Lo que separa a B de C ya no es la planta: es que en C **cortar, atravesar y
  apagar capas es correcto por construcción**, y en B cada una de esas tres
  cosas es una excepción al orden de pintado. Se ve en la cubierta y se ve en el
  personaje que camina.
- **B es muchísimo más barato**: 205 líneas y 20 pruebas sobre lo que ya existe,
  contra reconstruir selección, ficha, flujo en vivo, bitácora y 552 pruebas.
- El rendimiento **no decide**: los dos sobran, y el de B todavía no se midió.

Lo que falta antes de decidir, en orden de peso:

1. **Los personajes.** Es el eje que rompe el empate, no la geometría. Si lo
   que se busca es movimiento natural con modelos con esqueleto, eso es una
   canalización de activos que sólo tiene camino hecho en 3D, y entonces decide
   C. Si alcanza con figuras articuladas como las de hoy, `pose.ts` sirve igual
   en los dos y entonces el coste decide B. **La referencia del eje 3 que el
   dueño del producto va a desarrollar es, literalmente, el dato que falta.**
2. **Ver las tres capturas juntas.** B paga la oclusión con altura —42, o 114
   con cubierta— y C con profundidad real —21, con remate y con corte—. Esa
   diferencia no se decide leyendo números.
3. **Verificar los dos arreglos del spike** en el navegador.
4. **La referencia del eje 6** (cámara).

**Lo que NO recomiendo:** decidir ahora. Ni por rendimiento —era la
instrucción—, ni por líneas de código, ni por la compacidad, que acaba de dejar
de distinguir a los dos candidatos.

---

## Lo que NO se tocó

Por restricción explícita, y comprobado:

- Sin `push`, sin despliegue, sin tocar producción.
- Sin modificar el motor Python.
- Sin reconstruir el sistema de acontecimientos.
- Sin inventar agentes ni empleados: el spike pinta **sólo** los puestos que la
  organización declara ocupados, con el mismo `agente`/`persona` que la escena
  actual.
- Sin alterar permisos ni el aislamiento multiempresa: la empresa sale de
  `tenantDeLaSesion` en el servidor, igual que en `/centro-mando/v2`, porque es
  literalmente el mismo `load`.
- El prototipo de PixiJS queda **íntegro y recuperable**, y acá hay que ser
  preciso porque la segunda mitad de la sesión sí tocó dos de sus archivos:
  - `edificio.js`: se exportaron `nucleo()` y `circulacion()`, que ya existían.
    **Cero cambios de conducta**, y sus 48 pruebas lo miden.
  - `v2/+page.svelte`: la opción B se dibuja sólo con `?planta=compacta`. Sin el
    parámetro la pantalla hace exactamente lo que hacía.
  - El spike de Three.js no tocó ninguno de los dos.
  - La etiqueta `sede-pixi-2026-10-31` sigue apuntando al estado anterior.
