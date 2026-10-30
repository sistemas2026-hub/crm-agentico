import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import OrdenDelDia from './OrdenDelDia.svelte';
import { textoDelDiaDeLaCuadrilla, textoDeSeguimiento, textoDeTiempos } from './dia-publicado.js';

/**
 * El seguimiento de las cuadrillas en Programación (30/10/2026). El usuario:
 * «¿cómo le lleva el Supervisor el seguimiento a los técnicos, de cuánto han
 * demorado?», y que se vea en Programación («dale»). Con la forma de
 * `campo/tiempos_del_dia.py` y `services/salud_seguimiento.py`.
 */
describe('los textos', () => {
  it('los tiempos de una orden: traslado y en sitio; o cuánto lleva en sitio', () => {
    expect(textoDeTiempos({ traslado_min: 28, en_sitio_min: 40 })).toBe('28 min en camino · 40 min en sitio');
    expect(textoDeTiempos({ traslado_min: 12, en_sitio_min: null, en_sitio_hace_min: 35 })).toBe(
      '12 min en camino · en sitio hace 35 min'
    );
    expect(textoDeTiempos({ traslado_min: null, en_sitio_min: null })).toBe('');
    expect(textoDeTiempos(null)).toBe('');
  });

  it('el día de la cuadrilla en una línea', () => {
    expect(
      textoDelDiaDeLaCuadrilla({
        salio: '07:42',
        hechas: 3,
        total: 6,
        en_curso: { numero: 12, estado: 'en_sitio', desde: '09:10' }
      })
    ).toBe('Salió 07:42 · 3 de 6 hechas · en sitio en OT #12 desde 09:10');
    expect(
      textoDelDiaDeLaCuadrilla({ salio: '07:42', hechas: 0, total: 2, en_curso: { numero: 5, estado: 'en_camino', desde: '07:42' } })
    ).toBe('Salió 07:42 · 0 de 2 hechas · en camino a OT #5 desde 07:42');
    expect(textoDelDiaDeLaCuadrilla({ salio: null, hechas: 0, total: 4, en_curso: null })).toBe(
      'Todavía no sale · 0 de 4 hechas'
    );
  });

  it('la regla de los 30 minutos: vencida, o por qué no corre', () => {
    expect(textoDeSeguimiento({ tipo: 'vencido', minutos_desde_la_referencia: 38 })).toBe('Sin reporte hace 38 min');
    expect(textoDeSeguimiento({ tipo: 'pausado_noc' })).toBe('Pausado: espera al NOC');
    expect(textoDeSeguimiento({ tipo: 'pausado_novedad' })).toBe('Pausado por la novedad de la cuadrilla');
    expect(textoDeSeguimiento({ tipo: 'al_dia' })).toBe('');
  });
});

describe('en la tarjeta de la orden', () => {
  const orden = {
    numero: 12,
    estado: 'en_sitio',
    estado_texto: 'En sitio',
    asunto: 'No Tiene Internet',
    tecnicos: [],
    tiempos: { traslado_min: 12, en_sitio_min: null, en_sitio_hace_min: 35 },
    seguimiento: { tipo: 'vencido', minutos_desde_la_referencia: 38 }
  };
  const html = (o) => render(OrdenDelDia, { props: { orden: o, dia: '2026-10-30' } }).body;

  it('dice cuánto lleva, y en rojo si dejó de reportar', () => {
    const h = html(orden);
    expect(h).toContain('12 min en camino · en sitio hace 35 min');
    expect(h).toMatch(/class="od-seguimiento[^"]*od-seguimiento-vencido[^"]*">Sin reporte hace 38 min/);
  });

  it('sin tiempos ni seguimiento, no dibuja la línea', () => {
    expect(html({ ...orden, tiempos: null, seguimiento: null })).not.toContain('od-tiempos');
  });
});
