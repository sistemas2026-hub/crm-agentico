/**
 * La fila y los filtros de la cola, dibujados de verdad (11/11/2026): no
 * leídos como WhatsApp Business y etiquetas del equipo.
 *
 * Se afirma sobre lo que SALE en el HTML: el contador con su frase para el
 * lector de pantalla, el nombre en negrita solo con algo sin leer, dos chips y
 * «+N», y que una etiqueta que no está en el catálogo no se dibuja.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import ConversationRow from './ConversationRow.svelte';
import QueueFilters from './QueueFilters.svelte';

const catalogo = [
  { clave: 'vip', nombre: 'Cliente VIP', color: 'violeta' },
  { clave: 'moroso', nombre: 'Moroso', color: 'rojo' },
  { clave: 'visita', nombre: 'Pide visita', color: 'azul' }
];

const sinComentarios = (/** @type {string} */ html) => html.replace(/<!--[\s\S]*?-->/g, '');
const texto = (/** @type {string} */ html) =>
  sinComentarios(html).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

/** @param {any} c @param {any} [extra] */
const fila = (c, extra = {}) =>
  sinComentarios(
    render(ConversationRow, {
      props: {
        c: { id: 'c1', canal: 'whatsapp', usuario_externo: '573001112233', estado: 'abierta',
          nombre_cliente: 'Ana Pérez', actualizado_en: new Date().toISOString(), ...c },
        ahora: Date.now(),
        tramoEspera: () => 'reciente',
        motivoLabel: (/** @type {string} */ m) => m,
        etiquetas: catalogo,
        ...extra
      }
    }).body
  );

/* Desde el 11/11/2026 (H5) el contador y la negrita se ven solo con una
   persona en el caso: pedida o en atención. Las filas de abajo están pedidas. */
const PEDIDA = { escalada_a_humano: true };

describe('no leídos en la fila', () => {
  it('con mensajes sin leer: el número, la frase para el lector y el nombre en negrita', () => {
    const html = fila({ ...PEDIDA, no_leidos: 3 });
    expect(html).toMatch(/class="no-leidos[^"]*"/);
    expect(texto(html)).toMatch(/3 sin leer/);
    expect(html).toMatch(/class="quien[^"]*sin-leer/);
  });

  it('sin nada sin leer: ni contador ni negrita', () => {
    const html = fila({ ...PEDIDA, no_leidos: 0 });
    expect(html).not.toMatch(/no-leidos/);
    expect(html).not.toMatch(/sin-leer/);
  });

  it('más de 99 se escribe «99+»: el contador no ensancha la fila', () => {
    expect(texto(fila({ ...PEDIDA, no_leidos: 140 }))).toMatch(/99\+/);
  });

  it('en atención (tomada por alguien) también se ven', () => {
    const html = fila({ tomada_por: 'Ana', no_leidos: 2 });
    expect(texto(html)).toMatch(/2 sin leer/);
    expect(html).toMatch(/class="quien[^"]*sin-leer/);
  });

  it('EL EFECTO (H5): una fila que lleva la IA no tiene contador ni negrita, aunque el motor cuente 3', () => {
    const html = fila({ no_leidos: 3 });
    expect(html).not.toMatch(/no-leidos/);
    expect(html).not.toMatch(/sin-leer/);
    expect(texto(html)).not.toMatch(/sin leer/);
  });
});

describe('etiquetas del equipo en la fila', () => {
  it('dos chips con su nombre, en el orden del catálogo, y «+1» con el resto', () => {
    const t = texto(fila({ etiquetas_del_equipo: ['visita', 'moroso', 'vip'] }));
    expect(t).toMatch(/Cliente VIP\s+Moroso\s+\+1/);
    expect(t).not.toMatch(/Pide visita/);
  });

  it('una clave que no está en el catálogo no se dibuja', () => {
    const t = texto(fila({ etiquetas_del_equipo: ['borrada', 'vip'] }));
    expect(t).toMatch(/Cliente VIP/);
    expect(t).not.toMatch(/borrada/);
  });

  it('el color sale de la paleta, no del dato', () => {
    const html = fila({ etiquetas_del_equipo: ['vip'] });
    expect(html).toMatch(/--etq-texto:#6d28d9/);
  });

  it('sin catálogo, ninguna', () => {
    expect(texto(fila({ etiquetas_del_equipo: ['vip'] }, { etiquetas: [] }))).not.toMatch(/Cliente VIP/);
  });
});

describe('los filtros', () => {
  /** @param {any} props */
  const filtros = (props) =>
    sinComentarios(
      render(QueueFilters, {
        props: { motivos: [], motivoLabel: (/** @type {string} */ m) => m, ORDENES: [], ...props }
      }).body
    );

  it('«No leídas» está siempre, con cuántos chats, aunque no haya motivos', () => {
    const html = filtros({ nNoLeidas: 4 });
    expect(texto(html)).toMatch(/No leídas 4/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>\s*No leídas/);
  });

  it('puesto, se marca', () => {
    expect(filtros({ soloNoLeidas: true, nNoLeidas: 2 })).toMatch(/aria-pressed="true"[^>]*>\s*No leídas/);
  });

  it('cada etiqueta con su cifra, y la elegida marcada', () => {
    const html = filtros({
      etiquetasCola: [[catalogo[0], 3], [catalogo[1], 1]],
      etiqueta: 'moroso'
    });
    const t = texto(html);
    expect(t).toMatch(/Cliente VIP 3/);
    expect(t).toMatch(/Moroso 1/);
    expect(html).toMatch(/aria-pressed="true"[^>]*>[\s\S]*?Moroso/);
  });

  it('los motivos siguen en su grupo, separados', () => {
    const html = filtros({ motivos: [['queja', 2], ['tecnico', 1]] });
    expect(html).toMatch(/aria-label="Filtrar por motivo de escalada"/);
    expect(html).toMatch(/class="separador/);
  });
});
