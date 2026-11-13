/**
 * La cabecera de la conversación, dibujada (11/11/2026): «Marcar como no
 * leída» y las etiquetas del equipo del chat.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import ConversationHeader from './ConversationHeader.svelte';
import { ofreceMarcarNoLeida } from '../lectura.js';
import CatalogoDeEtiquetas from '../etiquetas/CatalogoDeEtiquetas.svelte';

const catalogo = [
  { clave: 'vip', nombre: 'Cliente VIP', color: 'violeta' },
  { clave: 'moroso', nombre: 'Moroso', color: 'rojo' }
];
const conversacion = { id: 'c1', canal: 'whatsapp', usuario_externo: '573001112233', estado: 'abierta' };

/** @param {any} props */
const dibujar = (props) =>
  render(ConversationHeader, { props: { conversacion, ...props } }).body.replace(/<!--[\s\S]*?-->/g, '');
const texto = (/** @type {string} */ html) => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

describe('marcar como no leída', () => {
  it('con la acción, hay un botón con su nombre para el lector', () => {
    const html = dibujar({ onMarcarNoLeida: () => {} });
    expect(html).toMatch(/<button[^>]*aria-label="Marcar como no leída"/);
  });

  it('sin la acción no se dibuja', () => {
    expect(dibujar({})).not.toMatch(/Marcar como no leída/);
  });

  /* H5 (11/11/2026): la pantalla pasa la acción solo donde el contador se va
     a ver -- `onMarcarNoLeida={ofreceNoLeida ? marcarNoLeida : undefined}` en
     routes/(app)/conversaciones/[id]/+page.svelte --. */
  /** @param {any[]} cola */
  const comoLaPantalla = (cola) =>
    dibujar({ onMarcarNoLeida: ofreceMarcarNoLeida(cola, conversacion) ? () => {} : undefined });

  it('un chat que lleva la IA no ofrece «Marcar como no leída»', () => {
    expect(comoLaPantalla([{ ...conversacion, no_leidos: 2 }])).not.toMatch(/Marcar como no leída/);
  });

  it('uno pedido para una persona, o en atención, sí', () => {
    expect(comoLaPantalla([{ ...conversacion, escalada_a_humano: true }])).toMatch(/aria-label="Marcar como no leída"/);
    expect(comoLaPantalla([{ ...conversacion, tomada_por: 'Ana' }])).toMatch(/aria-label="Marcar como no leída"/);
  });

  it('si no se pudo, lo dice', () => {
    const t = texto(dibujar({ onMarcarNoLeida: () => {}, avisoLectura: 'Este chat no tiene mensajes del cliente' }));
    expect(t).toMatch(/no tiene mensajes del cliente/);
  });
});

describe('las etiquetas del chat en la cabecera', () => {
  it('las del chat como chips, y el botón para cambiarlas', () => {
    const html = dibujar({ catalogoEtiquetas: catalogo, etiquetasAsignadas: ['moroso'] });
    const t = texto(html);
    expect(t).toMatch(/Moroso/);
    expect(t).not.toMatch(/Cliente VIP/);
    expect(html).toMatch(/<button[^>]*aria-expanded="false"[^>]*>[\s\S]*?Etiquetas/);
  });

  it('sin ninguna puesta, el botón invita a etiquetar', () => {
    expect(texto(dibujar({ catalogoEtiquetas: catalogo, etiquetasAsignadas: [] }))).toMatch(/Etiquetar/);
  });

  it('sin catálogo de la empresa no se ofrece nada', () => {
    const t = texto(dibujar({ catalogoEtiquetas: [], etiquetasAsignadas: ['vip'] }));
    expect(t).not.toMatch(/Etiquetar|Etiquetas/);
  });

  it('el motivo de un rechazo se ve', () => {
    const t = texto(dibujar({ catalogoEtiquetas: catalogo, errorEtiquetas: 'Esas etiquetas no existen' }));
    expect(t).toMatch(/Esas etiquetas no existen/);
  });
});

describe('el catálogo en /settings/bandeja', () => {
  /** @param {any} props */
  const catalogoHtml = (props) => render(CatalogoDeEtiquetas, { props }).body.replace(/<!--[\s\S]*?-->/g, '');

  it('muestra las de la empresa, y «Editar» solo a quien puede', () => {
    const html = catalogoHtml({ catalogo, puedeEditar: true });
    expect(texto(html)).toMatch(/Cliente VIP\s+Moroso/);
    expect(texto(html)).toMatch(/Editar etiquetas/);
    expect(texto(catalogoHtml({ catalogo, puedeEditar: false }))).not.toMatch(/Editar etiquetas/);
  });

  it('sin ninguna, dice que la Bandeja no ofrece etiquetar', () => {
    expect(texto(catalogoHtml({ catalogo: [] }))).toMatch(/no ofrece etiquetar/);
  });

  it('el error del motor se ve', () => {
    expect(texto(catalogoHtml({ catalogo, error: "'#f0a' no es uno de los colores" }))).toMatch(/colores/);
  });
});
