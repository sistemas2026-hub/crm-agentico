/**
 * El botón de enviar, dibujado de verdad en los tres estados (11/11/2026).
 *
 * Nace de una captura: «Enviar» en marino con halo, solo en el pie, y vivo a
 * la vista con la IA atendiendo -- donde no manda nada y la acción real es
 * «Intervenir». Y con la ventana cerrada, «Elegir plantilla» en el pie
 * repetía a «Plantillas» de la barra, justo arriba.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import MessageComposer from './MessageComposer.svelte';

const dibujar = (/** @type {any} */ props) =>
  render(MessageComposer, {
    props: { conversacion: { canal: 'whatsapp' }, modo: 'responder', entrada: '', ...props }
  }).body.replace(/<!--[\s\S]*?-->/g, '');

/** Los botones, con su texto plano. */
const botones = (/** @type {string} */ html) =>
  [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].map(([, attrs, dentro]) => ({
    attrs,
    texto: dentro.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
  }));

describe('el botón de enviar', () => {
  it('escalada y con la ventana abierta: «Enviar» al lado del cuadro, no en el pie', () => {
    const html = dibujar({ escalada: true });
    const caja = html.slice(html.indexOf('class="escribir'), html.indexOf('compositor-pie'));
    expect(caja).toMatch(/<textarea/);
    expect(botones(caja).map((b) => b.texto)).toContain('Enviar');
    const pie = html.slice(html.indexOf('compositor-pie'));
    expect(botones(pie)).toHaveLength(0);
  });

  it('con la IA atendiendo no hay «Enviar»: la acción es «Intervenir»', () => {
    const textos = botones(dibujar({ bloqueadoPorIA: true })).map((b) => b.texto);
    expect(textos).not.toContain('Enviar');
    expect(textos).toContain('Intervenir');
  });

  it('con la ventana cerrada hay UN botón de plantillas, y es la acción', () => {
    const html = dibujar({ escalada: true, bloqueadoPorVentana: true });
    const deplantilla = botones(html).filter((b) => /plantilla/i.test(b.texto));
    expect(deplantilla.map((b) => b.texto)).toEqual(['Elegir plantilla']);
    expect(deplantilla[0].attrs).toMatch(/barra-boton-accion/);
    expect(botones(html).map((b) => b.texto)).not.toContain('Enviar');
  });

  it('con la ventana abierta el de la barra es el discreto «Plantillas»', () => {
    const deplantilla = botones(dibujar({ escalada: true })).filter((b) => /plantilla/i.test(b.texto));
    expect(deplantilla.map((b) => b.texto)).toEqual(['Plantillas']);
    expect(deplantilla[0].attrs).not.toMatch(/barra-boton-accion/);
  });
});
