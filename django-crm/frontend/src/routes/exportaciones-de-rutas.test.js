import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

/**
 * Un archivo de ruta solo puede exportar lo que SvelteKit reconoce (13/11/2026).
 *
 * `export const MOTIVO_MAXIMO = 500` en un `+server.js` pasaba vitest y
 * svelte-check, y rompio `pnpm build` en el despliegue: «Invalid export
 * 'MOTIVO_MAXIMO' ... valid exports are GET, POST, ...». Ninguna prueba corre
 * el build, asi que el primero en verlo fue Dokploy. Lo que no es de SvelteKit
 * va con prefijo `_` (lo acepta) o en un modulo de `$lib`.
 */
const PERMITIDOS = {
  '+server.js': ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS', 'HEAD', 'fallback',
    'prerender', 'trailingSlash', 'config', 'entries'],
  '+page.server.js': ['load', 'actions', 'prerender', 'csr', 'ssr', 'trailingSlash', 'config', 'entries'],
  '+layout.server.js': ['load', 'prerender', 'csr', 'ssr', 'trailingSlash', 'config', 'entries'],
  '+page.js': ['load', 'prerender', 'csr', 'ssr', 'trailingSlash', 'config', 'entries'],
  '+layout.js': ['load', 'prerender', 'csr', 'ssr', 'trailingSlash', 'config', 'entries']
};

/** @param {string} dir @returns {string[]} */
function archivosDeRuta(dir) {
  /** @type {string[]} */
  const salida = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) salida.push(...archivosDeRuta(p));
    else if (e.name in PERMITIDOS) salida.push(p);
  }
  return salida;
}

/** Los nombres que exporta un archivo, leidos del texto. @param {string} texto */
export function _exportados(texto) {
  const nombres = [];
  for (const m of texto.matchAll(
    /^export\s+(?:async\s+)?(?:const|let|var|function\*?|class)\s+([A-Za-z_$][\w$]*)|^export\s*\{([^}]*)\}/gm
  )) {
    if (m[1]) nombres.push(m[1]);
    else
      for (const parte of m[2].split(',')) {
        const n = parte.split(/\s+as\s+/).pop()?.trim();
        if (n) nombres.push(n);
      }
  }
  return nombres;
}

describe('las rutas solo exportan lo que SvelteKit acepta', () => {
  it('lee las formas de export que se usan', () => {
    expect(_exportados('export const A = 1;\nexport async function GET() {}\nexport { b as C, D };'))
      .toEqual(['A', 'GET', 'C', 'D']);
  });

  it('ningun archivo de ruta exporta un nombre que rompa el build', () => {
    const raiz = process.cwd();
    const malos = archivosDeRuta(path.join(raiz, 'src', 'routes')).flatMap((p) => {
      const validos = PERMITIDOS[/** @type {keyof typeof PERMITIDOS} */ (path.basename(p))];
      return _exportados(readFileSync(p, 'utf-8'))
        .filter((n) => !validos.includes(n) && !n.startsWith('_'))
        .map((n) => `${path.relative(raiz, p)}: ${n}`);
    });
    expect(malos).toEqual([]);
  }, 60_000);
});
