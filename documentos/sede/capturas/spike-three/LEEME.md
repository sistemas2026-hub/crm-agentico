# El prototipo de Three.js, en capturas

La evidencia de [SPEC/objetivos/sede-virtual-comparacion-motores.md](../../../../SPEC/objetivos/sede-virtual-comparacion-motores.md).
Todas con la ventana **al frente**; sin eso el contador de fotogramas no mide
nada. Pantalla de 1600 × 900, lienzo de 1364 × 788.

| Archivo | Qué prueba |
|---|---|
| `three-0-primera-version-con-niebla.png` | **El primer intento, en negro.** Se guarda porque la causa es la lección: con cámara ortográfica la posición se pone a 300 unidades para que el volumen de vista cubra el edificio, así que una niebla pensada para distancias de escena se traga el edificio entero. Parecía un problema de luz y no lo era |
| `three-1-edificio-corte.png` | La vista de conjunto: planta compacta de 40 × 38, corte por planos en la esquina que mira a la cámara, interiores cálidos, cubierta y fachada de vidrio. **Defecto visible**: los rótulos de salas tapadas aparecen sobre la cubierta — corregido en código, sin verificar |
| `three-2-piso-aislado.png` | **La captura que justifica el spike.** P1 con sus cinco departamentos en DOS FILAS, todos visibles, sin oclusión posible. Es lo que la distribución lineal no podía dar |
| `three-3-rayos-x.png` | El modo traslúcido, **con el defecto conocido** de la cubierta opaca: el botón respondía y la vista no cambiaba. Corregido en código, sin verificar |

La serie equivalente de PixiJS está un nivel más arriba, en
[documentos/sede/capturas/](../).
