import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * EL SHELL DE (app) NO SCROLLEA, Y ESO SORPRENDE DOS VECES.
 *
 * `.v2-shell` es `height:100vh; overflow:hidden` y `.v2-main` tambien recorta
 * (lib/v2/styles/v2.css). El unico contenedor que se desplaza es `.v2-scroll`.
 * Una pantalla que se olvida de el se ve perfecta mientras el contenido quepa
 * en la ventana, y se recorta en silencio en cuanto crece: sin error, sin
 * barra, sin nada que mirar.
 *
 * Ya paso dos veces por la misma razon:
 *
 *   - settings/guias-tv, el 10/09/2026. Usaba `v2-page`, una clase que solo
 *     existe dentro de settings/oferta, y Svelte aisla estilos por componente.
 *     Con el catalogo vacio no se noto; con las 19 guias cargadas, todo lo que
 *     pasaba del alto quedo inalcanzable.
 *
 *   - supervisor-noc. Traia su propia hoja de estilos con su propio sistema de
 *     layout, asi que parecia una pantalla terminada. Lo reporto una persona
 *     mirandola, que es como se encuentran los bugs que ninguna prueba mira.
 *
 * LO QUE ESTA GUARDA SI HACE Y LO QUE NO
 * --------------------------------------
 * NO prueba que la pantalla scrollee: eso necesita un navegador con una
 * ventana de un alto concreto, y aqui no hay ninguno. Lo que hace es mas
 * modesto y cubre el caso que de verdad ocurrio: avisar cuando una pantalla
 * trae su PROPIO sistema de layout --una hoja de estilos importada-- y no
 * engancha el del shell. Las dos veces que fallo, fallo exactamente asi.
 *
 * Si algun dia una pantalla con CSS propio legitimamente no necesita el
 * contenedor, la respuesta es agregarla a EXENTAS con el motivo escrito, no
 * borrar esto.
 */

const APP = new URL('../../routes/(app)', import.meta.url).pathname.replace(
  /^\/([A-Za-z]:)/,
  '$1'
);

/** Pantallas con hoja propia que no necesitan el contenedor, con su motivo. */
const EXENTAS = {
  // (ninguna todavia)
};

/**
 * Si la pantalla USA la clase, no si la nombra.
 *
 * Dos versiones anteriores de esta comprobacion fallaron, y conviene que
 * queden escritas porque las dos son faciles de repetir:
 *
 *   1. `fuente.includes('v2-scroll')` pasaba con la clase QUITADA, porque el
 *      comentario que explica por que hace falta contiene esas mismas letras.
 *      Una guarda satisfecha por su propia documentacion no vigila nada.
 *
 *   2. La correccion uso un limite de palabra y lo que termino escrito en el
 *      archivo fue un caracter de RETROCESO literal (U+0008), asi que la
 *      expresion no casaba nunca. Esa fallo en rojo, que es la direccion
 *      afortunada.
 *
 * Por eso aqui no hay ningun escape: se extraen los atributos `class` y se
 * miran sus palabras una por una.
 */
function enganchaScroll(fuente) {
  for (const [, valor] of fuente.matchAll(/class=["']([^"']*)["']/g)) {
    if (valor.split(/\s+/).includes('v2-scroll')) return true;
  }
  return false;
}

/** Todas las `+page.svelte` bajo (app). */
function pantallas(dir, halladas = []) {
  for (const entrada of readdirSync(dir)) {
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) pantallas(ruta, halladas);
    else if (entrada === '+page.svelte') halladas.push(ruta);
  }
  return halladas;
}

describe('el contenedor que se desplaza', () => {
  const todas = pantallas(APP);

  it('encuentra las pantallas de (app)', () => {
    // Si esto diera cero, todo lo de abajo pasaria sin mirar nada.
    expect(todas.length).toBeGreaterThan(10);
  });

  it('reconoce la clase solo cuando esta de verdad', () => {
    // La comprobacion se comprueba a si misma, porque ya se equivoco en las
    // dos direcciones: un falso verde y un falso rojo.
    expect(enganchaScroll('<div class="v2-scroll">')).toBe(true);
    expect(enganchaScroll('<div class="algo v2-scroll otra">')).toBe(true);
    expect(enganchaScroll("<div class='v2-scroll'>")).toBe(true);

    expect(enganchaScroll('<!-- v2-scroll es el que scrollea -->')).toBe(false);
    expect(enganchaScroll('<div class="v2-scrollable">')).toBe(false);
    expect(enganchaScroll('<div class="no-v2-scroll">')).toBe(false);
  });

  it('toda pantalla con hoja de estilos propia engancha v2-scroll', () => {
    const sinScroll = [];
    for (const ruta of todas) {
      const fuente = readFileSync(ruta, 'utf8');
      const traeCss = /import\s+['"]\.\/[^'"]+\.css['"]/.test(fuente);
      if (!traeCss) continue;

      const corta = relative(APP, ruta).replace(/\\/g, '/');
      if (corta in EXENTAS) continue;
      if (!enganchaScroll(fuente)) sinScroll.push(corta);
    }

    expect(sinScroll).toEqual([]);
  });

  it('en supervisor-noc el modal queda fuera del contenedor', () => {
    // El modal es position:fixed y cubre la ventana. Dentro del contenedor
    // desplazado se moveria con el contenido.
    const fuente = readFileSync(join(APP, 'supervisor-noc', '+page.svelte'), 'utf8');
    expect(enganchaScroll(fuente)).toBe(true);

    const scroll = fuente.search(/class=["'][^"']*v2-scroll/);
    const modal = fuente.indexOf('MODAL DE DETALLE');
    expect(modal).toBeGreaterThan(scroll);

    // Entre la apertura y el modal tiene que haber un cierre: si el modal
    // quedara dentro, no habria ninguno.
    expect(fuente.slice(scroll, modal)).toContain('</div>');
  });
});
