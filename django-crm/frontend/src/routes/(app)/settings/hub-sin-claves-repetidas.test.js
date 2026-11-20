import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * NINGUNA TARJETA DEL HUB REPITE SU CLAVE  --  04/11/2026
 *
 * Configuración estuvo en blanco del 29/10 al 04/11: dos tarjetas con
 * `href: '/settings/bandeja'` en una lista identificada por `href`. Svelte 5
 * lanza `each_key_duplicate` y no dibuja NADA. `hub-se-dibuja-sin-esperar`
 * pasaba en verde porque `render` de `svelte/server` no valida claves; eso
 * solo lo hace el navegador. Esta guarda lee el componente, calcula la clave
 * de cada tarjeta como lo hace el `{#each}` (clave propia, si no el href) y
 * exige que no se repita dentro de un mismo grupo.
 *
 * Es texto y no render a propósito: un render de servidor es el instrumento
 * que ya demostró no medir esto.
 */
const fuente = readFileSync(fileURLToPath(new URL('./+page.svelte', import.meta.url)), 'utf-8');

/** Las tarjetas, en orden, con su grupo: lo que `{#each g.items as s}` recorre. */
function tarjetasPorGrupo() {
  /** @type {Record<string, string[]>} */
  const porGrupo = {};
  let grupo = '';
  const lineas = fuente.split('\n');
  let claveActual = null;
  let hrefActual = null;
  for (const linea of lineas) {
    const g = linea.match(/^\s*label:\s*'([^']+)'/);
    if (g) grupo = g[1];
    const c = linea.match(/^\s*clave:\s*'([^']+)'/);
    if (c) claveActual = c[1];
    const h = linea.match(/^\s*href:\s*'([^']+)'/);
    if (h) hrefActual = h[1];
    // Cada tarjeta cierra con `warn:`; ahí se consolida su clave.
    if (/^\s*warn:/.test(linea) && hrefActual) {
      (porGrupo[grupo] ??= []).push(claveActual ?? hrefActual);
      claveActual = null;
      hrefActual = null;
    }
  }
  return porGrupo;
}

describe('las tarjetas del hub de Configuración', () => {
  const porGrupo = tarjetasPorGrupo();

  it('hay tarjetas que vigilar (si esto da cero, cambió la forma y hay que revisar la guarda)', () => {
    expect(Object.values(porGrupo).flat().length).toBeGreaterThan(10);
  });

  it('EL EFECTO: dentro de un grupo ninguna clave se repite', () => {
    for (const [grupo, claves] of Object.entries(porGrupo)) {
      const repetidas = claves.filter((k, i) => claves.indexOf(k) !== i);
      expect(repetidas, `grupo «${grupo}»`).toEqual([]);
    }
  });

  it('el {#each} usa la clave propia antes que el href', () => {
    expect(fuente).toMatch(/\{#each g\.items as s \(s\.clave \?\? s\.href\)\}/);
  });
});
