import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import NovedadesDeLaCuadrilla from './NovedadesDeLaCuadrilla.svelte';
import { textoDeNovedad } from './dia-publicado.js';

/**
 * Las novedades de una cuadrilla en Programación (30/10/2026). El usuario:
 * «¿cómo el técnico reporta alguna novedad sin escribir en el ticket, por
 * ejemplo se pinchó la llanta?», y que el seguimiento se vea en Programación.
 * Con la forma de `campo/novedades.py::a_json`.
 */
const n = (extra = {}) => ({
  id: 'n-1',
  tipo: 'llanta',
  tipo_texto: 'Se pinchó una llanta',
  afecta: 'media_hora',
  texto: '',
  avisada_en: '2026-10-30T10:12:00-05:00',
  hasta: '2026-10-30T10:42:00-05:00',
  resuelta_en: null,
  vigente: true,
  quien: 'Jeider Amell',
  ...extra
});

const html = (novedades) => render(NovedadesDeLaCuadrilla, { props: { novedades } }).body;

describe('cuándo fue', () => {
  it('vigente: hasta su hora, o el resto del día', () => {
    expect(textoDeNovedad(n())).toBe('desde las 10:12 · hasta las 10:42');
    expect(textoDeNovedad(n({ afecta: 'resto_del_dia', hasta: null }))).toBe(
      'desde las 10:12 · el resto del día'
    );
  });

  it('terminada: lo que llegó antes, «Ya seguí» o su hora', () => {
    expect(textoDeNovedad(n({ vigente: false }))).toBe('de 10:12 a 10:42');
    expect(textoDeNovedad(n({ vigente: false, resuelta_en: '2026-10-30T10:30:00-05:00' }))).toBe(
      'de 10:12 a 10:30'
    );
    expect(
      textoDeNovedad(n({ vigente: false, hasta: null, resuelta_en: '2026-10-30T15:00:00-05:00' }))
    ).toBe('de 10:12 a 15:00');
  });
});

describe('lo que se dibuja', () => {
  it('la vigente, en rojo y con quién avisó; la del resto del día dice qué pasa con sus órdenes', () => {
    const h = html([n({ afecta: 'resto_del_dia', hasta: null, texto: 'en la autopista' })]);
    expect(h).toMatch(/class="nc nc-vigente[^"]*"/);
    expect(h).toContain('Se pinchó una llanta');
    expect(h).toContain('Sus órdenes sin empezar pasan a otra cuadrilla.');
    expect(h).toContain('«en la autopista»');
    expect(h).toContain('Avisó Jeider Amell');
  });

  it('la corta no dice que sus órdenes pasan a otra', () => {
    expect(html([n()])).not.toContain('pasan a otra cuadrilla');
  });

  it('las que terminaron, en una línea gris; sin novedades, nada', () => {
    const h = html([n({ vigente: false })]);
    expect(h).not.toContain('nc-vigente');
    expect(h).toContain('Hoy hubo: se pinchó una llanta (de 10:12 a 10:42)');
    expect(html([])).not.toContain('nc');
  });
});
