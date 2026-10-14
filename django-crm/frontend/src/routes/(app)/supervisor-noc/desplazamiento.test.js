/**
 * Toda pantalla del Supervisor NOC se puede desplazar.
 *
 * El marco de (app) es `overflow:hidden` y el único contenedor que se desplaza
 * es `.v2-scroll`. Una pantalla sin él se ve entera mientras el contenido
 * quepa en la ventana; cuando no cabe, lo de abajo queda recortado y no hay
 * forma de llegar. No da error ni aviso.
 *
 * Ya pasó tres veces por la misma razón: settings/guias-tv (10/09/2026), la
 * pantalla principal del Supervisor, y el 13/10/2026 Despacho, Plantillas,
 * Cuadrillas y Programación a la vez. Por eso esto recorre TODAS las pantallas
 * de la carpeta y no una lista: la que falta es siempre la nueva.
 */
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = dirname(fileURLToPath(import.meta.url));

/** @param {string} dir @returns {string[]} */
function pantallas(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return pantallas(p);
    return n === '+page.svelte' ? [p] : [];
  });
}

describe('las pantallas del Supervisor NOC', () => {
  const todas = pantallas(raiz);

  it('se encontraron (si da cero, la prueba no está mirando nada)', () => {
    expect(todas.length).toBeGreaterThanOrEqual(5);
  });

  for (const p of todas) {
    it(`${relative(raiz, p) || '+page.svelte'} tiene el contenedor que se desplaza`, () => {
      expect(readFileSync(p, 'utf-8')).toMatch(/class="v2-scroll"/);
    });
  }
});
