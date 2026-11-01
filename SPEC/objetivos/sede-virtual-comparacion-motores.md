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

Para **una** fila de salas sale `H > 12,75`, de donde los 15 que usa hoy. Para
**dos** filas haría falta `H > 28,7`: un edificio de 86 unidades de alto para
40 de planta. Una torre, no una sede.

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

## Los ocho criterios de comparación

Los que pidió el dueño del producto, en su orden. **Cumplido / parcial /
incumplido**, con la evidencia al lado.

| # | Criterio | PixiJS 2.5D | Three.js ortográfico | Quién gana |
|---|---|---|---|---|
| 1 | **Parecido con la referencia** | **Parcial.** Franja de esbeltez 4,85. La referencia es un bloque compacto | **Cumplido.** Esbeltez 1,05, sección abierta, fachada de vidrio, núcleo visible | **Three.js**, y es la razón por la que se abrió el spike |
| 2 | **Compacidad** | **Incumplido.** 88,2 × 18,2 × 48,4 | **Cumplido.** 40 × 38 × 21 | **Three.js**, medido |
| 3 | **Visibilidad de departamentos** | **Cumplido** en la vista general: con una fila por piso, todas las salas se ven a la vez | **Cumplido por aislamiento**, parcial en la vista general: el corte muestra el frente de los tres pisos, no las tres filas | **Empate, con matiz**: PixiJS muestra más de una vez; Three.js muestra todo cuando se pide |
| 4 | **Profundidad arquitectónica** | **Parcial.** Profundidad simulada con tres caras y un orden de pintado | **Cumplido.** Volúmenes reales, sombras proyectadas, buffer de profundidad | **Three.js** |
| 5 | **Iluminación y materiales** | **Parcial.** Luz pintada: tonos fijos por cara, charcos aditivos | **Cumplido.** Luz calculada: focos cálidos por planta, sombras, vidrio con transmisión | **Three.js**, pero ver «lo que esto cuesta» |
| 6 | **Interacción** | **Cumplido.** Selección por puesto, navegación edificio→piso→sala, ficha de agente, flujo en vivo | **Parcial.** Selección por sala con trazador de rayos, aislamiento de piso, ficha mínima | **PixiJS**, por madurez y no por capacidad |
| 7 | **Rendimiento** | 90–99 fps sostenidos, mín 87 · 2.426 objetos | 131–144 fps, mín 84 · 413 objetos · 554 llamadas · 10.240 triángulos | **No concluyente** — ver abajo |
| 8 | **Escalabilidad y mantenimiento** | 6 archivos acoplados al motor, ~4.000 líneas, 552 pruebas | 2 archivos, ~700 líneas, 16 pruebas. Dependencia nueva de 1,2 MB | **No concluyente** — el de PixiJS está terminado y el otro es un spike |

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

## Recomendación

**Three.js ortográfico para el edificio, y la decisión no está tomada todavía**
porque falta lo que el spike no puede dar.

Lo que sí está medido y no depende de opinión:

- La compacidad que se pidió **es alcanzable** y la cifra es 4,85 → 1,05.
- La causa de la franja **no era el motor** sino dibujar siempre todos los
  pisos; con eso resuelto, la planta compacta es posible en los dos.
- Lo que Three.js aporta es que **cortar, atravesar y apagar capas sea correcto
  por construcción** en vez de una excepción al orden de pintado.
- El rendimiento **no decide**: los dos sobran.

Lo que falta antes de decidir:

1. **Las referencias de los ejes 3 y 6** —personajes/animación y cámara—, que
   el dueño del producto dijo que desarrollaría aparte. El eje 3 es el que
   verdaderamente decide: un sistema de personajes de calidad es la mitad del
   trabajo, y los dos motores lo resuelven de forma muy distinta.
2. **Verificar S1 y S2 en el navegador** cuando vuelva el laboratorio.
3. **Un presupuesto honesto de migración**, porque lo que habría que reconstruir
   no es el edificio: es la selección por puesto, la ficha, el flujo en vivo, la
   bitácora y 552 pruebas.

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
- El prototipo de PixiJS queda **íntegro y recuperable**: ni un archivo suyo se
  modificó para este spike, y la etiqueta `sede-pixi-2026-10-31` sigue apuntando
  al estado anterior.
