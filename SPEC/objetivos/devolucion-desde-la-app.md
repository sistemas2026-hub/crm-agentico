# Objetivo · Una devolución se cuenta una sola vez

> Abierto el 13/10/2026. Estado: **abierto**, sin implementar. **Vivo en
> producción.** Sale de la auditoría de custodia
> (`SPEC/auditorias/2026-10-13-custodia-de-materiales.md`, hallazgo D1), donde
> lo encontraron por separado la pasada adversarial y, desde el cierre de
> jornada, la de frontera.

## El problema, verificado leyendo el código

Una devolución tiene hoy **dos caminos que no se conocen**:

```
la app      tipo 'devolucion'      custodia del tecnico -> (ninguna ubicacion)
            services/materiales.py::_direccion_de       «que llego a bodega lo
                                                         dice quien la recibe»
la web      recibir_devolucion()   custodia del tecnico -> bodega
            services/inventario.py
```

- **Si solo devuelve por la app:** su custodia baja, la bodega no sube. El
  material **sale del sistema**.
- **Si además la bodega registra la recepción:** la custodia baja **dos
  veces** (queda negativa) y la bodega sube una. `kit_de` y la conciliación
  ven el doble, y `motivos_para_no_cerrar` **no le deja cerrar la jornada** al
  técnico.
- La guarda `test_inventario_una_sola_verdad::test_ningun_movimiento_queda_sin_direccion`
  ejecuta los dos caminos en la misma prueba y **no afirma ninguna suma**: por
  eso no lo vio.

## La decisión que hace falta antes de escribir código

La idea de diseño es correcta y no hay que perderla: el teléfono **no sabe** si
el material llegó a bodega, y suponerlo sería inventar una recepción que nadie
firmó. Lo que falta es que la recepción **consuma** la declaración en vez de
restar otra vez. Dos formas, a elegir:

1. **Una ubicación «en tránsito» por técnico.** La app mueve custodia → tránsito;
   la bodega recibe tránsito → bodega. Lo no recibido queda **visible** en
   tránsito, con nombre y fecha, en vez de desaparecer.
2. **La recepción ligada a la declaración.** `recibir_devolucion` busca las
   devoluciones declaradas y no recibidas de ese técnico y las cierra; solo lo
   que NO estaba declarado sale de la custodia.

La 1 es más simple de razonar y deja el faltante a la vista; la 2 no agrega
ubicaciones. **Las dos necesitan una corrección de los datos que ya existen**
en producción, y antes, **medir** cuántas devoluciones por app hay y cuántas
tienen una recepción duplicada.

## Qué significa terminado

- Una prueba contra Postgres real que afirme la **suma**: devolver 18 por la
  app y recibir 18 en la web deja la custodia en 0 y la bodega en +18.
- La misma prueba con solo la mitad del camino: lo no recibido se ve en algún
  lado, no desaparece.
- Los datos existentes, medidos y corregidos con una migración de datos
  probada en una base aparte (memoria: una suite normal no puede ver un
  `RunPython`).
