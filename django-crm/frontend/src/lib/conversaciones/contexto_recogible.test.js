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

  it('los dos botones del panel son de solo ícono, y con nombre (10/11/2026)', () => {
    /* Sin texto a la vista, el nombre tiene que estar igual: un botón de
       solo ícono sin aria-label es mudo para un lector de pantalla, y sin
       title nadie sabe qué hace hasta apretarlo. */
    const boton = (fuente, clase) => {
      const i = fuente.indexOf(clase);
      return fuente.slice(fuente.lastIndexOf('<button', i), fuente.indexOf('</button>', i));
    };
    for (const [fuente, clase] of [[cabecera, 'contexto-toggle'], [pagina, 'info-cerrar']]) {
      const b = boton(fuente, clase);
      expect(b, clase).toMatch(/aria-label=/);
      expect(b, clase).toMatch(/title=/);
      // El contenido: lo que hay después del '>' que cierra la etiqueta de
      // apertura, que en los dos va solo en su renglón (el onclick lleva un
      // '=>', así que no se puede cortar en el primer '>').
      const contenido = b.split(/\n\s*>\s*\r?\n/)[1] ?? '';
      const texto = contenido.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, '')
        .replace(/\{[^}]*\}/g, '').trim();
      expect(texto, `${clase} no tiene texto visible`).toBe('');
    }
  });

  it('en ancha hay UN botón para recoger y expandir, no dos (10/11/2026)', () => {
    /* Estaban el de la cabecera y el del panel, haciendo lo mismo. El del
       panel queda solo en angosta, donde el panel es un cajón que tapa la
       cabecera y hace falta cerrarlo desde adentro. */
    const i = pagina.indexOf('class="v2-btn v2-btn-sm info-cerrar"');
    const antes = pagina.slice(Math.max(0, i - 200), i);
    expect(antes).toMatch(/\{#if !pantallaAncha\}\s*<button\s+type="button"\s*$/);
    // Y el de la cabecera alterna en ancha: recoge si está abierto, expande si no.
    expect(pagina).toMatch(/if \(pantallaAncha\) recogerContexto\(!contextoRecogido\);/);
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
