import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

/**
 * UNA CLASE QUE NO EXISTE NO AVISA DE NADA.
 *
 * El CSS no da error por una clase que no esta definida: el elemento
 * simplemente no toma ese estilo. La pantalla se ve casi bien, y lo que
 * fallaba era justo lo que esa clase hacia.
 *
 * Ya paso: settings/guias-tv usaba `v2-page`, una clase que solo existe
 * DENTRO de otro componente. Svelte aisla los estilos por componente, asi que
 * ahi no aplicaba nada y la pagina quedo sin el contenedor que la desplaza.
 * Nadie lo vio hasta que el catalogo crecio.
 *
 * supervisor-noc es la pantalla mas expuesta a esto: tiene ~90 clases propias
 * en una hoja aparte, y varias se agregaron de a una mientras se armaba el
 * tablero. Esta guarda las cruza.
 *
 * LO QUE NO MIRA
 * --------------
 * Que la clase HAGA lo correcto. Solo que exista. Una `.snoc-tabla-alta`
 * definida con el alto equivocado pasa igual -- eso se ve abriendo la
 * pantalla, no aqui.
 */

const RUTA = new URL('../../routes/(app)/supervisor-noc', import.meta.url).pathname.replace(
  /^\/([A-Za-z]:)/,
  '$1'
);

/**
 * El componente sin sus comentarios.
 *
 * Los comentarios de este archivo NOMBRAN clases al explicar por que estan
 * ("el alto vive en .snoc-tabla-alta"), y una clase citada en una explicacion
 * no es una clase usada. Sin quitarlos, borrar una clase y su regla dejaria
 * la guarda en verde mientras el comentario siga hablando de ella.
 */
function sinComentarios(fuente) {
  return fuente
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:])\/\/.*$/gm, '$1 ');
}

/**
 * Las clases `snoc-` que el componente usa de verdad.
 *
 * Se leen SOLO de los atributos `class`, y por dos razones que la primera
 * version de esta guarda aprendio a golpes -- reclamo por diez nombres que no
 * eran clases:
 *
 *   - `var(--snoc-md)`, `--snoc-on-surface`: son VARIABLES, viven en `style=`
 *     y en la hoja como propiedades, no como reglas `.snoc-md`.
 *   - `id="snoc-modal-titulo"`, `aria-labelledby`: son identificadores. Que
 *     compartan el prefijo no los hace clases.
 *
 * Se saltan ademas las que terminan en una llave --`snoc-tono-{k.tono}`,
 * `snoc-riel-{t.tono}`, `snoc-sla-{sla.tono}`-- porque ahi el nombre se arma
 * en tiempo de ejecucion y el trozo literal nunca existe como regla. Sus
 * variantes completas si estan en la hoja; comprobarlas exigiria saber que
 * valores toma cada una, y eso es adivinar.
 */
function clasesUsadas(fuente) {
  const limpia = sinComentarios(fuente);
  const usadas = new Set();

  // `class="…"` y `class={…}`: el segundo cubre los ternarios sueltos, como
  // `class={abierta === p.id ? 'snoc-fila-activa' : ''}`.
  for (const re of [/class="([^"]*)"/g, /class=\{([^}]*)\}/g]) {
    for (const [, valor] of limpia.matchAll(re)) {
      for (const m of valor.matchAll(/snoc-[a-z0-9-]+/g)) {
        if (valor[m.index + m[0].length] === '{') continue;
        usadas.add(m[0]);
      }
    }
  }
  return usadas;
}

/** Las clases que la hoja define. */
function clasesDefinidas(css) {
  const definidas = new Set();
  for (const m of css.matchAll(/\.(snoc-[a-z0-9-]+)/g)) definidas.add(m[1]);
  return definidas;
}

describe('las clases propias de supervisor-noc', () => {
  const css = readFileSync(`${RUTA}/supervisor-noc.css`, 'utf8');
  const definidas = clasesDefinidas(css);

  it('la hoja define un monton de clases', () => {
    // Si esto diera cero, todo lo de abajo fallaria por la razon equivocada.
    expect(definidas.size).toBeGreaterThan(50);
  });

  it('distingue una clase usada de una solo nombrada en un comentario', () => {
    // La guarda se comprueba a si misma: ya hubo una que se daba por
    // satisfecha con su propia documentacion.
    expect(clasesUsadas('<div class="snoc-real">').has('snoc-real')).toBe(true);
    expect(clasesUsadas('<!-- el alto vive en snoc-citada -->').has('snoc-citada')).toBe(false);
    expect(clasesUsadas('/* ver snoc-citada */').has('snoc-citada')).toBe(false);

    // Y no reclama por las que se arman en tiempo de ejecucion.
    expect(clasesUsadas('<div class="snoc-tono-{k.tono}">').has('snoc-tono-')).toBe(false);

    // Ni por lo que comparte el prefijo sin ser una clase: los diez nombres
    // con los que fallo la primera version eran de estas dos formas.
    expect(clasesUsadas('<div style="gap:var(--snoc-md)">').size).toBe(0);
    expect(clasesUsadas('<h2 id="snoc-modal-titulo">').size).toBe(0);

    // Un ternario suelto si cuenta.
    expect(clasesUsadas("<tr class={x ? 'snoc-fila-activa' : ''}>").has('snoc-fila-activa')).toBe(
      true
    );
  });

  for (const archivo of ['+page.svelte', 'programacion/+page.svelte']) {
    it(`toda clase snoc- de ${archivo} existe en la hoja`, () => {
      const fuente = readFileSync(`${RUTA}/${archivo}`, 'utf8');
      const huerfanas = [...clasesUsadas(fuente)].filter((c) => !definidas.has(c)).sort();
      expect(huerfanas).toEqual([]);
    });
  }
});
