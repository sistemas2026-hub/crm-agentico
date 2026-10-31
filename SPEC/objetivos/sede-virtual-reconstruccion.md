# Objetivo · La sede virtual se reconstruye para que sea un edificio, no una sala

> Abierto el 31/10/2026. Estado: **abierto** — en evaluación de motor gráfico.
> Fase siguiente de [empresa-virtual-isp.md](empresa-virtual-isp.md), que sigue
> siendo el contrato del **qué** y del **por qué**. Acá vive una sola pregunta:
> **con qué tecnología se dibuja**, y con qué evidencia se decide.
>
> Rama aislada: `spec/sede-virtual-3d`. Versión recuperable de lo anterior:
> tag `sede-pixi-2026-10-31` → `37972d59`.

---

## La regla que gobierna esta fase

Decisión del usuario, 31/10/2026, textual:

> **EL OBJETIVO FINAL TIENE PRIORIDAD SOBRE LA ARQUITECTURA VISUAL ACTUAL.**
> No estás obligado a conservar PixiJS, el compositor de pisos, las geometrías,
> los personajes, los mapas o la distribución existente si mantenerlos impide
> alcanzar la experiencia que buscamos.

Y su límite, igual de explícito:

> Esta libertad de reconstrucción aplica a los componentes necesarios para
> alcanzar el objetivo, principalmente la experiencia visual. Conserva las
> garantías de seguridad, aislamiento multiempresa, eventos verificables,
> permisos, auditoría y protección de datos.

Lo que esto cierra: **«ya está construido» deja de ser un argumento.** Lo que
no cierra: nada de lo que ya funciona del SaaS se sacrifica por la vista.

---

## Qué significa terminado

Un ISP entra al Centro de Mando y ve **su sede**: un edificio de tres niveles
con departamentos conectados por pasillos y ascensor, personal que se mueve, y
agentes cuya actividad en pantalla se puede rastrear hasta el evento del motor
que la causó — con la cámara de un juego de simulación y no de un plano.

Lo que explícitamente **no** se acepta como resultado, por decisión del usuario:
una cadena de oficinas flotantes, aunque alcance buenos fotogramas.

---

## Lo que se midió antes de recomendar nada

Medido el 31/10/2026 sobre `spec/empresa-virtual-isp` (`37972d59`).

```
escena acoplada al motor grafico   4 archivos · 4.311 lineas TS
   de esos, importan pixi.js       4   (montar, oficina, personaje, texturas)
capa de datos y configuracion     28 archivos ·  3.258 lineas JS · 0 importan pixi
pruebas de navegador              18, de las cuales 2 miran el lienzo
rendimiento hoy (ventana al frente)
   edificio   2.353 obj   101 fps
   un piso      601 obj   144 fps
   una sala     293 obj   144 fps
```

**El hallazgo que decide el costo:** el motor gráfico toca **4 archivos de 32**.
Toda la espina —catálogo de 84 herramientas, `Ocupacion.persona`,
`/agentes/acciones`, los `load` del servidor, `FichaDePuesto`, `departamentos.js`,
`plantillas.js`, `sugerencias.js`— es **agnóstica del motor**. Y de las 18
pruebas de navegador, **16 sobreviven intactas** a un cambio de motor: afirman
sobre lo que la pantalla *dice*, no sobre píxeles.

Esa decisión se tomó ayer por otro motivo —una prueba de píxeles se rompe cuando
alguien mueve una planta dos celdas— y es justo lo que hoy hace que
reconstruir sea pagable. Queda congelada abajo.

---

## Qué se conserva y qué se reconstruye

Pedido por el usuario el 31/10/2026: *«Mantén la arquitectura operativa
existente hasta determinar qué componentes gráficos debemos conservar o
reconstruir.»* Esto es esa determinación. **No depende de la referencia
visual**: depende de dónde están los contratos, y eso ya se puede leer.

Medido archivo por archivo, leyendo lo que cada uno declara hacer.

| Módulo | Líneas | Qué es | Veredicto |
|---|---|---|---|
| `adaptador.ts` | 321 | la frontera entre el contrato de datos y la animación; sostiene *«no saber gana siempre»* | **se conserva entero.** No importa el motor gráfico, y es donde vive la regla de frescura |
| `pose.ts` | 258 | la animación como números; las 20 transiciones salen de interpolar, no de escribirlas | **se conserva el contrato.** Un esqueleto en volumen también se anima con números por pieza |
| `paleta.ts` | 243 | los colores de la paleta Fibra del producto, con el contraste medido | **se conserva.** Lo que de verdad se conserva no son los enteros: es el contraste ya medido |
| `camara.ts` | 278 | tres números y `gesto()`, que separa un clic de un arrastre | **se conserva la decisión.** `gesto()` vale en cualquier motor: es el defecto de `setPointerCapture` ya pagado una vez. La transformación cambia sólo si cambia la proyección |
| `montar.ts` | 658 | la única puerta: cuatro verbos y ni una palabra de PixiJS | **se conserva la interfaz, se reescribe el cuerpo.** Tiene **un solo consumidor**: `v2/+page.svelte` |
| `isometria.ts` | 142 | la proyección 2:1, aritmética pura | **depende de la referencia.** Con volumen real la reemplaza la cámara; si la sede se queda en 2.5D se conserva entera |
| `oficina.ts` | 1.880 | suelo, muros, mobiliario y mural: 32 funciones de geometría | **se reconstruye** |
| `personaje.ts` | 349 | una figura sentada de primitivas, articulada por piezas con nombre | **se reconstruye** si hay volumen real; el nombrado de piezas y su contrato con `pose.ts` sobreviven |
| `texturas.ts` | 182 | halos y sombras generadas con `canvas` una vez al montar | **se reconstruye o se descarta**, según el motor |

```
se reconstruye            2.411 lineas   (oficina + personaje + texturas)
sobrevive                 1.900 lineas   (contratos, decisiones y la puerta)
capa de datos             3.258 lineas   intacta, 0 importan el motor grafico
───────────────────────────────────────────────────────────────────────────
el rediseno toca a lo sumo el 32% de centro-mando
```

**Y el reparto no lo invento yo: lo escribió `oficina.ts` el día que nació.** Su
encabezado dice, textual: *«Esto no es arte definitivo. (…) El día que haya
ilustración, lo que se reemplaza es el cuerpo de estas funciones: la rejilla, el
orden de pintado, la cámara y la frontera con los datos no se tocan. Ese reparto
es el verdadero entregable.»* La arquitectura anticipó su propia reconstrucción,
y por eso hoy se puede pagar.

**Lo que esto cierra como pregunta:** ninguna garantía del SaaS está del lado
que se reconstruye. Aislamiento por empresa, permisos, auditoría, eventos
verificables y protección de datos viven en `nucleo/` y en los `load` del
servidor — y el motor gráfico tiene un consumidor, que es una pantalla.

---

## La evaluación de motor

### El conflicto estructural que obliga a decidir

Está medido, no opinado. En la escena actual un puesto queda tapado por el piso
de arriba cuando:

```
(ALTURA_DE_PISO − z) · 0,8125  ≤  fondo − gy          con ALTURA_DE_PISO = 15
```

**`gx` no aparece en la desigualdad.** Por eso una sala ampliada sólo puede
crecer a lo **ancho**, nunca a lo hondo: a lo hondo desaparece debajo del piso
superior. Eso no es un defecto pendiente de pulir — es lo que *es* una escena
2.5D ordenada por pintor con losas opacas.

Y de ahí sale la conclusión incómoda: **«no oficinas flotantes» y «2.5D ordenado
por pintor» están en conflicto directo.** Con losas opacas no se ve dentro de un
edificio de tres pisos; sin losas, lo que queda son oficinas flotando. La
tercera salida —ver dentro de un volumen recortando lo que estorba— necesita
profundidad real y una cámara que pueda cortar. Eso es 3D.

### Las cuatro exigencias del objetivo, contra cada motor

| Exigencia | PixiJS 2.5D hoy | Three.js ortográfico |
|---|---|---|
| **Edificio de 3 pisos que se vea por dentro** | imposible sin volver a oficinas flotantes (desigualdad de arriba) | buffer de profundidad + ocultar/recortar niveles: es cómo lo resuelve cualquier juego del género |
| **Personajes con movimiento natural** | hojas de sprites (8 orientaciones × N animaciones × N aspectos) o esqueletos de pago. **No tenemos pipeline de arte ni artista** | un `.glb` con rig + clips (reposo, caminar, sentarse, teclear, hablar); el ciclo de caminata viene con el modelo |
| **Iluminación y profundidad de calidad comercial** | cada superficie y cada sombra se calcula a mano — es buena parte de las 1.880 líneas de `oficina.ts`, y cada mueble nuevo exige dibujar su sombra | una platina de luces; las sombras salen solas y siguen siendo coherentes cuando el contenido crece |
| **Cámara como juego de simulación** | panear y acercar, sí; **orbitar, no**: el arte sólo existe desde un ángulo. Mirar la otra cara del edificio es redibujar todo | orbitar es un parámetro de cámara |

### El caso a favor de quedarse, con su mejor cara

No es despreciable y hay que decirlo: funciona, corre a 101 fps con 2 353
objetos, **no depende de un solo archivo de arte**, y un departamento nuevo no
necesita que nadie modele nada. Eso último es una propiedad real del enfoque
procedural y es lo que hace que la configuración por empresa funcione hoy.

### El riesgo real de 3D, que no se puede tapar

**Es fácil construir 3D que se vea PEOR que un buen 2.5D.** Low-poly sin
materiales y con luces por defecto se ve como una maqueta de arquitecto de 2005.
La calidad comercial en 3D no es gratis: exige dirección de arte (materiales,
luz horneada, post-proceso) y es trabajo que no desaparece, se mueve.

Y lo procedural tampoco desaparece: un edificio configurable por empresa sigue
teniendo que **generarse desde la configuración**, no modelarse a mano. El
problema de composición se traslada, no se resuelve.

### Recomendación

**Three.js con cámara ortográfica**, que conserva la legibilidad isométrica que
ya funciona y gana profundidad real, luz y personajes articulados.

**Pero no se adopta por este documento.** Se adopta si un *spike* lo demuestra
contra criterios escritos ANTES de construirlo — o se descarta si no los
alcanza, y entonces el camino es 2.5D con arte real en vez de geometría
calculada. Un spike que se califica a sí mismo no mide nada.

---

## El spike, y sus criterios de muerte

Una rebanada vertical en `spec/sede-virtual-3d`, en una ruta nueva
(`/centro-mando/v3`), **sin tocar v2**: un edificio de 3 niveles generado desde
la configuración real de Rapilink, un departamento amoblado, un personaje
articulado caminando, y la cámara.

Se declara ANTES de construirlo. Si falla uno, el spike no pasa:

| # | Criterio | Se mide con |
|---|---|---|
| S1 | ≥ 50 fps con el edificio completo, 37 puestos y 8 personajes, **ventana al frente** | la cabecera de telemetría, y el foco controlado (ver riesgos) |
| S2 | Los tres niveles legibles a la vez: ningún piso oculta a los ocupantes de otro | captura del edificio completo |
| S3 | Una persona se distingue de un agente IA a escala de conjunto, sin leer el rótulo | captura del edificio completo |
| S4 | La silueta de un personaje caminando se lee como una caminata, no como un deslizamiento | captura en secuencia |
| S5 | El paquete no crece más de **+400 KB gz** sobre hoy | `vite build` y el tamaño real del bundle |
| S6 | Las 18 pruebas de navegador pasan con **a lo sumo 2 afirmaciones** cambiadas (las que miran el lienzo) | la corrida pegada |
| S7 | Ningún recurso en tiempo de ejecución sale a un tercero: modelos y texturas servidos por nosotros | revisión de red del navegador |

**S7 no es estética.** Un CDN de modelos es un tercero que recibe la IP de quien
mira, y la autorización de tratamiento nombra proveedores (CLAUDE.md §5): un
tercero nuevo se resuelve antes de activarse, no después.

---

## Los seis ejes de la referencia

Los fijó el usuario el 31/10/2026, y ordenan tanto las imágenes como la lista
con la que se juzga cada captura. Detalle operativo y carpetas en
[documentos/sede/referencia/LEEME.md](../../documentos/sede/referencia/LEEME.md).

| # | Eje | Qué decide |
|---|---|---|
| 1 | Arquitectura general y los tres pisos | la silueta del edificio y cuánto se ve de cada nivel a la vez |
| 2 | Conexiones: oficinas, pasillos, puertas, núcleo vertical | si la sede es un edificio o un apilado de salas |
| 3 | Personajes, mobiliario y animaciones | el nivel de detalle, y si una caminata se lee como caminata |
| 4 | Iluminación, materiales, profundidad y paleta corporativa | de dónde entra la luz y qué parte de la paleta Fibra sobrevive |
| 5 | Legibilidad de departamentos y estados | cómo se nombra una sala sin tapar la escena |
| 6 | Cámara y navegación | el ángulo, el acercamiento, si gira, y cómo se baja de edificio a sala |

**Los criterios visuales definitivos NO están congelados**, por pedido expreso:
se escriben cuando lleguen las imágenes, uno por eje, como afirmaciones
comprobables mirando una captura. Lo de abajo son los criterios del objetivo,
que es otra cosa: dicen con qué evidencia se cierra, no cómo se ve.

---

## Criterios de aceptación del objetivo

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | El spike cumple S1–S7, o queda escrito cuál falló y qué se decidió | tabla de arriba, con capturas y salidas pegadas |
| 2 | Las imágenes de referencia están puestas y de cada uno de los seis ejes salió su lista legible | los archivos en `documentos/sede/referencia/` + la lista versionada al lado |
| 3 | `cd pruebas-navegador && ./correr.sh` → 18/18 en verde, dos corridas seguidas | salida pegada |
| 4 | `py -3.13 tests/test_nucleo_sin_tenants.py` pasa | salida pegada |
| 5 | La suite de `vitest` de `centro-mando` en verde, y los rojos preexistentes sin crecer (línea base: 62) | salida pegada |
| 6 | Captura comparada v2 ↔ v3 contra la imagen de referencia, ítem por ítem | las dos capturas y la lista |
| 7 | `auditor-independiente` corrió sobre el bloque | sus hallazgos resueltos o anotados con motivo |
| 8 | `SPEC/DEXTER_ESTADO_ACTUAL.md` refleja el cierre | lo escribe la sesión dueña |

**El criterio 6 existe porque el 2 no alcanza solo.** Una imagen de referencia
sin lista legible se juzga con «se parece», y eso no es un criterio. La lista
—niveles legibles, acceso visible entre departamentos, rótulo leíble al nivel de
conjunto, persona distinguible de agente, sombras coherentes— sí.

---

## Restricciones

Las tres permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** sin decirlo: cada guardado parte la medición ON/OFF.
- **NO correr los 56 casos dorados** — `--humo` (~3 min).

Y las propias de esta fase:

- **v2 sigue funcionando hasta que v3 pase el criterio 6.** No se borra la ruta
  anterior para «limpiar»: es la versión recuperable en caliente, además del tag.
- **No se toca `nucleo/`** salvo que haga falta un dato nuevo de configuración —
  y entonces es configuración, no un `if` por empresa (§3.1).
- **La capa de datos no se reescribe de paso.** `departamentos.js`,
  `plantillas.js`, `sugerencias.js`, `edificio.js` y el contrato de
  `/agentes/acciones` se conservan: son lo que hace pagable esta reconstrucción.
- **La arquitectura operativa actual se mantiene intacta** hasta que la
  referencia esté fijada. Pedido textual del usuario, y además es lo
  correcto: el inventario de arriba se escribió leyendo código que sigue
  corriendo, no reconstruyéndolo para ver qué se rompía.
- No se tocan contenedores ajenos ni volúmenes del laboratorio.

---

## Lo que NO se hace, con su motivo

- **No se migra el Centro de Mando v1** (`/centro-mando`, la pantalla radial).
  Es otra pantalla con otro propósito y está en producción.
- **No se construye un editor de planta visual** (arrastrar muebles). Es un
  producto en sí mismo; la configuración por formulario ya resuelve el alcance
  acordado.
- **No se persigue fotorrealismo.** El objetivo dice «videojuego empresarial
  moderno», y eso es dirección de arte estilizada: más barata, más legible a
  escala de conjunto y más honesta con lo que podemos mantener.
- **No se inventa actividad.** Un personaje se mueve porque hay un evento del
  motor detrás, o no se mueve. Animar por ambiente lo que no pasó convierte la
  pantalla en una mentira bonita — es la misma regla que prohíbe mostrar
  acciones que el backend no permite.

---

## Decisiones congeladas en esta fase

1. **La información vive en el DOM; el lienzo la representa.** Encabezados,
   rótulos, pie y ficha son texto real, y el lienzo es una vista de lo mismo.
   Tres razones, y cualquiera alcanza: se puede probar sin mirar píxeles, se
   puede leer con un lector de pantalla, y sobrevive a un cambio de motor —
   medido: 16 de 18 pruebas de navegador no se enteran de con qué se dibuja.

2. **El respaldo de lo anterior es un tag, no una carpeta `v2_old/`.** Una copia
   de archivos en el árbol se desactualiza y nadie sabe si todavía corre.

3. **La guarda de push se pone POR RAMA, y una rama nueva no la hereda.**
   `branch.<rama>.pushRemote` es por rama; el `pre-push` de `.githooks` es el que
   cubre todo. Al abrir `spec/sede-virtual-3d` se puso la primera y se
   **volvió a medir** la segunda desde la rama nueva: destino rama de deploy →
   bloquea; destino propia → pasa.

---

## Bloqueos

| # | Qué | Por qué bloquea |
|---|---|---|
| B1 | **Las imágenes de referencia todavía no llegaron.** Resuelto quién las pone: el usuario, decidido el 31/10/2026. Van a `documentos/sede/referencia/`, clasificadas por los seis ejes | Sin ellas, «calidad comercial» se interpreta cada sesión distinto y no hay contra qué comparar una captura. **Bloquea construir**, por pedido expreso. NO bloquea el inventario (hecho) ni S1–S7, que son técnicos |

Hay material previo sin revisar que puede servir de referencia, sin seguimiento
de git en el árbol principal: `documentos/command-center/oficina-*.png`,
`cc-v3.png`, `estaciones/`, `avatares/`. No se da por buena ninguna sin que el
usuario lo diga.

---

## Riesgos pendientes

| # | Qué | Estado |
|---|---|---|
| R1 | **Medir fotogramas con la ventana tapada da 1 fps y la API de visibilidad no lo delata** (`visibilityState` = `visible`, `hasFocus()` = `true`). Comprobado con una pantalla sin lienzo, que también dio 1 fps | Mitigado: toda medición de S1 exige ventana al frente, y está escrito en el LEEME de la suite |
| R2 | Licencias de modelos y animaciones de terceros | A resolver antes de que un `.glb` entre al repositorio |
| R3 | Vite en este laboratorio sirve módulos viejos tras editar y hay que reiniciarlo; recién reiniciado hay que calentarlo o la suite muere con un error que no señala a nada | Documentado en `pruebas-navegador/LEEME.md` |
| R4 | Un paquete 3D cargado en la ruta equivocada pesa en pantallas que no lo usan | S5 lo mide; la importación va diferida en la ruta de la sede |

---

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 31/10/2026 | Los seis ejes de la referencia quedan fijados y la carpeta preparada; **inventario de qué se conserva y qué se reconstruye, medido archivo por archivo**: 2.411 líneas se reconstruyen, 1.900 sobreviven, la capa de datos no se toca, y el motor gráfico tiene un solo consumidor. Ninguna garantía del SaaS está del lado que se reconstruye | Las imágenes. Sin ellas no se construye | — |
| 31/10/2026 | Rama aislada `spec/sede-virtual-3d` + tag recuperable `sede-pixi-2026-10-31`; guarda de push medida desde la rama nueva; acoplamiento medido (4 de 32 archivos; 16 de 18 pruebas agnósticas); evaluación de motor con recomendación y criterios de muerte del spike escritos antes de construirlo | B1: fijar la imagen de referencia. Después: el spike | esta ficha |
