import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import MapaDeCuadrillas from './MapaDeCuadrillas.svelte';

/**
 * EL MAPA DE CUADRILLAS (31/10/2026).
 *
 * Se mide lo que se dibuja en el servidor: la cabecera, la cuenta de quién
 * reporta, la advertencia de lo que un punto significa y quién quedó sin
 * señal. Leaflet solo corre en el navegador (`onMount`), así que los pines no
 * entran acá — por eso lo que se afirma es lo que el supervisor LEE alrededor
 * del mapa, que es donde está el riesgo de que un punto se lea como un hecho
 * sobre una persona.
 */
const posicion = (extra = {}) => ({
  latitud: 10.9185, longitud: -74.7668, precision_m: 8, bateria: 72,
  minutos: 3, fresca: true, precision_pobre: false,
  medida_en: '2026-10-31T11:20:00-05:00', de: 'Mario Vásquez', ...extra
});
const cuadrilla = (extra = {}) => ({
  jornada: 'j-1', cuadrilla: 'Cuadrilla #5', ordenes: [], posicion: posicion(), ...extra
});
const html = (cuadrillas) => render(MapaDeCuadrillas, { props: { cuadrillas } }).body;

describe('el mapa de cuadrillas', () => {
  it('cuenta cuántas reportan, sobre el total', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null }),
      cuadrilla({ jornada: 'j-3', cuadrilla: 'Cuadrilla #1', posicion: null })
    ]);

    expect(h).toContain('1 de 3 reportando');
  });

  it('nombra a las que están sin señal, en vez de dejarlas invisibles', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null })
    ]);

    expect(h).toContain('Sin señal:');
    expect(h).toContain('Cuadrilla #3');
    expect(h).not.toMatch(/Sin señal:[^<]*Cuadrilla #5/);
  });

  it('con todas reportando no dice que falte ninguna', () => {
    expect(html([cuadrilla()])).not.toContain('Sin señal:');
  });

  it('dice siempre qué significa un punto y qué significa lo atenuado', () => {
    const h = html([cuadrilla()]);

    expect(h).toContain('no que la persona esté ahí');
    expect(h).toContain('es dónde estuvo, no dónde está');
  });

  it('sin ninguna cuadrilla no revienta y sigue dibujando la caja', () => {
    for (const vacio of [[], undefined]) {
      const h = html(vacio);
      expect(h).toContain('0 de 0 reportando');
      expect(h).toContain('class="mp-caja');
    }
  });
});
