import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import path from 'node:path';

/**
 * LAS FUENTES SE SIRVEN DESDE ACÁ, NO DESDE GOOGLE  --  12/11/2026
 *
 * Un tercero que no nombra la autorización de tratamiento (CLAUDE.md §5) se
 * enteraba de cada carga de página. Esta guarda impide que app.html vuelva a
 * pedirle algo, y que el CSS local apunte a un archivo que no está (una
 * @font-face rota no da error: la pantalla cae a otra letra en silencio).
 *
 * Al fusionar (12/11/2026) se quitaron también los <link> de las nueve
 * pantallas que traían el suyo (Bandeja, Inventario y el Supervisor NOC con
 * sus subpáginas), así que la guarda recorre TODO src/: una pantalla nueva
 * copiada de un diseño de Stitch trae su <link> a Google, y es así como volvía.
 */
const raiz = process.cwd();

/** Todos los archivos de src/ que puede servir la app, sin las pruebas. */
function archivosDeSrc(dir = path.join(raiz, 'src')) {
  /** @type {string[]} */
  const salida = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) salida.push(...archivosDeSrc(p));
    else if (/\.(svelte|js|html|css)$/.test(e.name) && !/\.test\.js$/.test(e.name)) salida.push(p);
  }
  return salida;
}
const appHtml = readFileSync(path.join(raiz, 'src/app.html'), 'utf-8');
const css = readFileSync(path.join(raiz, 'static/fuentes/fuentes.css'), 'utf-8');

describe('fuentes autoalojadas', () => {
  it('app.html no le pide nada a Google y carga el CSS local', () => {
    expect(appHtml).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    expect(appHtml).toContain('/fuentes/fuentes.css');
  });

  it('ninguna pantalla le pide fuentes a Google', () => {
    const conGoogle = archivosDeSrc()
      .filter((p) => /<link[^>]+fonts\.(googleapis|gstatic)\.com/.test(readFileSync(p, 'utf-8')))
      .map((p) => path.relative(raiz, p));
    expect(conGoogle).toEqual([]);
    // Recorre TODO src/: por un volumen de Docker en Windows tarda ~10 s, y
    // los 5 s por defecto la daban por fallida sin haber encontrado nada.
  }, 60_000);

  it('cada url() del CSS es un archivo que existe en static/fuentes', () => {
    const urls = [...css.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1]);
    expect(urls.length).toBeGreaterThan(10);
    for (const u of urls) {
      expect(u.startsWith('/fuentes/')).toBe(true);
      expect(existsSync(path.join(raiz, 'static', u))).toBe(true);
    }
  });

  it('declara las familias que usan las pantallas', () => {
    for (const familia of [
      'Inter',
      'JetBrains Mono',
      'Geist',
      'Atkinson Hyperlegible Next',
      'Barlow Semi Condensed',
      'Hanken Grotesk',
      'Material Symbols Outlined'
    ]) {
      expect(css).toContain(`font-family: '${familia}'`);
    }
  });

  it('viaja con sus licencias', () => {
    for (const f of ['OFL-inter.txt', 'OFL-jetbrainsmono.txt', 'LICENSE-material-symbols.txt']) {
      expect(existsSync(path.join(raiz, 'static/fuentes/licencias', f))).toBe(true);
    }
  });
});
