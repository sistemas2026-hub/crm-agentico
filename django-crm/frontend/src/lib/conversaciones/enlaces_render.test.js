/**
 * Los enlaces de salida de una conversación (12/11/2026, auditoría §2).
 *
 * Se afirma sobre lo DIBUJADO: el `href` que sale en la cabecera y en el panel
 * del caso, y que sin el dato no hay enlace. La cadena desde el motor —que
 * `ticket_operativo` viaje en la apertura— la mide
 * tests/test_apertura_conversacion.py.
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from 'svelte/server';

// CasePanel usa `enhance` para el formulario de asignar; acá solo se dibuja.
vi.mock('$app/forms', () => ({ enhance: () => ({ destroy() {} }) }));
import { enlacesDeSalida } from './enlaces.js';
import ConversationHeader from './conversation/ConversationHeader.svelte';
import CasePanel from './context/CasePanel.svelte';

const base = { id: 'c1', canal: 'whatsapp', usuario_externo: '573001112233', estado: 'abierta' };
const completa = { ...base, id_cliente: '77 12', ticket_operativo: '94553', rol_efectivo: 'soporte_tecnico_cliente' };

const html = (/** @type {any} */ C, /** @type {any} */ props) =>
  render(C, { props }).body.replace(/<!--[\s\S]*?-->/g, '');

describe('enlacesDeSalida', () => {
  it('cada enlace sale de su campo, codificado', () => {
    expect(enlacesDeSalida(completa)).toEqual({
      ficha: '/clientes/77%2012',
      ticketOperativo: '/tickets?search=94553&all=1',
      agente: '/agentes'
    });
  });
  it('sin el dato, sin enlace', () => {
    expect(enlacesDeSalida(base)).toEqual({ ficha: null, ticketOperativo: null, agente: null });
    expect(enlacesDeSalida({ ...base, id_cliente: '  ', ticket_operativo: null })).toMatchObject({ ficha: null, ticketOperativo: null });
    expect(enlacesDeSalida(null)).toEqual({ ficha: null, ticketOperativo: null, agente: null });
  });
});

describe('la cabecera', () => {
  it('con id_cliente y ticket: «Ver ficha completa» y el ticket enlazado', () => {
    const h = html(ConversationHeader, { conversacion: completa });
    expect(h).toMatch(/<a[^>]*href="\/clientes\/77%2012"[^>]*>Ver ficha completa<\/a>/);
    expect(h).toMatch(/<a[^>]*href="\/tickets\?search=94553&amp;all=1"/);
  });
  it('sin ellos, ninguno de los dos', () => {
    const h = html(ConversationHeader, { conversacion: base });
    expect(h).not.toMatch(/Ver ficha completa/);
    expect(h).not.toMatch(/\/tickets\?search=/);
  });
});

describe('el panel del caso', () => {
  it('el ticket operativo deja de ser un chip sin salida, y el agente lleva a /agentes', () => {
    const h = html(CasePanel, { caso: null, conversacion: completa, ownerActual: null });
    expect(h).toMatch(/<a[^>]*href="\/tickets\?search=94553&amp;all=1"[^>]*>\s*Buscar en Tickets/);
    expect(h).toMatch(/<a[^>]*href="\/agentes"[^>]*>\s*soporte_tecnico_cliente/);
  });
  it('sin agente ni ticket, ninguno', () => {
    const h = html(CasePanel, { caso: null, conversacion: base, ownerActual: null });
    expect(h).not.toMatch(/href="\/agentes"/);
    expect(h).not.toMatch(/Buscar en Tickets/);
  });
});
