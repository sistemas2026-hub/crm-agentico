/**
 * TEXTURAS GENERADAS, PORQUE NO HAY ARTE.
 *
 * Este repositorio no tiene un solo sprite ni un atlas, y producirlos no es
 * trabajo de una sesión: el arte es el coste real de una escena así, no la
 * librería. Lo que sí se puede hacer sin arte es generar las pocas texturas que
 * de verdad cambian el aspecto —un halo, una sombra blanda, un barrido— con un
 * `canvas` y un degradado, UNA vez, al montar.
 *
 * POR QUÉ NO SE DIBUJAN CON `Graphics` EN CADA FOTOGRAMA
 * Un halo es un degradado radial. Imitarlo con treinta círculos concéntricos
 * cuesta treinta figuras por puesto y por fotograma; como textura cuesta un
 * cuadrilátero y una multiplicación. Con un puesto da igual; con ocho
 * departamentos y cuarenta puestos es la diferencia entre 60 y 20 cuadros por
 * segundo, y esa cuenta hay que hacerla ahora y no cuando ya haya ocho
 * departamentos.
 *
 * NADA DE ESTO CORRE EN EL SERVIDOR
 * Usa `document`. Se llama al montar la escena, que solo pasa en el navegador;
 * si alguien lo llama durante el renderizado del servidor, falla ruidosamente
 * acá en vez de entregar una escena vacía sin decir por qué.
 */

import { Texture } from 'pixi.js';

function lienzo(ancho: number, alto: number) {
  if (typeof document === 'undefined') {
    throw new Error('las texturas de la escena se generan solo en el navegador');
  }
  const c = document.createElement('canvas');
  c.width = ancho;
  c.height = alto;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('el navegador no entregó un contexto 2d para las texturas');
  return { c, ctx };
}

/**
 * Halo radial blanco, de opaco en el centro a transparente en el borde.
 *
 * Se tiñe con el color del estado al usarlo (`sprite.tint`) y se suma a lo que
 * hay debajo (`blendMode: 'add'`), que es cómo se comporta la luz: ilumina lo
 * que toca en vez de taparlo. Una mancha de color opaca sobre el suelo se lee
 * como una alfombra, no como una luz, y es el error típico.
 *
 * La curva no es lineal: elevar al cubo concentra el brillo en el centro y deja
 * el borde largo y suave. Un degradado lineal deja un anillo visible donde
 * termina, y ese anillo delata el truco.
 */
export function texturaHalo(radio = 128): Texture {
  const d = radio * 2;
  const { c, ctx } = lienzo(d, d);
  const g = ctx.createRadialGradient(radio, radio, 0, radio, radio, radio);
  for (let i = 0; i <= 16; i++) {
    const p = i / 16;
    g.addColorStop(p, `rgba(255,255,255,${Math.pow(1 - p, 3).toFixed(4)})`);
  }
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, d, d);
  return Texture.from(c);
}

/**
 * Sombra de contacto: una elipse borrosa, achatada a la proporción isométrica.
 *
 * Es lo que apoya un objeto en el suelo. Sin ella todo flota, y el síntoma no
 * se describe como «falta la sombra» sino como «la escena se ve plana»: se
 * busca el problema en la iluminación general y no está ahí.
 */
export function texturaSombra(ancho = 160, alto = 80): Texture {
  const { c, ctx } = lienzo(ancho, alto);
  const g = ctx.createRadialGradient(ancho / 2, alto / 2, 0, ancho / 2, alto / 2, ancho / 2);
  for (let i = 0; i <= 12; i++) {
    const p = i / 12;
    g.addColorStop(p, `rgba(0,0,0,${(0.55 * Math.pow(1 - p, 2)).toFixed(4)})`);
  }
  ctx.save();
  ctx.translate(ancho / 2, alto / 2);
  ctx.scale(1, alto / ancho);
  ctx.translate(-ancho / 2, -alto / 2);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, ancho, ancho);
  ctx.restore();
  return Texture.from(c);
}

/**
 * Degradado vertical blanco→transparente, para el haz de luz de una luminaria
 * y para el reflejo de una pantalla sobre el escritorio.
 */
export function texturaHaz(ancho = 64, alto = 128): Texture {
  const { c, ctx } = lienzo(ancho, alto);
  const g = ctx.createLinearGradient(0, 0, 0, alto);
  g.addColorStop(0, 'rgba(255,255,255,0.75)');
  g.addColorStop(0.55, 'rgba(255,255,255,0.16)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, ancho, alto);
  return Texture.from(c);
}

/**
 * Trama de una pantalla grande: líneas horizontales finas con un poco de ruido.
 *
 * Lo que hace que un rectángulo brillante se lea como un monitor no es el
 * brillo: es que tenga estructura. Tres píxeles de trama bastan, y a la escala
 * de la escena no se distingue de un contenido real.
 */
export function texturaTrama(ancho = 128, alto = 128): Texture {
  const { c, ctx } = lienzo(ancho, alto);
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  ctx.fillRect(0, 0, ancho, alto);
  ctx.fillStyle = 'rgba(255,255,255,0.11)';
  for (let y = 0; y < alto; y += 3) ctx.fillRect(0, y, ancho, 1);
  // Un poco de grano: sin él la trama es demasiado regular y se ve como una
  // textura repetida, que es exactamente lo que es.
  for (let i = 0; i < 260; i++) {
    const x = Math.floor(Math.random() * ancho);
    const y = Math.floor(Math.random() * alto);
    ctx.fillStyle = `rgba(255,255,255,${(Math.random() * 0.1).toFixed(3)})`;
    ctx.fillRect(x, y, 1, 1);
  }
  return Texture.from(c);
}

/**
 * Viñeta: transparente en el centro, oscura en los bordes.
 *
 * Es el recurso más barato que separa «escena isométrica» de «videojuego». No
 * agrega un solo objeto a la sala: oscurece las esquinas de la VISTA, así que
 * la mirada cae donde está la acción en vez de repartirse por un rectángulo
 * uniforme. Va sobre el escenario y NO dentro del mundo — si se moviera con la
 * cámara dejaría de ser una viñeta y sería una mancha que persigue al suelo.
 *
 * La curva es cuadrática y arranca al 55% del radio: antes de eso no oscurece
 * nada. Un degradado que empieza en el centro apaga la escena entera y se nota
 * como «esto se ve sucio».
 */
export function texturaVineta(lado = 512): Texture {
  const { c, ctx } = lienzo(lado, lado);
  const r = lado / 2;
  const g = ctx.createRadialGradient(r, r, 0, r, r, r);
  for (let i = 0; i <= 16; i++) {
    const p = i / 16;
    const k = p < 0.55 ? 0 : Math.pow((p - 0.55) / 0.45, 2);
    g.addColorStop(p, `rgba(0,0,0,${(k * 0.82).toFixed(4)})`);
  }
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, lado, lado);
  return Texture.from(c);
}

/** Todas las texturas de la escena, generadas una vez. */
export interface Texturas {
  halo: Texture;
  sombra: Texture;
  haz: Texture;
  trama: Texture;
  vineta: Texture;
  destruir(): void;
}

export function generarTexturas(): Texturas {
  const halo = texturaHalo();
  const sombra = texturaSombra();
  const haz = texturaHaz();
  const trama = texturaTrama();
  const vineta = texturaVineta();
  return {
    halo,
    sombra,
    haz,
    trama,
    vineta,
    /** Sin esto, salir y entrar de la pantalla cinco veces deja cinco juegos de
     *  texturas en la memoria de la tarjeta. Es la fuga más fácil de provocar
     *  y la más difícil de notar: no falla, solo va poniéndose lento. */
    destruir() {
      for (const t of [halo, sombra, haz, trama, vineta]) t.destroy(true);
    }
  };
}
