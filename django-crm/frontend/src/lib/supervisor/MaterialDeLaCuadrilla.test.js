import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import MaterialDeLaCuadrilla from './MaterialDeLaCuadrilla.svelte';

/**
 * El material de una cuadrilla en Programación (29/10/2026). El usuario, con la
 * tarjeta a la vista: «arriba se ve muy feo… el acta está de más… y los avisos,
 * que se contraigan como el material». Se mide lo que se dibuja, con la forma
 * de `campo/material_del_dia.py`.
 */
const FALTA = 'Le falta material para completar el kit (13 de 14 materiales): sale con lo que hay en bodega.';
const CATV = 'Sale sin ONU CATV: no puede hacer el trabajo que lo necesita.';
const WIFI = 'Sale sin ONU WIFI: no puede hacer el trabajo que lo necesita.';

const m = {
  kit: 'Kit de instalacion',
  kit_por: 'se parece por el nombre a «Instalacion»',
  bodega: 'BOG-SOLEDAD',
  bodega_por: 'su zona la nombra',
  lider: 'JEIDER AMELL',
  acta: 'MAT-20261029-f7fa6fcc',
  cargado_en: '2026-10-29T12:36:00-05:00',
  avisos: [FALTA, CATV, WIFI],
  lineas: [
    { material: 'CABLE DROP', unidad: 'm', kit: '150', en_mano: '0', necesita: '150', asignado: '0', falta: '150' }
  ]
};

const html = (props) => render(MaterialDeLaCuadrilla, { props }).body;

describe('el material de una cuadrilla', () => {
  it('a la vista: el kit, de dónde, para quién y cuándo se cargó; sin el acta', () => {
    const h = html({ m });
    expect(h).toContain('Kit de instalacion');
    expect(h).toContain('de BOG-SOLEDAD para JEIDER AMELL');
    expect(h).toContain('Cargado a las 12:36');
    expect(h).not.toContain('MAT-20261029');
  });

  it('los avisos se pliegan detrás de una línea que los resume', () => {
    const h = html({ m });
    expect(h).toMatch(/<details class="mc-avisos[^"]*"><summary[^>]*>Falta material · sale sin ONU CATV y ONU WIFI<\/summary>/);
    expect(h).toContain(CATV);
  });

  it('un solo aviso se muestra entero, sin desplegable', () => {
    const h = html({ m: { ...m, avisos: [CATV] } });
    expect(h).not.toContain('mc-avisos');
    expect(h).toMatch(/class="mc-aviso[^"]*">Sale sin ONU CATV/);
  });

  it('el porqué del kit y de la bodega va adentro de la lista, no a la vista', () => {
    const h = html({ m });
    const lineas = h.slice(h.indexOf('mc-lineas'));
    expect(lineas).toContain('Kit: lo eligió el Supervisor: se parece por el nombre');
    expect(lineas).toContain('Bodega: lo eligió el Supervisor: su zona la nombra');
    expect(h.slice(0, h.indexOf('mc-lineas'))).not.toContain('lo eligió el Supervisor');
  });

  it('con labor de apoyo dice los dos kits (30/10/2026)', () => {
    const h = html({ m: { ...m, kit: 'Kit de soporte', kit_apoyo: 'Kit de instalacion' } });
    expect(h).toMatch(/Kit de soporte<\/strong>(?:<!--[^>]*-->)?<span[^>]*>\s*\+\s*<\/span><strong[^>]*>Kit de instalacion<\/strong>/);
    expect(html({ m })).not.toContain(' + ');
  });

  it('sin cargar dice que es una propuesta', () => {
    expect(html({ m: { ...m, cargado_en: null } })).toContain('Propuesta');
  });
});
