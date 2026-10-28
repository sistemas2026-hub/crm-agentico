import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { PESTANAS_NOC } from './pestanas.js';

/**
 * LAS PESTAÑAS DE SUPERVISOR NOC SON UNA SOLA LISTA (28/10/2026).
 *
 * Estaban copiadas a mano en cada pantalla y se habían desordenado: unas tenían
 * «Ajustes», otras no tenían «Plantillas». Esta guarda mira el EFECTO: que
 * cada pantalla use el componente y que ninguna vuelva a escribir las suyas.
 */
const RUTA = 'src/routes/(app)/supervisor-noc';
const PANTALLAS = [
  '+page.svelte',
  'cuadrillas/+page.svelte',
  'despacho/+page.svelte',
  'programacion/+page.svelte',
  'planes-semanales/+page.svelte',
  'plantillas/+page.svelte',
  'ajustes/+page.svelte'
];

describe('las pestañas de Supervisor NOC', () => {
  it('Programación va después de Despacho, y están todas', () => {
    expect(PESTANAS_NOC.map((p) => p.id)).toEqual([
      'pendientes',
      'cuadrillas',
      'despacho',
      'programacion',
      'plantillas',
      'ajustes'
    ]);
  });

  for (const archivo of PANTALLAS) {
    it(`${archivo} usa el componente y no escribe las suyas`, () => {
      const fuente = readFileSync(`${RUTA}/${archivo}`, 'utf8');
      expect(fuente).toMatch(/<PestanasNoc activa="[a-z]+" \/>/);
      //  Una pestaña escrita a mano es una píldora con la ruta Y el texto de una
      //  pestaña. «Ver programación» desde un bloque, o un enlace dentro de una
      //  frase, no lo son.
      for (const p of PESTANAS_NOC) {
        const a_mano = new RegExp(`snoc-pildora[^"]*" href="${p.href}">\\s*${p.texto}\\s*<`);
        expect(fuente).not.toMatch(a_mano);
      }
    });
  }
});
