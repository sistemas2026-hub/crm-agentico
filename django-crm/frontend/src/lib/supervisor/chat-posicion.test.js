import { describe, it, expect } from 'vitest';
import {
  MARGEN,
  SEPARACION,
  UMBRAL_PX,
  acotar,
  anclaje,
  esArrastre,
  estiloDe,
  leerGuardada
} from './chat-posicion.js';

/**
 * MOVER EL BOTÓN «PREGUNTAR» DEL SUPERVISOR  (25/11/2026)
 * =======================================================
 *
 * Se afirma sobre el EFECTO de cada decisión: que un temblor al hacer clic no
 * mueva el botón, que no se lo pueda soltar fuera de la pantalla, y que el
 * panel se abra hacia donde hay lugar. La última es la que rompería sin que
 * nadie lo note: un botón arriba con el panel abriéndose hacia arriba deja el
 * chat fuera de la ventana, y arrastrar "funciona".
 */

const VENTANA = { ancho: 1200, alto: 800 };
const BOTON = { ancho: 120, alto: 44 };

describe('arrastrar o hacer clic', () => {
  it('un temblor al presionar NO es un arrastre: el clic sigue abriendo el chat', () => {
    expect(esArrastre(0, 0)).toBe(false);
    expect(esArrastre(2, -3)).toBe(false);
    expect(esArrastre(UMBRAL_PX - 1, 0)).toBe(false);
  });

  it('pasado el umbral, en cualquier dirección, sí', () => {
    expect(esArrastre(UMBRAL_PX, 0)).toBe(true);
    expect(esArrastre(0, -UMBRAL_PX)).toBe(true);
    expect(esArrastre(-5, 5)).toBe(true);
  });
});

describe('hasta dónde puede ir', () => {
  it('una posición dentro de la ventana se respeta tal cual', () => {
    expect(acotar({ x: 300, y: 200 }, BOTON, VENTANA)).toEqual({ x: 300, y: 200 });
  });

  it('soltarlo fuera lo deja ENTERO adentro, a un margen del borde', () => {
    expect(acotar({ x: -500, y: -500 }, BOTON, VENTANA)).toEqual({ x: MARGEN, y: MARGEN });
    expect(acotar({ x: 5000, y: 5000 }, BOTON, VENTANA)).toEqual({
      x: VENTANA.ancho - BOTON.ancho - MARGEN,
      y: VENTANA.alto - BOTON.alto - MARGEN
    });
  });

  it('al achicar la ventana, lo guardado vuelve a entrar', () => {
    const chica = { ancho: 400, alto: 300 };
    const r = acotar({ x: 1000, y: 700 }, BOTON, chica);
    expect(r.x + BOTON.ancho).toBeLessThanOrEqual(chica.ancho - MARGEN);
    expect(r.y + BOTON.alto).toBeLessThanOrEqual(chica.alto - MARGEN);
  });

  it('en una ventana más chica que el botón gana el borde de arriba a la izquierda', () => {
    expect(acotar({ x: 50, y: 50 }, BOTON, { ancho: 60, alto: 20 })).toEqual({
      x: MARGEN,
      y: MARGEN
    });
  });
});

describe('hacia dónde se abre el panel', () => {
  it('abajo a la derecha (donde nace): cuelga de abajo y de la derecha', () => {
    const a = anclaje({ x: 1056, y: 732 }, BOTON, VENTANA);
    expect(a.horizontal).toBe('right');
    expect(a.vertical).toBe('bottom');
    expect(a.distanciaHorizontal).toBe(VENTANA.ancho - (1056 + BOTON.ancho));
    expect(a.distanciaVertical).toBe(VENTANA.alto - (732 + BOTON.alto));
  });

  it('ARRIBA: el panel se abre hacia abajo, y le queda lo que hay debajo del botón', () => {
    const a = anclaje({ x: 1056, y: 20 }, BOTON, VENTANA);
    expect(a.vertical).toBe('top');
    expect(a.distanciaVertical).toBe(20);
    expect(a.maxAlto).toBe(VENTANA.alto - (20 + BOTON.alto) - SEPARACION - MARGEN);
  });

  it('A LA IZQUIERDA: el panel crece hacia la derecha, y le queda de ahí al otro borde', () => {
    const a = anclaje({ x: 20, y: 732 }, BOTON, VENTANA);
    expect(a.horizontal).toBe('left');
    expect(a.distanciaHorizontal).toBe(20);
    expect(a.maxAncho).toBe(VENTANA.ancho - 20 - MARGEN);
  });

  it('el panel nunca recibe más lugar del que hay entre el botón y el borde', () => {
    //  En cada cuadrante: el panel, con el máximo que se le da, cabe entero.
    for (const pos of [
      { x: 8, y: 8 },
      { x: 1072, y: 8 },
      { x: 8, y: 748 },
      { x: 1072, y: 748 },
      { x: 560, y: 390 }
    ]) {
      const a = anclaje(pos, BOTON, VENTANA);
      const espacioH =
        a.horizontal === 'right' ? pos.x + BOTON.ancho : VENTANA.ancho - pos.x;
      const espacioV =
        a.vertical === 'bottom' ? pos.y : VENTANA.alto - (pos.y + BOTON.alto);
      expect(a.maxAncho).toBeLessThanOrEqual(espacioH - MARGEN);
      expect(a.maxAlto).toBeLessThanOrEqual(espacioV - SEPARACION - MARGEN);
      expect(a.maxAncho).toBeGreaterThanOrEqual(0);
      expect(a.maxAlto).toBeGreaterThanOrEqual(0);
    }
  });

  it('en una ventana mínima no devuelve tamaños negativos', () => {
    const a = anclaje({ x: 8, y: 8 }, BOTON, { ancho: 100, alto: 40 });
    expect(a.maxAncho).toBeGreaterThanOrEqual(0);
    expect(a.maxAlto).toBeGreaterThanOrEqual(0);
  });
});

describe('el estilo del contenedor', () => {
  it('fija UN lado por eje y suelta el opuesto: con los dos se estiraría', () => {
    const s = estiloDe(anclaje({ x: 20, y: 20 }, BOTON, VENTANA));
    expect(s).toContain('left:20px');
    expect(s).toContain('right:auto');
    expect(s).toContain('top:20px');
    expect(s).toContain('bottom:auto');
  });

  it('con el botón arriba invierte la columna: el panel queda debajo', () => {
    expect(estiloDe(anclaje({ x: 1056, y: 20 }, BOTON, VENTANA))).toContain(
      'flex-direction:column-reverse'
    );
    expect(estiloDe(anclaje({ x: 1056, y: 732 }, BOTON, VENTANA))).toContain(
      'flex-direction:column;'
    );
  });

  it('alinea el panel con el borde del que cuelga el botón', () => {
    expect(estiloDe(anclaje({ x: 20, y: 732 }, BOTON, VENTANA))).toContain(
      'align-items:flex-start'
    );
    expect(estiloDe(anclaje({ x: 1056, y: 732 }, BOTON, VENTANA))).toContain(
      'align-items:flex-end'
    );
  });
});

describe('lo guardado en el navegador', () => {
  it('una posición bien escrita vuelve', () => {
    expect(leerGuardada('{"x":120,"y":340}')).toEqual({ x: 120, y: 340 });
  });

  it('lo que no sirve devuelve null, y el botón vuelve a su esquina', () => {
    for (const malo of [null, undefined, '', 'no es json', '[]', '"texto"', '{"x":1}',
      '{"x":"10","y":20}', '{"x":null,"y":20}', '{"x":1e999,"y":2}']) {
      expect(leerGuardada(malo)).toBeNull();
    }
  });
});
