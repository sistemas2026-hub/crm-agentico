/**
 * «Escalar a un área» se dibuja cuando corresponde (T22, 30/10/2026).
 *
 * Renderiza el componente de verdad. Nace de un error de esta misma sesión:
 * el botón quedó dentro del bloque de Tomar/Soltar, que no se dibuja con la
 * conversación ya ATENDIDA -- justo el caso de quien validó, respondió y no
 * pudo resolver. Las negativas importan tanto: la de otra persona no se
 * escala (eso es Reasignar), y con la IA atendiendo no hay nada que escalar.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import HandoffControls from './HandoffControls.svelte';

const BASE = /** @type {any} */ ({
  conversacion: { id: 'c1', estado: 'abierta', motivo_escalamiento: null },
  caso: null,
  operadores: [],
  iaEnPausa: true, escalada: true, atendida: false, esMia: true, asignadaA: 'Ana',
  esAdmin: false, gobernada: true,
  areas: { soporte_tecnico: 'Soporte Técnico' }
});
const hay = (props) =>
  /Escalar a un área/.test(render(HandoffControls, { props: { ...BASE, ...props } }).body);

describe('el botón «Escalar a un área»', () => {
  it('con la conversación mía: aparece', () => {
    expect(hay({})).toBe(true);
  });
  it('YA ATENDIDA (respondí y no pude resolver): también aparece', () => {
    expect(hay({ atendida: true })).toBe(true);
  });
  it('sin dueño: aparece', () => {
    expect(hay({ esMia: false, asignadaA: '' })).toBe(true);
  });
  it('de otra persona: no (eso es Reasignar, de administrador)', () => {
    expect(hay({ esMia: false, asignadaA: 'Luis' })).toBe(false);
  });
  it('cerrada, o sin escalar, o sin áreas: no', () => {
    expect(hay({ conversacion: { ...BASE.conversacion, estado: 'cerrada' } })).toBe(false);
    expect(hay({ escalada: false })).toBe(false);
    expect(hay({ areas: {} })).toBe(false);
  });
});

describe('a qué área se escaló', () => {
  it('se dice con la etiqueta de la empresa', () => {
    const { body } = render(HandoffControls, {
      props: { ...BASE, conversacion: { ...BASE.conversacion, area_destino: 'soporte_tecnico' } }
    });
    expect(body).toMatch(/Escalada a Soporte Técnico/);
  });
});
