# Las tres opciones, capturadas el 01/11/2026

Todas con la **misma empresa** (el fixture `organizacion-por-defecto.json`: 11
salas en 3 pisos), el **mismo encuadre** (1600 × 900) y los **mismos letreros**
que arma `/centro-mando/v2`.

## Cómo se tomaron, y qué NO prueban

El laboratorio estuvo caído toda la sesión: el motor Linux de Docker Desktop se
murió —`com.docker.backend` ausente— y **no se reinició**, por restricción. Las
capturas salen de un **banco** que sirve los módulos de la sede directamente del
árbol de trabajo, con Node despojando los tipos de TypeScript y un mapa de
importación para `three` y `pixi.js`.

Eso significa que estas imágenes **miden el dibujo y no la pantalla**: no hay
backend, ni sesión, ni cabecera, ni ficha de puesto, ni flujo en vivo. Y el
contador de fotogramas de un navegador sin ventana está limitado a 60, así que
**ninguna de estas capturas dice nada sobre rendimiento**.

## Qué hay en cada una

| Archivo | Qué muestra |
|---|---|
| `A-pixi-lineal.png` | Lo que hay hoy. 95,2 × 18,2 × 48,4, esbeltez **5,23**. Once salas visibles, mobiliario y personajes completos |
| `B-pixi-compacto-con-cubierta.png` | La planta compacta en PixiJS, 39 × 39, esbeltez **1,00** — y **la cubierta borra el piso de arriba entero**. «NOC y Redes» queda rotulado sobre un techo vacío |
| `B-pixi-compacto-sin-cubierta.png` | Lo mismo sin remate: las once salas a la vista, dos filas por piso, y el edificio leído como **tres bandejas flotando** |
| `B-pixi-compacto-piso1.png` | La mejor imagen de B: piso aislado, cinco salas en dos filas, mobiliario y personajes con su placa |
| `C-three-corte.png` | Three.js, misma planta, 40 × 38 × **21**, con cubierta y con la esquina recortada |
| `C-three-rayosx.png` | La cubierta apagada: se ve el piso 3 desde arriba, con sus nombres |
| `C-three-piso1.png` | El piso 1 aislado, cinco salas en dos filas, las cinco con nombre |
| `C-DEFECTO-un-solo-rotulo.png` | **Guardada a propósito.** El arreglo de los rótulos antes de verificarlo: un nombre de once. El mecanismo estaba puesto y el efecto no |

**La comparación honesta es `B-pixi-compacto-piso1.png` contra
`C-three-piso1.png`**: misma planta, misma empresa, mismo encuadre. B tiene
mobiliario y gente; C tiene volumen, luz y remate.

## Lo que la verificación encontró

Dos defectos que ninguna prueba sin pantalla iba a ver, los dos de la misma
familia —el trazador de rayos sólo conoce la geometría—:

1. **El ancla del rótulo estaba en el centro de la sala, que está bajo la
   cubierta.** Se veía un nombre de once. Ahora se prueban seis anclajes, de la
   esquina que mira a la cámara hacia adentro: **8 de 11**.
2. **El rayo no sabe que un objeto está apagado.** En «Rayos X» la cubierta se
   apaga y aun así bloqueaba **27 de 40 rayos**, dejando sin nombre justo al
   piso que ese modo existe para mostrar.

Detalle y decisión en
[SPEC/objetivos/sede-virtual-comparacion-motores.md](../../../../SPEC/objetivos/sede-virtual-comparacion-motores.md).
**La decisión de motor sigue sin tomar.**
