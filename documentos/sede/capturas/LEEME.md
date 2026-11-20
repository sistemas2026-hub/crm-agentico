# Las capturas de la validación del 31/10/2026

La evidencia de la matriz de los ocho criterios, que vive en
[SPEC/objetivos/sede-virtual-reconstruccion.md](../../../SPEC/objetivos/sede-virtual-reconstruccion.md).

Se guardan en el repositorio y no sólo en la carpeta de trabajo porque **una
matriz sin su captura no se puede volver a juzgar**: la siguiente sesión leería
«cumplido» y tendría que creerlo.

| Archivo | Qué prueba |
|---|---|
| `00-antes-p7-1-edificio.png` | **La línea base.** El mismo edificio esa misma mañana: tres losas escalonadas, sin basamento, sin fachada, sin cubierta. Es contra esto que se compara todo lo demás |
| `v1-edificio-completo.png` | Criterios 1, 2 y 4: volumen cerrado, nueve salas legibles, encuadre sin recortes |
| `v2-piso-aislado.png` | Criterios 4 y 6 en un nivel. Antes el núcleo quedaba cortado por arriba: el suelo del zoom impedía el encuadre y «Encuadrar» no hacía nada |
| `v3-noc-ampliado.png` | Criterio 6 a escala de sala, y la diferenciación: un agente IA y dos personas del equipo, distinguibles sin leer el rótulo |
| `v4-ficha-agente.png` | La selección por enlace y la ficha: identificación, actividad, historial y qué puede hacer hoy ese agente |
| `v6-nucleo-de-cerca.png` | Criterio 5. Es el recorte que cerró el parcial: la torre de vidrio con su remate sobre la cubierta |
| `w1-edificio-final.png` | El estado al cerrar, con la luz cálida, el filo azul de cada forjado y los rótulos de piso ya sin solaparse |

Todas con la ventana **al frente** (`page.bringToFront()`). Sin eso, el contador
de fotogramas marca 10 fps mientras `visibilityState` dice `visible` — la misma
escena, medida mal.
