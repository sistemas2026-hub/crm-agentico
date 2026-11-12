import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';

/**
 * LAS FUENTES SE SIRVEN DESDE ACÁ, NO DESDE GOOGLE  --  12/11/2026
 *
 * Un tercero que no nombra la autorización de tratamiento (CLAUDE.md §5) se
 * enteraba de cada carga de página. Esta guarda impide que app.html vuelva a
 * pedirle algo, y que el CSS local apunte a un archivo que no está (una
 * @font-face rota no da error: la pantalla cae a otra letra en silencio).
 *
 * Mira solo app.html y static/: las pantallas que todavía traen su <link> a
 * Google son de otros dueños y se cambian al fusionar (informe del agente I).
 */
const raiz = process.cwd();
const appHtml = readFileSync(path.join(raiz, 'src/app.html'), 'utf-8');
const css = readFileSync(path.join(raiz, 'static/fuentes/fuentes.css'), 'utf-8');

describe('fuentes autoalojadas', () => {
  it('app.html no le pide nada a Google y carga el CSS local', () => {
    expect(appHtml).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    expect(appHtml).toContain('/fuentes/fuentes.css');
  });

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
