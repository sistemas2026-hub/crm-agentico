/**
 * Las respuestas rápidas, DIBUJADAS de verdad en el compositor (11/11/2026).
 *
 * Se dibuja con lo escrito ya en el cuadro («/sa») y el cursor al final, que
 * es lo que el compositor supone antes de que la persona toque el cuadro: así
 * el servidor dibuja la lista abierta y se puede afirmar sobre el HTML --
 * la opción, el texto con el nombre resuelto, y la accesibilidad que permite
 * elegir sin sacar el foco del cuadro.
 *
 * La regla de las teclas (Enter elige con la lista abierta) se prueba pura en
 * respuestas-rapidas.test.js; acá se fija que el compositor la consulte ANTES
 * de enviar, porque sin DOM no hay forma de apretar Enter.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import MessageComposer from './MessageComposer.svelte';

const RESPUESTAS = [
  { atajo: 'saludo', texto: 'Hola {nombre}, ¿en qué te ayudo?' },
  { atajo: 'reinicio', texto: 'Desconectá el equipo 30 segundos.' },
  { atajo: 'sabado', texto: 'Los sábados atendemos de 8 a 12.' }
];

const dibujar = (/** @type {any} */ props) =>
  render(MessageComposer, {
    props: {
      conversacion: { canal: 'whatsapp', nombre_cliente: 'ANA MARÍA PÉREZ' },
      modo: 'responder',
      escalada: true,
      entrada: '',
      respuestasRapidas: RESPUESTAS,
      ...props
    }
  }).body.replace(/<!--[\s\S]*?-->/g, '');

const opciones = (/** @type {string} */ html) =>
  [...html.matchAll(/<li\b([^>]*role="option"[^>]*)>([\s\S]*?)<\/li>/g)].map(([, attrs, dentro]) => ({
    attrs,
    texto: dentro.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
  }));

describe('la lista de respuestas rápidas', () => {
  it('«/sa» abre la lista filtrada, con el nombre del cliente ya puesto', () => {
    const html = dibujar({ entrada: '/sa' });
    expect(html).toMatch(/role="listbox"/);
    const ops = opciones(html);
    // «saludo» empieza con «sa»; «sabado» también. «reinicio» no.
    expect(ops.map((o) => o.texto.split(' ')[0])).toEqual(['/saludo', '/sabado']);
    expect(ops[0].texto).toContain('Hola Ana, ¿en qué te ayudo?');
  });

  it('la primera está marcada y el cuadro la anuncia sin perder el foco', () => {
    const html = dibujar({ entrada: '/sa' });
    const [primera, segunda] = opciones(html);
    expect(primera.attrs).toMatch(/aria-selected="true"/);
    expect(segunda.attrs).toMatch(/aria-selected="false"/);
    const id = primera.attrs.match(/id="([^"]+)"/)?.[1];
    const textarea = html.match(/<textarea\b[^>]*>/)?.[0] ?? '';
    expect(textarea).toMatch(/role="combobox"/);
    expect(textarea).toMatch(/aria-expanded="true"/);
    expect(textarea).toContain(`aria-activedescendant="${id}"`);
    const lista = html.match(/<ul\b[^>]*role="listbox"[^>]*>/)?.[0] ?? '';
    const idLista = lista.match(/id="([^"]+)"/)?.[1];
    expect(textarea).toContain(`aria-controls="${idLista}"`);
  });

  it('sin nombre conocido, {nombre} se quita sin dejar la frase rota', () => {
    const html = dibujar({ entrada: '/salu', conversacion: { canal: 'whatsapp' } });
    expect(opciones(html)[0].texto).toContain('Hola, ¿en qué te ayudo?');
  });

  it('sin «/» no hay lista y el cuadro no dice que la hay', () => {
    const html = dibujar({ entrada: 'hola' });
    expect(html).not.toMatch(/role="listbox"/);
    expect(html.match(/<textarea\b[^>]*>/)?.[0]).toMatch(/aria-expanded="false"/);
  });

  it('en la nota interna no se ofrece: es texto para el equipo', () => {
    expect(dibujar({ entrada: '/sa', modo: 'nota' })).not.toMatch(/role="listbox"/);
  });

  it('con la IA atendiendo o la ventana cerrada tampoco: ahí no se escribe', () => {
    expect(dibujar({ entrada: '/sa', bloqueadoPorIA: true })).not.toMatch(/role="listbox"/);
    expect(dibujar({ entrada: '/sa', bloqueadoPorVentana: true })).not.toMatch(/role="listbox"/);
  });

  it('nada que coincida: no hay lista, y se dice que Enter envía tal cual', () => {
    const html = dibujar({ entrada: '/zzz' });
    expect(html).not.toMatch(/role="listbox"/);
    expect(html).toMatch(/Ninguna respuesta rápida coincide con «\/zzz»/);
  });

  it('sin respuestas guardadas, el «/» lleva a crearlas', () => {
    const html = dibujar({ entrada: '/', respuestasRapidas: [] });
    expect(html).not.toMatch(/role="listbox"/);
    expect(html).toMatch(/No hay respuestas rápidas guardadas/);
    expect(html).toMatch(/href="\/settings\/bandeja"/);
    // Y el cuadro no se declara combobox de una lista que no existe.
    expect(html.match(/<textarea\b[^>]*>/)?.[0]).not.toMatch(/role="combobox"/);
  });

  it('el botón de enviar sigue al lado del cuadro con la lista abierta', () => {
    const html = dibujar({ entrada: '/sa' });
    const caja = html.slice(html.indexOf('class="escribir'), html.indexOf('compositor-pie'));
    expect(caja).toMatch(/<textarea/);
    expect(caja).toMatch(/Enviar/);
  });
});

describe('el compositor consulta la lista ANTES de enviar', () => {
  const fuente = readFileSync(
    fileURLToPath(new URL('./MessageComposer.svelte', import.meta.url)),
    'utf-8'
  );
  const onkeydown = fuente.slice(fuente.indexOf('onkeydown={(e) => {'));

  it('teclaDeLaLista corre primero y, si la tecla es de la lista, corta con return', () => {
    const lista = onkeydown.indexOf('teclaDeLaLista(e, listaAbierta');
    const enviar = onkeydown.indexOf("e.key === 'Enter' && !e.shiftKey");
    expect(lista).toBeGreaterThan(-1);
    expect(enviar).toBeGreaterThan(lista);
    const entre = onkeydown.slice(lista, enviar);
    expect(entre).toMatch(/if \(deLaLista\) \{[\s\S]*e\.preventDefault\(\);[\s\S]*return;\s*\}/);
  });
});
