import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import OrdenDelDia from './OrdenDelDia.svelte';
import { textoDeSeguimiento, textoDeTiempos } from './dia-publicado.js';

/**
 * El seguimiento de las cuadrillas en Programación (30/10/2026). El usuario:
 * «¿cómo le lleva el Supervisor el seguimiento a los técnicos, de cuánto han
 * demorado?», y que se vea en Programación («dale»). Con la forma de
 * `campo/tiempos_del_dia.py` y `services/salud_seguimiento.py`.
 */
describe('los textos', () => {
  it('los tiempos de una orden: traslado y en sitio; o cuánto lleva en sitio', () => {
    expect(textoDeTiempos({ traslado_min: 28, en_sitio_min: 40 })).toBe('28 min en camino · 40 min en sitio');
    expect(
      textoDeTiempos({ traslado_min: 0, en_sitio_min: null, en_sitio_hace_min: null, en_sitio_desde: '15/10 18:43' })
    ).toBe('0 min en camino · en sitio desde el 15/10 18:43');
    expect(textoDeTiempos({ traslado_min: 12, en_sitio_min: null, en_sitio_hace_min: 35 })).toBe(
      '12 min en camino · en sitio hace 35 min'
    );
    expect(textoDeTiempos({ traslado_min: null, en_sitio_min: null })).toBe('');
    expect(textoDeTiempos(null)).toBe('');
  });

  //  ACÁ SE PROBABA `textoDelDiaDeLaCuadrilla` (30/10/2026 – 07/11/2026): el
  //  día de una cuadrilla en una línea, dentro de su tarjeta. La función se
  //  fue con su único llamador —el cuadro de Seguimiento, arriba en la misma
  //  pantalla, ya lo dice mejor— y sus pruebas con ella: una suite en verde
  //  sobre código que nadie ejecuta es justo el falso verde que este proyecto
  //  persigue. Que la tarjeta no lo repita lo mide
  //  `routes/(app)/supervisor-noc/tarjetas-de-cuadrilla.test.js`.

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
