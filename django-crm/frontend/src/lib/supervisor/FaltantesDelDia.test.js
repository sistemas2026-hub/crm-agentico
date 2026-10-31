import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import FaltantesDelDia from './FaltantesDelDia.svelte';
import { cuantosFaltan, faltantesPorBodega, pastillasDeCuentas } from './material-del-dia.js';

/**
 * Las cuentas y los faltantes del material del día (29/10/2026). El usuario,
 * con la captura de trece líneas rojas iguales: «¿qué podemos hacer con esto
 * para que se vea más estético?». Se mide lo que se dibuja, con la forma de
 * `campo/material_del_dia.py`.
 */
const f = (bodega, material, disponible = '0', pedido = '10', unidad = 'unidades') => ({
  bodega,
  material,
  unidad,
  disponible,
  pedido,
  falta: String(Number(pedido) - Number(disponible))
});

const cuentas = { cuadrillas: 5, completas: 1, con_faltantes: 3, sin_carga: 1 };
const faltantes = [
  f('BOG-SOLEDAD', 'CABLE DROP', '0', '2000', 'm'),
  f('BOG-SOLEDAD', 'CHAZO', '0', '30'),
  f('BOG-NORTE', 'ONU WIFI', '2', '8'),
  // Mixta: de una cosa hay algo, de otra nada. No es «stock sin cargar».
  f('BOG-NORTE', 'TENSOR', '0', '5')
];

const html = (props) => render(FaltantesDelDia, { props }).body;

describe('los ayudantes', () => {
  it('las cuentas en pastillas; lo que está en cero no se dice, salvo las completas', () => {
    expect(pastillasDeCuentas(cuentas)).toEqual([
      { texto: '1 de 5 con el kit completo', tono: 'ok' },
      { texto: '3 con faltantes', tono: 'falta' },
      { texto: '1 sin carga', tono: 'sin' }
    ]);
    expect(pastillasDeCuentas({ cuadrillas: 4, completas: 0, con_faltantes: 0, sin_carga: 0 })).toEqual([
      { texto: '0 de 4 con el kit completo', tono: 'ok' }
    ]);
  });

  it('una entrada por bodega, en el orden en que llegan; «sin nada» si no hay libre nada', () => {
    const g = faltantesPorBodega(faltantes);
    expect(g.map((x) => [x.bodega, x.materiales.length, x.sinNada])).toEqual([
      ['BOG-SOLEDAD', 2, true],
      ['BOG-NORTE', 2, false]
    ]);
    expect(cuantosFaltan(13)).toBe('le faltan 13 materiales');
    expect(cuantosFaltan(1)).toBe('le falta 1 material');
  });
});

describe('lo que se dibuja', () => {
  it('una línea por bodega, plegada, y no una por material', () => {
    const h = html({ cuentas, faltantes });
    expect(h.match(/<details class="fd-bodega/g)).toHaveLength(2);
    expect(h).toMatch(/BOG-SOLEDAD<\/span>\s*<span class="fd-cuenta[^"]*">le faltan 2 materiales/);
    expect(h).not.toContain('libres; se piden');
  });

  it('la tabla dice material, cuánto se pide, cuánto hay y cuánto falta', () => {
    const h = html({ cuentas, faltantes });
    expect(h).toMatch(/<td[^>]*>CABLE DROP<\/td>\s*<td[^>]*>2000 m<\/td>\s*<td[^>]*>0<\/td>\s*<td class="fd-faltan[^"]*">2000<\/td>/);
    // Con algo libre, lo que falta no es lo que se pide.
    expect(h).toMatch(/<td[^>]*>ONU WIFI<\/td>\s*<td[^>]*>8 unidades<\/td>\s*<td[^>]*>2<\/td>\s*<td class="fd-faltan[^"]*">6<\/td>/);
  });

  it('la pista del stock sin cargar, solo en la bodega que no tiene libre nada', () => {
    const h = html({ cuentas, faltantes });
    expect(h.match(/falta cargar su\s+stock en Inventario/g)).toHaveLength(1);
    const norte = h.slice(h.indexOf('BOG-NORTE'));
    expect(norte).not.toContain('falta cargar');
  });

  it('sin faltantes, solo las pastillas', () => {
    const h = html({ cuentas: { cuadrillas: 2, completas: 2 }, faltantes: [] });
    expect(h).toContain('2 de 2 con el kit completo');
    expect(h).not.toContain('fd-bodega');
  });
});
