import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import SeguimientoDeCuadrillas from './SeguimientoDeCuadrillas.svelte';

/**
 * Los cuadros del seguimiento, arriba de Programación (30/10/2026). El usuario:
 * «unos cuadros indicando la cuadrilla, qué tiene en progreso y qué tiempo
 * lleva, y un log contraíble de los seguimientos». Con la forma de
 * `campo/tiempos_del_dia.py` y `campo/dia_publicado.py`.
 */
const c = (extra = {}) => ({
  jornada: 'j-1',
  cuadrilla: 'Cuadrilla 1',
  labor: 'Soporte',
  resumen_del_dia: {
    salio: '07:42',
    hechas: 3,
    total: 6,
    en_curso: { numero: 12, estado: 'en_sitio', desde: '09:10', asunto: 'No Tiene Internet', minutos: 35 }
  },
  novedades: [],
  sin_reporte: null,
  log: [
    { hora: '07:10', texto: 'El Supervisor le asignó OT #12, #15', de: 'supervisor' },
    { hora: '07:42', texto: 'Salió hacia OT #12', de: 'tecnico' }
  ],
  ...extra
});

const html = (cuadrillas) => render(SeguimientoDeCuadrillas, { props: { cuadrillas } }).body;

describe('el cuadro de cada cuadrilla', () => {
  it('en qué está, el asunto, cuánto lleva y cuántas de cuántas', () => {
    const h = html([c()]);
    expect(h).toContain('En sitio · OT #12');
    expect(h).toContain('No Tiene Internet');
    expect(h).toContain('⏱ 35 min');
    expect(h).toContain('3 de 6 · salió 07:42');
    expect(h).toMatch(/<progress[^>]*max="6"[^>]*value="3"|<progress[^>]*value="3"[^>]*max="6"/);
  });

  it('el log del día, plegado, con lo del Supervisor distinguido', () => {
    const h = html([c()]);
    expect(h).toMatch(/<details class="sc-log[^"]*"><summary[^>]*>Seguimiento \(2\)<\/summary>/);
    expect(h).toMatch(/class="sc-log-supervisor[^"]*"><time[^>]*>07:10<\/time>/);
    expect(h).toContain('Salió hacia OT #12');
  });

  it('lo que pide atención: la novedad vigente y la orden sin reporte, en rojo', () => {
    const h = html([
      c({
        novedades: [{ id: 'n', vigente: true, tipo_texto: 'Se pinchó una llanta', afecta: 'media_hora',
                      avisada_en: '2026-10-30T10:12:00-05:00', hasta: '2026-10-30T10:42:00-05:00' }],
        sin_reporte: { numero: 15, minutos: 38 }
      })
    ]);
    expect(h).toMatch(/class="sc-cuadro[^"]*sc-alerta/);
    expect(h).toContain('⚠ Se pinchó una llanta · desde las 10:12 · hasta las 10:42');
    expect(h).toContain('⚠ Sin reporte hace 38 min · OT #15');
    expect(html([c()])).not.toContain('sc-alerta');
  });

  it('sin orden en curso dice si no salió, si está entre órdenes o si terminó', () => {
    const sin = (r) => html([c({ resumen_del_dia: r, log: [] })]);
    expect(sin({ salio: null, hechas: 0, total: 4, en_curso: null })).toContain('Todavía no sale');
    expect(sin({ salio: '07:42', hechas: 2, total: 4, en_curso: null })).toContain('Entre órdenes');
    expect(sin({ salio: '07:42', hechas: 4, total: 4, en_curso: null })).toContain('Terminó el día');
  });

  it('sin cuadrillas no dibuja nada', () => {
    expect(html([])).not.toContain('sc-cuadro');
  });
});
