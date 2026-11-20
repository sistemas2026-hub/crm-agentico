/**
 * La línea de estado y el resumen, dibujados de verdad (04/11/2026).
 *
 * Nace del rediseño que juntó cinco indicadores en una sola línea: una
 * conversación cerrada decía a la vez «cerrada», «Sin asignar», «IA no
 * responde», el motivo y «Resuelta» en verde. Afirma sobre lo que SALE --no
 * sobre que el mecanismo exista--, en las combinaciones donde se separaban.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import HandoffControls from './HandoffControls.svelte';
import EscalationSummary from './EscalationSummary.svelte';

const BASE = /** @type {any} */ ({
  conversacion: { id: 'c1', estado: 'abierta', motivo_escalamiento: 'falla_servicio' },
  caso: { id: 'k1' },
  operadores: [],
  iaEnPausa: true, escalada: true, atendida: false, esMia: false, asignadaA: '',
  esAdmin: false, gobernada: true,
  areas: {}
});
const texto = (props) =>
  render(HandoffControls, { props: { ...BASE, ...props } }).body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

describe('la conversación cerrada dice una sola cosa', () => {
  const cerrada = { conversacion: { ...BASE.conversacion, estado: 'cerrada', atendida_por: 'Admin' } };

  it('la línea de estado, con quién la resolvió y qué pasa si se escribe', () => {
    const t = texto(cerrada);
    expect(t).toMatch(/Cerrada · la resolvió Admin/);
    expect(t).toMatch(/abre una conversación nueva/);
  });

  it('y nada de lo que contaba una conversación viva', () => {
    const t = texto(cerrada);
    expect(t).not.toMatch(/Caso abierto en CRM/);
    expect(t).not.toMatch(/Resuelta/);
    expect(t).not.toMatch(/IA no responde/);
    expect(t, 'el motivo es historia').not.toMatch(/falla/i);
    expect(t).not.toMatch(/Tomar|Soltar|Resuelto/);
  });

  it('la página manda la línea ya elegida, y esa gana', () => {
    const t = texto({
      ...cerrada,
      estadoUnico: { clave: 'cerrada', tono: 'neutro', texto: 'Cerrada · la resolvió Ana el 31/10 a las 13:43', detalle: 'x' }
    });
    expect(t).toMatch(/la resolvió Ana el 31\/10/);
  });
});

describe('la conversación abierta conserva sus gestos', () => {
  it('sin dueño: la alerta, el motivo, el caso, Tomar y Resuelto', () => {
    const html = render(HandoffControls, { props: BASE }).body;
    const t = texto({});
    expect(html).toMatch(/aviso-estado-alerta/);
    expect(t).toMatch(/Espera a una persona · la IA no responde/);
    expect(t).toMatch(/Caso abierto en CRM/);
    expect(t).toMatch(/Tomar/);
    expect(t).toMatch(/Resuelto/);
  });

  it('mía: azul de persona, y «Asignada a mí» se dice una sola vez', () => {
    const html = render(HandoffControls, { props: { ...BASE, esMia: true, asignadaA: 'Yo' } }).body;
    expect(html).toMatch(/aviso-estado-humano/);
    expect(texto({ esMia: true, asignadaA: 'Yo' }).match(/Asignada a mí/g)).toHaveLength(1);
    expect(texto({ esMia: true, asignadaA: 'Yo' })).toMatch(/Soltar/);
  });

  it('con la IA atendiendo ya no dice «Escalada»: nadie la escaló', () => {
    const t = texto({ iaEnPausa: false, escalada: false });
    expect(t).toMatch(/La atiende la IA/);
    expect(t).not.toMatch(/Escalada/);
  });
});

describe('«Por qué llegó acá»', () => {
  const filas = (cita) => [
    { rotulo: cita ? 'Primer mensaje del cliente' : 'Qué quiere', orden: 0,
      texto: cita ? 'Hola' : 'Que le revisen la fibra', cita, vacio: '' }
  ];
  const dibuja = (props) => render(EscalationSummary, { props: { hizoLaIA: [], ...props } }).body;

  it('un saludo citado no se presenta como el pedido', () => {
    const html = dibuja({ resumenEscalada: filas(true) });
    expect(html).toMatch(/Primer mensaje del cliente/);
    expect(html).not.toMatch(/Qué quiere/);
  });

  it('con resumen del modelo, el rótulo es el de siempre', () => {
    const html = dibuja({ resumenEscalada: filas(false) });
    expect(html).toMatch(/Por qué llegó acá/);
    expect(html).toMatch(/Qué quiere/);
  });

  it('el rojo solo si espera a una persona sin dueño', () => {
    expect(dibuja({ resumenEscalada: filas(false) })).not.toMatch(/brief-rotulo-urgente/);
    expect(dibuja({ resumenEscalada: filas(false), urgente: true })).toMatch(/brief-rotulo-urgente/);
  });
});
