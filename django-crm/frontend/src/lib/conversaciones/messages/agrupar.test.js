/**
 * La agrupación del hilo (04/11/2026): solo el primer mensaje de una ráfaga
 * del mismo autor lleva su nombre encima.
 *
 * Las negativas pesan tanto como la positiva: si dos personas del equipo se
 * fundieran en un grupo, la respuesta de una se leería como de la otra; y si
 * una nota interna no cortara, el mensaje siguiente parecería parte de ella.
 */
import { describe, it, expect } from 'vitest';
import { agruparMensajes, VENTANA_GRUPO_MS } from './agrupar.js';

const T0 = Date.parse('2026-11-04T15:00:00Z');
const en = (min) => new Date(T0 + min * 60 * 1000).toISOString();
let n = 0;
const msg = (m) => ({ tipo: 'msg', clave: `m-${n++}`, m: { adjuntos: [], ...m } });
const cliente = (min, extra = {}) => msg({ rol: 'user', origen: 'cliente', creado_en: en(min), ...extra });
const ia = (min) => msg({ rol: 'assistant', origen: 'ia', creado_en: en(min) });
const persona = (min, nombre) =>
  msg({ rol: 'assistant', origen: 'humano', autor_nombre: nombre, creado_en: en(min) });
const inicios = (items) =>
  agruparMensajes(items).filter((i) => i.tipo === 'msg').map((i) => i.inicioDeGrupo);

describe('una ráfaga del mismo autor', () => {
  it('nombra al autor solo en el primero', () => {
    expect(inicios([cliente(0), cliente(1), cliente(3)])).toEqual([true, false, false]);
  });

  it('el primero del hilo siempre abre grupo', () => {
    expect(inicios([ia(0)])).toEqual([true]);
  });

  it('cambiar de autor abre grupo', () => {
    expect(inicios([cliente(0), ia(1), ia(2), cliente(3)])).toEqual([true, true, false, true]);
  });
});

describe('lo que corta un grupo', () => {
  it('diez minutos o más entre uno y otro', () => {
    const casi = VENTANA_GRUPO_MS / 60000 - 1;
    expect(inicios([cliente(0), cliente(casi)])).toEqual([true, false]);
    expect(inicios([cliente(0), cliente(10)])).toEqual([true, true]);
  });

  it('dos personas distintas del equipo no se funden', () => {
    expect(inicios([persona(0, 'Ana'), persona(1, 'Luis'), persona(2, 'Luis')]))
      .toEqual([true, true, false]);
  });

  it('una nota interna en el medio', () => {
    const nota = msg({ rol: 'nota', creado_en: en(1), autor_nombre: 'Ana' });
    expect(inicios([persona(0, 'Ana'), nota, persona(2, 'Ana')])).toEqual([true, true, true]);
  });

  it('un separador de día, una marca de cierre o «ver anteriores»', () => {
    for (const corte of [
      { tipo: 'dia', clave: 'd', texto: 'Hoy' },
      { tipo: 'cierre', clave: 'c', texto: 'Cerrada' },
      { tipo: 'mas', clave: 'x', texto: 'Ver conversaciones anteriores' }
    ]) {
      expect(inicios([cliente(0), corte, cliente(1)]), corte.tipo).toEqual([true, true]);
    }
  });

  it('otro día, aunque sean pocos minutos', () => {
    const antes = msg({ rol: 'user', origen: 'cliente', creado_en: '2026-11-04T23:58:00' });
    const despues = msg({ rol: 'user', origen: 'cliente', creado_en: '2026-11-05T00:02:00' });
    expect(inicios([antes, despues])).toEqual([true, true]);
  });

  it('un mensaje sin hora no se da por seguido', () => {
    expect(inicios([cliente(0), cliente(0, { creado_en: null })])).toEqual([true, true]);
  });

  it('el cliente de otra conversación del chat no sigue al de esta', () => {
    expect(inicios([cliente(0, { deOtraConversacion: true }), cliente(1)])).toEqual([true, true]);
  });
});

describe('no toca lo que no es suyo', () => {
  it('no muta los items ni cambia el orden ni la cantidad', () => {
    const items = [cliente(0), { tipo: 'dia', clave: 'd', texto: 'Hoy' }, cliente(1)];
    const copia = JSON.parse(JSON.stringify(items));
    const salida = agruparMensajes(items);
    expect(items).toEqual(copia);
    expect(salida.map((i) => i.clave)).toEqual(items.map((i) => i.clave));
    expect(salida[1]).toBe(items[1]);
  });

  it('tolera una lista vacía o ausente', () => {
    expect(agruparMensajes([])).toEqual([]);
    expect(agruparMensajes(undefined)).toEqual([]);
  });
});
