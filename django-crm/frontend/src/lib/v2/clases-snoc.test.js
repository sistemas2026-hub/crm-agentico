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

  //  `class:snoc-x={condicion}` -- la directiva de Svelte, que NO es un
  //  atributo `class` y por eso se escapaba entera. Siete usos del detalle del
  //  hallazgo entraron asi, sin que la guarda mirara ninguno.
  for (const [, nombre] of limpia.matchAll(/class:(snoc-[a-z0-9-]+)/g)) usadas.add(nombre);

  return usadas;
}

/**
 * Las clases que se prenden cuando un dato NO llego, con el nombre tal cual.
 *
 * Se leen del `class:x={algo === AUSENTE}` del detalle: son las que marcan una
 * celda como dato ausente.
 */
function clasesDeDatoAusente(fuente) {
  const marcas = new Set();
  for (const [, nombre] of sinComentarios(fuente).matchAll(
    /class:(snoc-[a-z0-9-]+)=\{[^}]*AUSENTE/g
  ))
    marcas.add(nombre);
  return marcas;
}

/**
 * Lo que la hoja declara para `.clase` cuando es el selector completo.
 *
 * Los comentarios se van primero: el que va encima de una regla termina en un
 * cierre de comentario, y sin quitarlo el selector deja de estar al principio
 * de una declaracion -- la regla no se encuentra y la clase parece no tener
 * ningun estilo.
 *
 * Se parte por bloques en vez de armar una expresion regular con el nombre de
 * la clase interpolado: ese camino ya se escribio y se rompio dos veces con
 * los escapes.
 */
function reglasBaseDe(css, clase) {
  const limpia = css.replace(/\/\*[\s\S]*?\*\//g, ' ');
  const reglas = [];

  for (const bloque of limpia.split('}')) {
    const corte = bloque.indexOf('{');
    if (corte === -1) continue;
    const selector = bloque.slice(0, corte).trim();
    //  Solo el selector COMPLETO: `.x:hover` o `.x .y` son otra regla, y una
    //  media query llega aqui como el selector de dentro, que es lo que importa.
    if (selector === `.${clase}`) reglas.push(bloque.slice(corte + 1));
  }
  return reglas.join(';');
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

    // Y la directiva de Svelte tambien: es la forma que la guarda no leia.
    expect(clasesUsadas('<dd class:snoc-sin-fuente={v === AUSENTE}>').has('snoc-sin-fuente')).toBe(
      true
    );
  });

  /**
   * LA MARCA DE «FALTA EL DATO» PINTA TEXTO, NO UNA CAJA.
   *
   * No es una regla de gusto: `.snoc-ausente` ya existia en la hoja como una
   * caja con fondo y padding, y el detalle del hallazgo volvio a declararla
   * mas abajo como texto gris en cursiva. Las dos reglas se aplicaban a los
   * dos usos -- la celda de tabla se llevaba el fondo de caja y la caja se
   * llevaba la cursiva. La guarda de arriba lo dejo pasar entero, porque la
   * clase SI estaba definida: comprobaba su existencia, no que fuera una sola
   * cosa.
   *
   * Afirma sobre el efecto (que la clase no traiga caja), no sobre el nombre
   * que hoy tiene: renombrarla otra vez no rompe esta prueba, reusar una clase
   * de caja si.
   */
  it('la clase que marca un dato ausente no es una clase-caja', () => {
    const fuente = readFileSync(`${RUTA}/+page.svelte`, 'utf8');
    const marcas = [...clasesDeDatoAusente(fuente)];

    //  Si esto diera cero, lo de abajo pasaria sin mirar nada.
    expect(marcas.length).toBeGreaterThan(0);

    for (const clase of marcas) {
      const reglas = reglasBaseDe(css, clase);
      expect(reglas, `.${clase} no tiene reglas propias en la hoja`).not.toBe('');
      expect(reglas, `.${clase} trae fondo de caja`).not.toMatch(/background/);
      expect(reglas, `.${clase} trae padding de caja`).not.toMatch(/padding/);
      expect(reglas, `.${clase} es un contenedor, no texto`).not.toMatch(/display:\s*flex/);
    }
  });

  for (const archivo of ['+page.svelte', 'programacion/+page.svelte']) {
    it(`toda clase snoc- de ${archivo} existe en la hoja`, () => {
      const fuente = readFileSync(`${RUTA}/${archivo}`, 'utf8');
      const huerfanas = [...clasesUsadas(fuente)].filter((c) => !definidas.has(c)).sort();
      expect(huerfanas).toEqual([]);
    });
  }
});
