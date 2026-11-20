import { describe, it, expect } from 'vitest';
import { itemsDelChat, textoDeCierre } from './chat.js';
import { pendiente, resuelta, enAtencion } from './estado.js';
import { loQuePaso } from './actividad.js';

describe('el registro de actividad distingue T21 de una intervención', () => {
  const ev = { tipo: 'intervencion', actor_tipo: 'operador', actor_nombre: 'Ana Perez',
               datos: { version: 1, tomada: true, continua_de: 'cerrada-1' } };
  it('escribirle a un chat cerrado no se cuenta como intervenir', () => {
    expect(loQuePaso(ev).texto).toContain('le escribió al chat cerrado');
  });
  it('una intervención de verdad se sigue contando como tal', () => {
    expect(loQuePaso({ ...ev, datos: { version: 1, tomada: true } }).texto).toContain('intervino');
  });
});

/* La bandeja como WhatsApp (21/10/2026, contrato §4.5): un chat por número.
   Se afirma sobre lo que la pantalla DIBUJA y CUENTA, no sobre la forma. */

const diaDe = (/** @type {string} */ iso) => iso.slice(0, 10);
const etiquetaDia = (/** @type {string} */ iso) => `DIA ${iso.slice(0, 10)}`;
const formatoHora = (/** @type {string} */ iso) => `a las ${iso.slice(11, 16)}`;

describe('la marca de cierre dice solo lo registrado', () => {
  it('con quién y cuándo, los dice', () => {
    expect(textoDeCierre({ por: 'operador', en: '2026-10-20T15:30:00Z' }, formatoHora))
      .toBe('Conversación cerrada · a las 15:30 · la cerró una persona');
  });
  it('el cierre por inactividad de hoy no deja ni quién ni cuándo: no se inventan', () => {
    expect(textoDeCierre({ por: null, en: null }, formatoHora)).toBe('Conversación cerrada');
  });
  it('un motivo desconocido no se traduce a cualquier cosa', () => {
    expect(textoDeCierre({ por: 'otro_motivo', en: null }, formatoHora)).toBe('Conversación cerrada');
  });
});

describe('el hilo del chat', () => {
  const tramos = [
    { conversacion: { id: 'c1', estado: 'cerrada', cierre: { por: 'ia_cliente', en: '2026-10-19T10:00:00Z' } },
      mensajes: [{ id: 'a', rol: 'user', creado_en: '2026-10-19T09:00:00Z', conversation_id: 'c1' }] },
    { conversacion: { id: 'c2', estado: 'cerrada', cierre: { por: null, en: null } },
      mensajes: [{ id: 'b', rol: 'user', creado_en: '2026-10-20T09:00:00Z', conversation_id: 'c2' }] }
  ];
  const actuales = [{ id: 'c', rol: 'user', creado_en: '2026-10-20T18:00:00Z' }];
  const items = itemsDelChat(tramos, actuales, { diaDe, etiquetaDia, formatoHora, hayAnteriores: true });

  it('pone primero el botón de ver más, después las anteriores en orden y al final la actual', () => {
    expect(items.map((i) => i.tipo)).toEqual(['mas', 'dia', 'msg', 'cierre', 'dia', 'msg', 'cierre', 'dia', 'msg']);
    expect(items.filter((i) => i.tipo === 'msg').map((i) => i.m.id)).toEqual(['a', 'b', 'c']);
  });
  it('cada marca dice lo suyo', () => {
    expect(items.filter((i) => i.tipo === 'cierre').map((i) => i.texto)).toEqual([
      'Conversación cerrada · a las 10:00 · el cliente confirmó con la IA',
      'Conversación cerrada'
    ]);
  });
  it('después de una marca el día se vuelve a decir, aunque sea el mismo', () => {
    const dias = items.filter((i) => i.tipo === 'dia').map((i) => i.texto);
    expect(dias).toEqual(['DIA 2026-10-19', 'DIA 2026-10-20', 'DIA 2026-10-20']);
  });
  it('los mensajes viejos se marcan como de otra conversación; los actuales no', () => {
    const msgs = items.filter((i) => i.tipo === 'msg').map((i) => i.m);
    expect(msgs.map((m) => !!m.deOtraConversacion)).toEqual([true, true, false]);
    expect(msgs[0].conversation_id).toBe('c1');
  });
  it('una anterior que sigue abierta no se dibuja como cerrada', () => {
    const abierta = itemsDelChat(
      [{ conversacion: { id: 'x', estado: 'abierta', cierre: null }, mensajes: [] }], [],
      { diaDe, etiquetaDia });
    expect(abierta[0].texto).toBe('Esta conversación del mismo número sigue abierta');
  });
  it('la marca de una que sigue abierta lleva a ella; la de una cerrada no lleva a ningún lado', () => {
    // Sin el enlace, una escalada vieja detrás de la conversación actual no
    // tenía cómo tomarse desde la pantalla (auditor independiente, 21/10/2026).
    const abierta = itemsDelChat(
      [{ conversacion: { id: 'x', estado: 'abierta', cierre: null }, mensajes: [] }], [],
      { diaDe, etiquetaDia });
    expect(abierta[0].enlace).toBe('x');
    expect(items.filter((i) => i.tipo === 'cierre').map((i) => i.enlace)).toEqual([null, null]);
  });
  it('una sincronización sin terminar de una conversación vieja sigue a la vista (I17)', () => {
    const conSync = itemsDelChat(
      [{ conversacion: { id: 'y', estado: 'cerrada', cierre: { por: 'operador', en: null },
                         sincronizacion_pendiente: true }, mensajes: [] }], [],
      { diaDe, etiquetaDia });
    expect(conSync[0].texto).toBe('Conversación cerrada · la cerró una persona · con una sincronización sin terminar');
  });
  it('un número que cambió de dueño se dice en la marca, sin decir quién era', () => {
    const otro = itemsDelChat(
      [{ conversacion: { id: 'z', estado: 'cerrada', cierre: { por: null, en: null }, otro_cliente: true },
         mensajes: [] }], [], { diaDe, etiquetaDia });
    expect(otro[0].texto).toBe('Conversación cerrada · era otro cliente');
  });
  it('sin anteriores queda igual que antes: solo días y mensajes', () => {
    const solo = itemsDelChat([], actuales, { diaDe, etiquetaDia });
    expect(solo.map((i) => i.tipo)).toEqual(['dia', 'msg']);
  });
});

describe('las pestañas cuentan el chat entero', () => {
  // El representante es una conversación nueva que atiende la IA; detrás hay
  // una escalada vieja del mismo número, sin tomar. Mirar solo la fila la
  // escondía de "Por atender".
  const chat = {
    estado: 'abierta', escalada_a_humano: false, necesita_atencion_humana: false, atendida: false,
    abiertas: [{ estado: 'abierta', escalada_a_humano: true, necesita_atencion_humana: true,
                 atendida: false, tomada_por: null }]
  };
  it('una escalada detrás del representante deja el chat en Por atender', () => {
    expect(pendiente(chat)).toBe(true);
  });
  it('y no está resuelto mientras tenga una abierta', () => {
    expect(resuelta({ ...chat, estado: 'cerrada' })).toBe(false);
  });
  it('si la de atrás la tomó alguien, está en atención', () => {
    const tomada = { ...chat, abiertas: [{ ...chat.abiertas[0], tomada_por: 'Ana' }] };
    expect(pendiente(tomada)).toBe(false);
    expect(enAtencion(tomada)).toBe(true);
  });
  it('una conversación sola se cuenta como siempre', () => {
    expect(pendiente({ estado: 'abierta', escalada_a_humano: true, atendida: false })).toBe(true);
    expect(resuelta({ estado: 'cerrada' })).toBe(true);
  });
});
