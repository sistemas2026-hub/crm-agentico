/**
 * DÓNDE QUEDA EL BOTÓN «PREGUNTAR» CUANDO SE LO MUEVE
 * ====================================================
 *
 * Pedido del usuario (25/11/2026): poder mover el botón del chat del
 * Supervisor — presionar, arrastrar, y que al soltar se quede ahí. En la
 * esquina de abajo a la derecha tapa lo último de las tablas.
 *
 * ACÁ VIVE LA GEOMETRÍA, Y NADA MÁS. No toca el DOM ni el almacenamiento: son
 * funciones puras, para que lo que decide —qué es arrastrar y qué es un clic,
 * hasta dónde puede ir, de qué borde cuelga— se pueda probar sin navegador.
 * Es el mismo reparto que `chat-sesion.js`.
 *
 * POR QUÉ EL BOTÓN CUELGA DEL BORDE MÁS CERCANO
 * ---------------------------------------------
 * El panel del chat se abre pegado al botón. Si el botón se lleva arriba, un
 * panel que sigue abriéndose hacia arriba queda fuera de la pantalla; si se
 * lleva a la izquierda, uno que crece hacia la izquierda también. Por eso el
 * panel se abre SIEMPRE hacia el lado donde hay lugar: el botón cuelga del
 * borde que tiene más cerca y el panel crece hacia el otro.
 *
 * Colgar del borde cercano además deja al botón quieto cuando cambia de
 * tamaño («Preguntar» ↔ «×», o el contador de mensajes nuevos): crece hacia
 * adentro de la pantalla, no se corre.
 */

/** Cuánto se separa el botón del borde de la ventana, como mínimo. */
export const MARGEN = 8;

/** Lo que hay entre el botón y el panel (el `gap` de `.snoc-chat`). */
export const SEPARACION = 12;

/**
 * Cuánto hay que mover el puntero para que sea un arrastre y no un clic.
 *
 * Un dedo o un mouse nunca se quedan perfectamente quietos al presionar: sin
 * umbral, cada clic con un temblor de dos píxeles movería el botón en vez de
 * abrir el chat.
 */
export const UMBRAL_PX = 6;

/** Dónde se guarda la posición en el navegador. */
export const CLAVE = 'dexter.supervisor.chat.posicion';

/**
 * ¿El puntero ya se movió lo suficiente como para estar arrastrando?
 *
 * @param {number} dx @param {number} dy
 */
export function esArrastre(dx, dy) {
  return Math.hypot(dx, dy) >= UMBRAL_PX;
}

/**
 * La posición más cercana a la pedida que deja el botón ENTERO a la vista.
 *
 * `x`, `y` son la esquina de arriba a la izquierda del botón, en píxeles de la
 * ventana. Si la ventana es más chica que el botón, gana el borde de arriba a
 * la izquierda: se ve el principio del botón, que es por donde se lo agarra.
 *
 * @param {{ x: number, y: number }} pos
 * @param {{ ancho: number, alto: number }} boton
 * @param {{ ancho: number, alto: number }} ventana
 * @returns {{ x: number, y: number }}
 */
export function acotar(pos, boton, ventana) {
  const maxX = Math.max(MARGEN, ventana.ancho - boton.ancho - MARGEN);
  const maxY = Math.max(MARGEN, ventana.alto - boton.alto - MARGEN);
  return {
    x: Math.min(Math.max(pos.x, MARGEN), maxX),
    y: Math.min(Math.max(pos.y, MARGEN), maxY)
  };
}

/**
 * De qué bordes cuelga el botón, hacia dónde se abre el panel y cuánto lugar
 * tiene.
 *
 * - `horizontal`: 'right' si el centro del botón está en la mitad derecha de
 *   la ventana (el panel crece hacia la izquierda), 'left' si no.
 * - `vertical`: 'bottom' si está en la mitad de abajo (el panel se abre hacia
 *   arriba), 'top' si no.
 * - `maxAncho`, `maxAlto`: el lugar que le queda al panel hacia ese lado, sin
 *   salirse de la ventana. Nunca negativos.
 *
 * @param {{ x: number, y: number }} pos
 * @param {{ ancho: number, alto: number }} boton
 * @param {{ ancho: number, alto: number }} ventana
 */
export function anclaje(pos, boton, ventana) {
  const derecha = pos.x + boton.ancho / 2 >= ventana.ancho / 2;
  const abajo = pos.y + boton.alto / 2 >= ventana.alto / 2;

  const bordeDerecho = pos.x + boton.ancho;
  const bordeInferior = pos.y + boton.alto;

  const maxAncho = derecha ? bordeDerecho - MARGEN : ventana.ancho - pos.x - MARGEN;
  const maxAlto = abajo
    ? pos.y - SEPARACION - MARGEN
    : ventana.alto - bordeInferior - SEPARACION - MARGEN;

  return {
    horizontal: /** @type {'left' | 'right'} */ (derecha ? 'right' : 'left'),
    vertical: /** @type {'top' | 'bottom'} */ (abajo ? 'bottom' : 'top'),
    distanciaHorizontal: Math.max(0, derecha ? ventana.ancho - bordeDerecho : pos.x),
    distanciaVertical: Math.max(0, abajo ? ventana.alto - bordeInferior : pos.y),
    maxAncho: Math.max(0, maxAncho),
    maxAlto: Math.max(0, maxAlto)
  };
}

/**
 * El `style` del contenedor `.snoc-chat` para esa posición.
 *
 * Se pisan los cuatro lados a propósito: la hoja de estilos lo fija con
 * `right` y `bottom`, y dejar uno de esos puesto junto al opuesto estiraría el
 * contenedor de lado a lado.
 *
 * @param {ReturnType<typeof anclaje>} a
 */
export function estiloDe(a) {
  const px = (/** @type {number} */ n) => `${Math.round(n)}px`;
  return [
    `left:${a.horizontal === 'left' ? px(a.distanciaHorizontal) : 'auto'}`,
    `right:${a.horizontal === 'right' ? px(a.distanciaHorizontal) : 'auto'}`,
    `top:${a.vertical === 'top' ? px(a.distanciaVertical) : 'auto'}`,
    `bottom:${a.vertical === 'bottom' ? px(a.distanciaVertical) : 'auto'}`,
    //  El panel va antes que el botón en el HTML. Con el botón abajo, en
    //  columna queda arriba suyo; con el botón arriba, se invierte.
    `flex-direction:${a.vertical === 'bottom' ? 'column' : 'column-reverse'}`,
    `align-items:${a.horizontal === 'right' ? 'flex-end' : 'flex-start'}`,
    `--snoc-chat-max-ancho:${px(a.maxAncho)}`,
    `--snoc-chat-max-alto:${px(a.maxAlto)}`
  ].join(';');
}

/**
 * Lo guardado en el navegador, o `null` si no sirve.
 *
 * Lo que hay en `localStorage` lo pudo escribir una versión vieja, otra
 * pestaña o una extensión: se valida como cualquier dato de afuera. Ante la
 * duda, `null` — el botón vuelve a su esquina, que es un lugar que siempre
 * funciona.
 *
 * @param {string | null | undefined} texto
 * @returns {{ x: number, y: number } | null}
 */
export function leerGuardada(texto) {
  if (!texto) return null;
  try {
    const d = JSON.parse(texto);
    if (!d || typeof d !== 'object') return null;
    const { x, y } = d;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { x, y };
  } catch {
    return null;
  }
}
