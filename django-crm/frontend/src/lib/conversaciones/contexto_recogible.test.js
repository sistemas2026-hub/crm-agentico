/**
 * La columna de contexto se recoge también en pantalla ancha (29/10/2026).
 *
 * Test de texto, por lo mismo que t6_cableado.test.js: el harness no compila
 * la página. Lo que protege son las tres piezas que, si una falta, dejan el
 * pedido a medias sin que nada falle: el botón de la cabecera escondido en
 * ancha (no hay cómo desplegarla), la clase sin su regla (no se recoge), o la
 * preferencia sin try/catch (en modo privado rompe la página).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
const pagina = leer('../../routes/(app)/conversaciones/[id]/+page.svelte');
const cabecera = leer('./conversation/ConversationHeader.svelte');

describe('la columna de contexto en pantalla ancha', () => {
  it('el botón «Contexto» de la cabecera ya no se esconde en ancha', () => {
    const regla = cabecera.slice(cabecera.indexOf('.contexto-toggle {'));
    expect(regla.slice(0, 80)).not.toMatch(/display:\s*none/);
  });

  it('la columna lleva la clase y la regla que la recoge', () => {
    expect(pagina).toMatch(/class:recogida=\{contextoRecogido\}/);
    expect(pagina).toMatch(/@media \(min-width: 1241px\)\s*\{\s*\.info\.recogida\s*\{\s*display:\s*none/);
  });

  it('la preferencia se lee y se escribe dentro de try', () => {
    for (const uso of ['localStorage.getItem(CLAVE_RECOGIDO)', 'localStorage.setItem(CLAVE_RECOGIDO']) {
      const i = pagina.indexOf(uso);
      expect(i, uso).toBeGreaterThan(0);
      expect(pagina.slice(Math.max(0, i - 40), i)).toMatch(/try \{/);
    }
  });
});
