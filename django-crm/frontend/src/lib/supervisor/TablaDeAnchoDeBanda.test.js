import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import TablaDeAnchoDeBanda from './TablaDeAnchoDeBanda.svelte';
import { etiquetaDePerfil, filasDePerfiles, quedaPorDebajo, velocidadKbps } from './perfiles-de-velocidad.js';

/**
 * LA TABLA DE ANCHO DE BANDA, PROBADA POR LO QUE DIBUJA (27/11/2026).
 *
 * Al cargarla en producción, ELITE (350 de subida) quedó dos veces con un
 * perfil más chico: «PLAN_100MB» y «PLAN_1000MB» se confunden a simple vista.
 * Ahora cada opción dice su velocidad y la fila avisa si queda corta.
 */

//  Los perfiles de subida reales de la cuenta (get_speed_profiles, 27/11/2026).
const SUBIDA = [
  { nombre: 'Unlimited', kbps: 0 }, { nombre: 'PLAN_50MB', kbps: 54784 },
  { nombre: 'PLAN_100MB', kbps: 112640 }, { nombre: 'PLAN_250MB', kbps: 256320 },
  { nombre: 'PLAN_300MB', kbps: 315136 }, { nombre: 'PLAN_1000MB', kbps: 1012640 }
];
const BAJADA = [{ nombre: 'PLAN_700MB', kbps: 766000 }, { nombre: 'PLAN_500MB', kbps: 512640 }];
const DEL_MOTOR = /** @type {any} */ ({
  disponible: true, error: '', perfiles: { bajada: BAJADA, subida: SUBIDA },
  planes: [
    { nombre: 'PLAN ELITE', bajada: '700M', subida: '350M', sugerido: { bajada: 'PLAN_700MB', subida: 'PLAN_1000MB' } },
    { nombre: 'PLAN ULTRA', bajada: '500M', subida: '250M', sugerido: { bajada: 'PLAN_500MB', subida: 'PLAN_250MB' } }
  ]
});

/** @param {any[]} guardados */
const pintar = (guardados) => render(TablaDeAnchoDeBanda, {
  props: { perfiles: { ...DEL_MOTOR, filas: filasDePerfiles(DEL_MOTOR, guardados) } }
}).body.replace(/<!--[^>]*-->/g, '');

describe('la lista dice la velocidad y cuál es la sugerida', () => {
  it('cada opción con su velocidad, y la sugerida marcada en su plan', () => {
    const html = pintar([]);
    expect(html).toContain('PLAN_1000MB — 1013 megas · sugerido');
    expect(html).toContain('PLAN_100MB — 113 megas<');
    expect(html).toContain('Unlimited — sin límite');
  });

  it('cada lista sale con lo guardado elegido', () => {
    const html = pintar([{ plan: 'PLAN ELITE', bajada: 'PLAN_700MB', subida: 'PLAN_100MB' }]);
    expect(html).toMatch(/<option value="PLAN_100MB" selected[^>]*>PLAN_100MB — 113 megas/);
  });
});

describe('avisa si lo elegido queda por debajo de lo que paga el cliente', () => {
  it('ELITE con PLAN_100MB de subida (lo que pasó en producción) se avisa', () => {
    const html = pintar([{ plan: 'PLAN ELITE', bajada: 'PLAN_700MB', subida: 'PLAN_100MB' },
                         { plan: 'PLAN ULTRA', bajada: 'PLAN_500MB', subida: 'PLAN_250MB' }]);
    expect(html).toContain('PLAN ELITE: la subida queda');
    expect(html).toContain('por debajo de lo que paga el cliente (700M / 350M)');
    expect(html).not.toContain('PLAN ULTRA: la');
  });

  it('con lo sugerido no hay ningún aviso', () => {
    expect(pintar([])).not.toContain('por debajo de lo que paga');
  });
});

describe('las cuentas de la tabla', () => {
  it('la velocidad del plan, como la escribe WispHub', () => {
    expect(velocidadKbps('350M')).toBe(350000);
    expect(velocidadKbps('215040k')).toBe(215040);
    expect(velocidadKbps('100')).toBe(null);
  });

  it('queda por debajo: sí, no, o no se sabe', () => {
    expect(quedaPorDebajo('PLAN_300MB', SUBIDA, 350000)).toBe(true);
    expect(quedaPorDebajo('PLAN_1000MB', SUBIDA, 350000)).toBe(false);
    expect(quedaPorDebajo('Unlimited', SUBIDA, 350000)).toBe(null);
    expect(quedaPorDebajo('', SUBIDA, 350000)).toBe(null);
    expect(quedaPorDebajo('PLAN_300MB', SUBIDA, null)).toBe(null);
  });

  it('la etiqueta sin velocidad conocida es solo el nombre', () => {
    expect(etiquetaDePerfil({ nombre: 'RARO', kbps: null })).toBe('RARO');
  });
});
