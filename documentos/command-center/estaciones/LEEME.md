# Imágenes de estación

Aquí van los renders de los puestos de trabajo. Uno por agente, con el
nombre de su id:

    router.png        Recepción y triaje
    soporte.png       Soporte técnico FTTH
    facturacion.png   Facturación y cartera
    ventas.png        Ventas y contratación
    campo.png         Despacho de campo
    supervisor.png    Supervisión
    generica.png      respaldo para un rol nuevo que no tenga la suya

## Cómo deben venir

- **Sin personaje y sin texto.** El avatar y los datos se ponen encima por
  código; si vienen dibujados en la imagen quedan congelados para siempre.
- **Fondo transparente.** Si la herramienta no lo permite, fondo magenta
  plano #FF00FF y avísame para recortarlo.
- **Mismo ángulo en las seis**: isométrica tres cuartos desde arriba, unos
  35 grados, el pod centrado y completo dentro del cuadro.
- **Azul neutro.** El color de estado (verde, cian, ámbar, violeta) se aplica
  encima por código; si el render ya viene verde, el tinte se ensucia.
- Cuadradas, 1536x1536 o más. Conviene optimizarlas a WebP antes de publicar.

## Cómo se activan

No hay que tocar código: en cuanto el archivo existe con el nombre correcto,
esa estación pasa a usar la imagen y se apaga su dibujo en SVG. Si el archivo
no está, se sigue dibujando la estación como hasta ahora.
