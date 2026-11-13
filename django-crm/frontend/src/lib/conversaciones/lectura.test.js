import { describe, it, expect } from 'vitest';
import {
  noLeidos,
  noLeidosVisibles,
  hayPersonaEnElCaso,
  ofreceMarcarNoLeida,
  ultimoDelCliente,
  filaDelChat,
  debeMarcarLeida
} from './lectura.js';
import { PREDICADOS } from './cola/pestanas.js';

/**
 * Cuándo la conversación avisa que se leyó (11/11/2026). Lo que se protege:
 * que se marque al abrir y con algo NUEVO a la vista, nunca en cada sondeo
 * sin novedad ni con la pestaña de fondo, y que una cola vieja no reabra la
 * marca que ya se hizo.
 */
describe('lo que se lee', () => {
  it('no_leidos como número, y 0 para lo que no lo es', () => {
    expect(noLeidos({ no_leidos: 3 })).toBe(3);
    expect(noLeidos({ no_leidos: '2' })).toBe(2);
    expect(noLeidos({})).toBe(0);
    expect(noLeidos({ no_leidos: -1 })).toBe(0);
    expect(noLeidos(null)).toBe(0);
  });

  it('el último del CLIENTE, no el último del hilo', () => {
    const t = ultimoDelCliente([
      { rol: 'user', creado_en: '2026-11-11T10:00:00Z' },
      { rol: 'user', creado_en: '2026-11-11T10:05:00Z' },
      { rol: 'assistant', creado_en: '2026-11-11T10:09:00Z' }
    ]);
    expect(t).toBe(Date.parse('2026-11-11T10:05:00Z'));
    expect(ultimoDelCliente([{ rol: 'assistant', creado_en: '2026-11-11T10:00:00Z' }])).toBeNull();
  });

  it('la fila del chat se encuentra por cualquiera de sus conversaciones', () => {
    const cola = [{ id: 'a', ids: ['x', 'a'] }, { id: 'b' }];
    expect(filaDelChat(cola, 'x')?.id).toBe('a');
    expect(filaDelChat(cola, 'b')?.id).toBe('b');
    expect(filaDelChat(cola, 'z')).toBeNull();
  });
});

/**
 * Lo que se MUESTRA (11/11/2026, decisión de producto H5): contador, negrita y
 * filtro «No leídas» solo con una persona en el caso -- la misma regla que las
 * pestañas «Por atender» y «En atención». En «Lleva la IA», nada.
 */
describe('los no leídos se muestran solo con una persona en el caso', () => {
  const abierta = { estado: 'abierta', no_leidos: 3 };
  const pedida = { ...abierta, escalada_a_humano: true };
  const marcada = { ...abierta, necesita_atencion_humana: true };
  const sinGestion = { ...abierta, banda_nombre: 'sin_gestion' };
  const tomada = { ...abierta, tomada_por: 'Ana' };
  const escribio = { ...abierta, atendida: true };
  const deLaIA = { ...abierta };

  it('pedida para una persona (escalada, marcada o sin gestión): se muestran', () => {
    for (const c of [pedida, marcada, sinGestion]) expect(noLeidosVisibles(c)).toBe(3);
  });

  it('en atención (tomada, o una persona ya escribió): se muestran', () => {
    for (const c of [tomada, escribio]) expect(noLeidosVisibles(c)).toBe(3);
  });

  it('EL EFECTO: la lleva la IA -- nadie la pidió ni la tomó --: 0, aunque el motor cuente 3', () => {
    expect(noLeidos(deLaIA)).toBe(3);
    expect(noLeidosVisibles(deLaIA)).toBe(0);
  });

  it('un chat de la IA con OTRA abierta pedida del mismo número: se muestran (mira el chat entero)', () => {
    expect(noLeidosVisibles({ ...deLaIA, abiertas: [{ estado: 'abierta', escalada_a_humano: true }] })).toBe(3);
  });

  it('es exactamente la regla de las pestañas: visible si y solo si «Por atender» o «En atención»', () => {
    const casos = [pedida, marcada, sinGestion, tomada, escribio, deLaIA,
      { ...pedida, estado: 'cerrada' }, { ...tomada, estado: 'cerrada' }];
    for (const c of casos) {
      const enPestanaConPersona = PREDICADOS['por-atender'](c) || PREDICADOS['en-atencion'](c);
      expect(hayPersonaEnElCaso(c)).toBe(enPestanaConPersona);
      if (PREDICADOS['lleva-ia'](c)) expect(noLeidosVisibles(c)).toBe(0);
    }
  });

  it('sin fila, nada', () => {
    expect(hayPersonaEnElCaso(null)).toBe(false);
    expect(noLeidosVisibles(undefined)).toBe(0);
  });
});

describe('«Marcar como no leída» solo donde el contador se ve', () => {
  it('se ofrece con una persona en el caso, mirando la fila del CHAT en la cola', () => {
    const cola = [{ id: 'rep', ids: ['vieja', 'rep'], estado: 'abierta', tomada_por: 'Ana' }];
    expect(ofreceMarcarNoLeida(cola, { id: 'vieja', estado: 'abierta' })).toBe(true);
  });

  it('en un chat que lleva la IA no se ofrece', () => {
    const cola = [{ id: 'c1', estado: 'abierta', no_leidos: 2 }];
    expect(ofreceMarcarNoLeida(cola, { id: 'c1', estado: 'abierta' })).toBe(false);
  });

  it('si la cola no tiene el chat, decide la conversación misma', () => {
    expect(ofreceMarcarNoLeida([], { id: 'c1', estado: 'abierta', escalada_a_humano: true })).toBe(true);
    expect(ofreceMarcarNoLeida(undefined, { id: 'c1', estado: 'abierta' })).toBe(false);
  });
});

describe('cuándo se marca leída', () => {
  const base = { visible: true, marcadaAlAbrir: true, marcadaEn: 1000, ultimoCliente: 500,
    marcadoHasta: 500, noLeidosEnCola: 0, colaLeidaEn: 900 };

  it('al abrir, con la pestaña a la vista', () => {
    expect(debeMarcarLeida({ ...base, marcadaAlAbrir: false })).toBe(true);
  });

  it('con la pestaña de fondo, nunca: abierta no es leída', () => {
    expect(debeMarcarLeida({ ...base, marcadaAlAbrir: false, visible: false })).toBe(false);
    expect(debeMarcarLeida({ ...base, visible: false, ultimoCliente: 2000 })).toBe(false);
  });

  it('sin nada nuevo no se vuelve a marcar en cada sondeo', () => {
    expect(debeMarcarLeida(base)).toBe(false);
  });

  it('un mensaje nuevo del cliente en esta conversación la marca', () => {
    expect(debeMarcarLeida({ ...base, ultimoCliente: 1500 })).toBe(true);
  });

  it('la cola dice que hay no leídos (otra abierta del chat) y es posterior a la marca', () => {
    expect(debeMarcarLeida({ ...base, noLeidosEnCola: 2, colaLeidaEn: 1200 })).toBe(true);
  });

  it('una cola leída ANTES de la marca no la reabre', () => {
    expect(debeMarcarLeida({ ...base, noLeidosEnCola: 2, colaLeidaEn: 800 })).toBe(false);
  });

  it('con una marca viajando no sale otra', () => {
    expect(debeMarcarLeida({ ...base, marcadaAlAbrir: false, enVuelo: true })).toBe(false);
  });
});
