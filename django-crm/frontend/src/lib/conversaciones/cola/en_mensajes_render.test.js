/**
 * «En mensajes», dibujado (11/11/2026): debajo de la cola, cada mensaje que
 * contiene lo buscado, con la coincidencia resaltada partiendo el texto -- el
 * fragmento es de un cliente y NUNCA entra como HTML. Y los tres estados
 * (buscando, sin resultados, error) se dicen sin tapar la cola.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import MessageSearchResults from './MessageSearchResults.svelte';
import ConversationList from './ConversationList.svelte';

const RES = [
  {
    mensaje_id: 'm1',
    conversation_id: 'c1',
    rol: 'user',
    es_nota: false,
    creado_en: '2026-11-01T15:00:00Z',
    fragmento: 'el <b>POSTE</b> caído frente a mi casa',
    nombre_cliente: 'Ana Pérez',
    usuario_externo: '573001',
    estado: 'abierta'
  },
  {
    mensaje_id: 'm2',
    conversation_id: 'c2',
    rol: 'nota',
    es_nota: true,
    creado_en: '2026-11-01T14:00:00Z',
    fragmento: 'revisar el poste de la calle 8',
    nombre_cliente: null,
    usuario_externo: '573002',
    estado: 'cerrada'
  }
];

const busqueda = (/** @type {any} */ extra) => ({
  estado: 'listo',
  q: 'poste',
  resultados: RES,
  tope: 30,
  error: '',
  ...extra
});

const dibujar = (/** @type {any} */ props) =>
  render(MessageSearchResults, { props }).body.replace(/<!--[\s\S]*?-->/g, '');

describe('En mensajes', () => {
  it('cada resultado abre su conversación y resalta lo buscado con <mark>', () => {
    const html = dibujar({ busqueda: busqueda(), resultados: RES });
    expect(html).toMatch(/En mensajes/);
    expect(html).toContain('href="/conversaciones/c1"');
    expect(html).toContain('href="/conversaciones/c2"');
    expect(html).toMatch(/<mark[^>]*>POSTE<\/mark>/);
    expect(html).toMatch(/<mark[^>]*>poste<\/mark>/);
  });

  it('EL EFECTO: el marcado que escribió el cliente sale escapado, no como HTML', () => {
    const html = dibujar({ busqueda: busqueda(), resultados: RES });
    expect(html).not.toContain('<b>');
    expect(html).toContain('&lt;b>');
  });

  it('dice de quién es, y marca la nota interna y la conversación cerrada', () => {
    const html = dibujar({ busqueda: busqueda(), resultados: RES });
    expect(html).toContain('Ana Pérez');
    expect(html).toMatch(/Nota interna/);
    expect(html).toMatch(/Cerrada/);
  });

  it('buscando, sin resultados y error son tres textos distintos', () => {
    expect(dibujar({ busqueda: busqueda({ estado: 'buscando', resultados: [] }), resultados: [] })).toMatch(
      /Buscando «poste» en los mensajes/
    );
    expect(dibujar({ busqueda: busqueda({ resultados: [] }), resultados: [] })).toMatch(
      /Ningún mensaje contiene «poste»/
    );
    expect(
      dibujar({ busqueda: busqueda({ estado: 'error', resultados: [], error: 'el asistente no contestó' }), resultados: [] })
    ).toMatch(/No se pudo buscar en los mensajes: el asistente no contestó/);
  });

  it('al tope avisa que hay más', () => {
    const treinta = Array.from({ length: 30 }, (_, i) => ({ ...RES[0], mensaje_id: `m${i}` }));
    const html = dibujar({ busqueda: busqueda({ resultados: treinta }), resultados: treinta });
    expect(html).toMatch(/Se muestran los 30 más recientes/);
  });

  it('inactivo no dibuja nada', () => {
    expect(dibujar({ busqueda: busqueda({ estado: 'inactivo' }), resultados: [] }).trim()).toBe('');
  });
});

describe('en la lista de la cola', () => {
  const base = {
    conversaciones: [{ id: 'x' }],
    tramoEspera: () => null,
    motivoLabel: (/** @type {string} */ m) => m
  };

  it('un error del motor no tapa el hueco de la cola filtrada', () => {
    const html = render(ConversationList, {
      props: {
        ...base,
        visibles: [],
        busqueda: 'poste',
        busquedaMensajes: busqueda({ estado: 'error', resultados: [], error: 'caído' }),
        resultadosMensajes: []
      }
    }).body;
    expect(html).toMatch(/Ninguna coincide con «poste»/);
    expect(html).toMatch(/No se pudo buscar en los mensajes/);
  });

  it('sin búsqueda en mensajes, la cola es la de siempre', () => {
    const html = render(ConversationList, { props: { ...base, visibles: [], busqueda: 'po' } }).body;
    expect(html).not.toMatch(/En mensajes/);
  });
});
