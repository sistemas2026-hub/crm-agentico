# Material apartado para una orden

**Estado:** construido el 02/10/2026, **sin desplegar**. Queda una decisión de
producto abierta, abajo.

## De dónde sale

De una pregunta sobre la pantalla: *«¿qué función tiene "Material de esta orden"
en la ficha?»*. Al medirla apareció que la tarjeta decía servir para saber **qué
hay reservado antes de entrar**, y eso era falso: el backend acepta
`reservar(..., orden=...)` desde siempre, el endpoint también, y
`materiales_de_orden` ya arma el bloque `comprometido` que la app dibuja — pero
**el formulario del CRM nunca mandaba el campo**. El bloque llegaba siempre
vacío.

O sea: la función estaba construida de punta a punta menos el último centímetro.

## Lo que hacía falta, y no era el formulario

Antes de conectar el campo se midieron dos huecos que hacían que la función
fuera **peor que no tenerla**, porque el inventario empieza a mentir despacio y
el síntoma no apunta a la causa.

### 1 · Un despacho de kit se llevaba por delante lo apartado para un trabajo

`consumir_reservas` elegía por ubicación y material, la más antigua primero, sin
mirar la orden. Con reservas por orden eso significa: la bodega aparta 100 m para
la OT-1843 y 50 para la OT-1844; sale un **despacho de kit** —que por decisión
congelada no nombra ninguna orden, porque el kit es a la custodia del técnico y
no a un trabajo— y se cierra la reserva de la 1843. El bloque `comprometido` de
la ficha diría lo contrario de la realidad, y el ajuste quedaría escrito en el
libro como un hecho.

Ahora el ámbito es explícito:

```
sin `orden`  → solo las reservas SIN orden
con `orden`  → primero las de ESA orden; si no alcanzan, las genéricas
```

Es el mismo criterio que ya regía para la serie —cumplir lo específico antes que
lo genérico— y por la misma razón.

### 2 · Nada soltaba una reserva cuando la orden moría

`vencer_reservas` solo toca las que tienen plazo, **y es a propósito**: «una
reserva sin plazo es una decisión de quien la hizo». Nadie más volvía a mirarlas.
Una reserva atada a una orden cancelada bloqueaba material **para siempre**, y el
síntoma —falta material que está en la bodega— no apunta nunca a la causa.

Ahora una orden que pasa a `CANCELADA` o `CERRADA` suelta sus reservas abiertas,
con desenlace `LIBERADA` y el motivo adentro. Se libera, **no se borra**: la fila
explica después por qué se soltó. Y queda en la bitácora del trabajo
(`reservas_liberadas: N`), porque es un efecto sobre el inventario y quien lea la
orden dentro de un año tiene que poder verlo.

## Lo que se agregó, ya en el último centímetro

- **El endpoint acepta el número de OT**, no solo el UUID. Quien aparta material
  es la bodega, y lo que la bodega tiene en la mano es el número impreso en la
  orden — pedirle un UUID de 36 caracteres es pedirle que copie algo que no
  tiene. El UUID sigue sirviendo para una integración.
- **No se puede apartar para una orden ya terminada** (409). Sin esa puerta, ese
  material quedaría bloqueado hasta que alguien lo note: la transición que lo
  soltaría ya ocurrió.
- **El formulario del CRM** tiene «Para la OT», opcional. Vacío es el caso
  normal: la mayoría de las reservas son contra la bodega, no contra un trabajo.

**Una estimación propia que estaba mal:** dije que haría falta un endpoint nuevo
para que la oficina listara órdenes. `TrabajosListView` filtra por asignación
**solo cuando el rol es técnico**; un ADMIN ya ve todas las del tenant. Igual no
se usó un desplegable: una lista de treinta OT abiertas es inusable.

## Qué se midió

```
15 pruebas nuevas, contra PostgreSQL real (no SQLite)
```

Seis mutaciones las atacan y las seis se ponen en **rojo**: que un despacho de kit
consuma lo apartado para una orden, cumplir lo genérico antes que lo específico,
dejar el material bloqueado al cancelar, soltarlo en cualquier transición,
ignorar el número de orden, y apartar para una orden ya terminada.

**Lo que NO se verificó, y hay que decirlo:** el `pnpm check` del frontend. Este
worktree no tiene `node_modules` y la regla del repo prohíbe correrlo en Windows
con Docker arriba. Son dos líneas sin tipos de por medio —un `<input>` en el
formulario y un campo en la acción— pero no está tipado.

## La decisión de producto, cerrada el 02/10/2026

Se preguntó si Rapilink aparta material **por orden** o despacha **por kit del
día**. La respuesta del usuario, textual:

> «se crea plantilla cuando los trabajos son lo mismo para entregar los mismos
> materiales, pero habrá caso que se despachará por material normal»

**Las dos cosas conviven**, y cada una ya tiene su pieza:

| Caso | Pieza | Qué es |
|---|---|---|
| Trabajos repetidos, mismos materiales | `PlantillaDeKit` | Una lista por empresa que **rellena** las líneas del despacho. No mueve material ni queda en el libro: es un borrador que alguien revisa y confirma |
| Lo puntual, material suelto | Despacho línea por línea | Lo que no entra en ninguna plantilla |

Y por eso **el bloque `comprometido` se queda**. Apartar por orden es
exactamente la herramienta del segundo caso: cuando un trabajo necesita algo que
no viene en la plantilla, la bodega lo separa contra esa OT y el técnico lo ve en
su ficha antes de salir. En el primer caso no hace falta — la plantilla ya
describe lo que lleva el kit — y por eso el campo es **opcional**, que es como
quedó.

Nada de esto rompe la decisión congelada de que `EntregaDeKit` **no tiene FK a la
orden**: el kit sigue siendo a la custodia del técnico. Lo apartado para una OT es
otra cosa, vive en `ReservaDeMaterial`, y un despacho de kit ya no la toca.

## Lo que queda por hacer

- **Correr `pnpm check`** sobre el frontend cuando haya un entorno donde se pueda
  (ver arriba por qué no se hizo).
- **Nada bloquea el despliegue** del lado del backend: sin reservas por orden,
  todo se comporta exactamente como antes.
