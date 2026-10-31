import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/**
 * LAS TARJETAS DE CUADRILLA NO REPARTEN SU CONTENIDO (28/10/2026).
 *
 * `.snoc-tarjeta` trae `justify-content: space-between`. En la rejilla de
 * cuadrillas la tarjeta se estira a la altura de la más larga, y con eso las
 * órdenes de una cuadrilla con pocas quedaban separadas por huecos enormes
 * (captura del usuario en Programación; Simular el día tenía lo mismo).
 */
const RUTA = 'src/routes/(app)/supervisor-noc';

describe('las tarjetas de cuadrilla', () => {
  for (const archivo of ['programacion/+page.svelte', 'despacho/+page.svelte']) {
    it(`${archivo}: el contenido va arriba`, () => {
      const fuente = readFileSync(`${RUTA}/${archivo}`, 'utf8');
      const tarjetas = fuente.match(/<div class="snoc-tarjeta snoc-pila-xs" style="[^"]*"/g) ?? [];
      const deCuadrilla = tarjetas.filter((t) => t.includes('min-width:0'));

      expect(deCuadrilla.length).toBe(1);
      expect(deCuadrilla[0]).toContain('justify-content:flex-start');
    });
  }
});
