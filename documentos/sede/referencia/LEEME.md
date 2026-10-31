# La referencia visual de la sede

Acá van las imágenes que fijan **cómo tiene que verse** la sede virtual. No son
inspiración suelta: de ellas sale la lista con la que se juzga cada captura del
objetivo [sede-virtual-reconstruccion.md](../../../SPEC/objetivos/sede-virtual-reconstruccion.md).

Decidido el 31/10/2026: **las imágenes las pone el usuario**, y **los criterios
visuales no se congelan hasta que lleguen.** Lo segundo es tan importante como
lo primero: un criterio escrito antes de la referencia es una interpretación
mía disfrazada de acuerdo.

---

## Los seis ejes

Son los que el usuario fijó. Cada imagen sirve para uno o varios; conviene
decir cuál, porque una referencia que vale por su iluminación y se juzga por su
mobiliario manda a construir lo que nadie pidió.

| # | Eje | Qué tiene que quedar claro al mirarla |
|---|---|---|
| 1 | **Arquitectura y los tres pisos** | la silueta del edificio, cómo se apilan los niveles, qué se ve de cada uno a la vez |
| 2 | **Conexiones: pasillos, puertas, núcleo vertical** | por dónde se pasa de un departamento a otro, dónde está el ascensor o la escalera, qué es espacio común |
| 3 | **Personajes, mobiliario y animación** | el nivel de detalle y el estilo de una figura, qué tan amoblada está una sala, qué movimientos existen |
| 4 | **Luz, materiales, profundidad y paleta** | de dónde entra la luz, qué brilla y qué no, cuánta sombra, qué colores son corporativos |
| 5 | **Legibilidad de departamentos y estados** | cómo se nombra una sala sin tapar la escena, cómo se ve que algo va bien o va mal |
| 6 | **Cámara y navegación** | el ángulo, cuánto se acerca, si gira, cómo se pasa de edificio a piso a sala |

### Cómo dejarlas

Nombre libre. Si querés que el eje quede atado al archivo, alcanza con empezar
el nombre por el número: `3-personajes-detalle.png`, `4-luz-nocturna.jpg`.
Si una imagen vale por una sola cosa y el resto conviene ignorarlo, decilo en
`notas.md` acá al lado — una línea por archivo.

Carpetas sugeridas, por si son muchas:

```
1-arquitectura/   2-conexiones/   3-personajes/
4-luz/            5-legibilidad/  6-camara/
```

---

## Qué se deriva de ellas, y por qué no alcanza la imagen sola

Una imagen de referencia sin lista legible se juzga con *«se parece»*, y eso no
es un criterio: dos personas miran la misma captura y una dice que sí.

Así que de cada eje se escribe acá mismo una **lista de afirmaciones
comprobables mirando una captura**:

```
eje 1   [ ] los tres niveles se leen a la vez, ninguno oculta a los ocupantes de otro
        [ ] el edificio tiene silueta: se distingue de un apilado de losas
eje 2   [ ] se ve por donde se pasa de un departamento al pasillo
        [ ] el nucleo vertical existe y se reconoce como tal
eje 3   [ ] una figura caminando se lee como una caminata, no como un deslizamiento
eje 4   [ ] las sombras caen todas del mismo lado
eje 5   [ ] el rotulo de un departamento se lee a escala de edificio completo
        [ ] una persona se distingue de un agente IA sin leer el rotulo
eje 6   [ ] ...
```

Esa lista decide, ítem por ítem, contra la captura de cada versión. La imagen es
de dónde sale; la lista es con qué se mide. **Las dos quedan versionadas**, para
que la siguiente sesión no las reinterprete.

---

## Lo que NO espera estas imágenes

Dos cosas, y están hechas:

- **El inventario de qué se conserva y qué se reconstruye.** Está medido y vive
  en la ficha del objetivo. No depende del estilo: depende de dónde están los
  contratos, y eso ya se puede leer.
- **Los siete criterios técnicos del spike** (fotogramas con la ventana al
  frente, niveles legibles a la vez, peso del paquete, las 18 pruebas de
  navegador, ningún recurso saliendo a un tercero). Se miden igual, y si fallan
  el estilo no los salva.

Lo que **sí** espera: construir. La arquitectura operativa actual se mantiene
intacta hasta que la referencia esté fijada.
