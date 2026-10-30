/**
 * La carga por operador (29/10/2026). Lo que importa: que cuente
 * conversaciones y no chats, que no cuente las cerradas ni las sin dueño, y
 * que la espera que muestra sea la MÁS VIEJA, que es la que hay que mirar.
 */
import { describe, it, expect } from 'vitest';
import { cargaPorOperador } from './carga.js';

const ana = { asignada_a_usuario_id: 'u-ana', asignada_a: 'Ana' };
const luis = { asignada_a_usuario_id: 'u-luis', asignada_a: 'Luis' };

describe('cargaPorOperador', () => {
  it('cuenta las abiertas de cada persona, la más cargada primero', () => {
    const cola = [
      { id: '1', estado: 'abierta', ...ana },
      { id: '2', estado: 'abierta', ...ana },
      { id: '3', estado: 'abierta', ...luis }
    ];
    const r = cargaPorOperador(cola);
    expect(r.map((p) => [p.nombre, p.abiertas])).toEqual([['Ana', 2], ['Luis', 1]]);
    expect(r[0].ids).toEqual(['1', '2']);
  });

  it('un chat con dos abiertas de la misma persona son dos', () => {
    const cola = [{ id: '1', estado: 'abierta', ...ana, abiertas: [{ id: '9', estado: 'abierta', ...ana }] }];
    expect(cargaPorOperador(cola)[0].abiertas).toBe(2);
  });

  it('ni las cerradas ni las que no tienen dueño', () => {
    const cola = [
      { id: '1', estado: 'cerrada', ...ana },
      { id: '2', estado: 'abierta' }
    ];
    expect(cargaPorOperador(cola)).toEqual([]);
  });

  it('la espera es la más vieja', () => {
    const cola = [
      { id: '1', estado: 'abierta', ...ana, esperando_desde: '2026-10-29T10:00:00Z' },
      { id: '2', estado: 'abierta', ...ana, esperando_desde: '2026-10-28T10:00:00Z' }
    ];
    expect(cargaPorOperador(cola, Date.parse('2026-10-30T00:00:00Z'))[0].esperandoDesde)
      .toBe('2026-10-28T10:00:00Z');
  });

  it('la misma conversación repetida no se cuenta dos veces', () => {
    const fila = { id: '1', estado: 'abierta', ...ana };
    expect(cargaPorOperador([{ ...fila, abiertas: [fila] }])[0].abiertas).toBe(1);
  });
});
