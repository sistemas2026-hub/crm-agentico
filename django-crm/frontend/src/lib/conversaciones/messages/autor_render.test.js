/**
 * Quien aparece sobre cada burbuja, dibujado de verdad.
 *
 * Nace de una duda concreta (22/09/2026): en produccion dos mensajes del
 * cliente salieron rotulados «ORIGEN NO REGISTRADO». Medido contra la base,
 * las dos filas tenian `origen = 'cliente'`, y el motor devuelve esa columna.
 * Asi que o el componente se equivoca, o al navegador le llego otra cosa.
 * Esto contesta la primera mitad: con la forma exacta que manda el motor,
 * que dibuja.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import MessageThread from './MessageThread.svelte';

const hilo = (m) => [{ tipo: 'msg', clave: '1', m: { adjuntos: [], ...m } }];

const dibuja = (m, nombreCliente = 'Mario QA') =>
  render(MessageThread, {
    props: { hilo: hilo(m), cantidadMensajes: 1, conversacionId: 'x', nombreCliente, casos: [] }
  }).body;

describe('el rotulo de autor sale de lo durable', () => {
  it('cliente con origen: su nombre, sin ficha', () => {
    const html = dibuja({ id: '1', rol: 'user', origen: 'cliente', contenido: 'hola',
                          creado_en: '2026-09-22T19:52:00Z' });
    expect(html).toMatch(/Mario QA/);
    expect(html, 'el cliente no lleva ficha: su burbuja ya esta del otro lado')
      .not.toMatch(/Origen no registrado/i);
  });

  it('sin nombre de cliente, dice «Cliente» y no inventa uno', () => {
    const html = dibuja({ id: '1', rol: 'user', origen: 'cliente', contenido: 'hola',
                          creado_en: '2026-09-22T19:52:00Z' }, '');
    expect(html).toMatch(/Cliente/);
    expect(html).not.toMatch(/Origen no registrado/i);
  });

  it('SIN origen: lo dice, y no lo deduce del rol', () => {
    /* Es la guarda de D30: un `user` historico sin origen no puede salir
       afirmado como Cliente. */
    const html = dibuja({ id: '1', rol: 'user', origen: null, contenido: 'hola',
                          creado_en: '2026-09-22T19:52:00Z' });
    expect(html).toMatch(/Origen no registrado/i);
  });

  it('la IA y la persona no se confunden', () => {
    const ia = dibuja({ id: '1', rol: 'assistant', origen: 'ia', contenido: 'x',
                        creado_en: '2026-09-22T19:52:00Z' });
    expect(ia).toMatch(/Dexter IA/);
    const humano = dibuja({ id: '1', rol: 'assistant', origen: 'humano',
                            autor_nombre: 'Ana QA', contenido: 'x',
                            creado_en: '2026-09-22T19:52:00Z' });
    expect(humano).toMatch(/Ana QA/);
    expect(humano).not.toMatch(/Dexter IA/);
  });
});

describe('el estado de entrega se dibuja como palomitas', () => {
  const pie = (estado) =>
    render(MessageThread, {
      props: {
        hilo: hilo({ id: '1', rol: 'assistant', origen: 'ia', contenido: 'x',
                     creado_en: '2026-09-22T19:52:00Z', estado_entrega: estado }),
        cantidadMensajes: 1, conversacionId: 'x', nombreCliente: '', casos: []
      }
    }).body;

  it('cada estado lleva su palabra, aunque se vea un tilde', () => {
    /* El color no puede ser la unica señal: entregado y leido son las mismas
       dos palomitas y solo los separa el azul. La palabra sigue estando en
       `title` y `aria-label` -- si se va, esta prueba se pone roja. */
    for (const [estado, palabra] of [
      ['pendiente', 'Enviando'],
      ['enviado', 'Enviado'],
      ['entregado', 'Entregado'],
      ['leido', 'Leído']
    ]) {
      const html = pie(estado);
      expect(html, estado).toMatch(/class="[^"]*palomita/);
      expect(html, estado).toMatch(new RegExp(`aria-label="${palabra}`));
    }
  });

  it('«descartado» sigue siendo texto: no es un grado de entrega', () => {
    /* D24: la IA la calculo y una persona tomo el control antes de que
       saliera. Un tilde diria que algo se mando, y no se mando nada. */
    const html = pie('descartado');
    expect(html).not.toMatch(/class="[^"]*palomita/);
    expect(html).toMatch(/una persona tomó el control/i);
  });

  it('sin estado no se dibuja nada: NULL es «no se sabe»', () => {
    const html = pie(null);
    expect(html).not.toMatch(/class="[^"]*palomita/);
  });
});
