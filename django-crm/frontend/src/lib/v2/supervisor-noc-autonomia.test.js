import { describe, it, expect } from 'vitest';
import { loQueHaceSolo } from './supervisor-noc-autonomia.js';

const tarea = (clave, extra = {}) => ({
  clave,
  nombre: `Tarea ${clave}`,
  que_hace: `Hace ${clave}`,
  delegada: true,
  nivel_alcanza: true,
  exige_nivel: 3,
  la_despierta_algo: { si: true },
  ...extra
});

describe('loQueHaceSolo', () => {
  it('sin respuesta del backend no afirma nada: estado desconocido', () => {
    const r = loQueHaceSolo(null);
    expect(r.leido).toBe(false);
    expect(r.activas).toEqual([]);
  });

  it('una tarea delegada, con nivel y con algo que la despierte, ACTÚA', () => {
    const r = loQueHaceSolo({ interruptor_permite: true, efectivo: 3, delegaciones: [tarea('a')] });
    expect(r.activas).toHaveLength(1);
    expect(r.activas[0]).toMatchObject({ clave: 'a', actua: true, porQue: null });
  });

  it('delegada no es lo mismo que funcionando: sin nivel, NO actúa y dice por qué', () => {
    //  El 15/10 una tarea estuvo delegada, con nada que la corriera, cinco
    //  vueltas. Un punto verde ahí habría mentido.
    const r = loQueHaceSolo({
      interruptor_permite: true,
      efectivo: 1,
      delegaciones: [tarea('a', { nivel_alcanza: false })]
    });
    expect(r.activas[0].actua).toBe(false);
    expect(r.activas[0].porQue).toBe('Necesita nivel 3 y el que aplica hoy es 1.');
  });

  it('delegada sin nada que la despierte: NO actúa, con el motivo del backend', () => {
    const r = loQueHaceSolo({
      interruptor_permite: true,
      efectivo: 3,
      delegaciones: [tarea('a', { la_despierta_algo: { si: false, por_que: 'El reloj está apagado.' } })]
    });
    expect(r.activas[0]).toMatchObject({ actua: false, porQue: 'El reloj está apagado.' });
  });

  it('con el freno de mano puesto ninguna actúa, aunque todo lo demás esté bien', () => {
    const r = loQueHaceSolo({
      interruptor_permite: false,
      efectivo: 3,
      delegaciones: [tarea('a'), tarea('b')]
    });
    expect(r.frenado).toBe(true);
    expect(r.activas.every((t) => !t.actua)).toBe(true);
    expect(r.activas[0].porQue).toBe('El freno de mano está puesto.');
  });

  it('las no delegadas no se listan: se cuentan', () => {
    const r = loQueHaceSolo({
      interruptor_permite: true,
      efectivo: 3,
      delegaciones: [tarea('a'), tarea('b', { delegada: false }), tarea('c', { delegada: false })]
    });
    expect(r.activas.map((t) => t.clave)).toEqual(['a']);
    expect(r.sinDelegar).toBe(2);
  });

  it('cuenta cuántas actúan de verdad, no cuántas están delegadas', () => {
    const r = loQueHaceSolo({
      interruptor_permite: true,
      efectivo: 3,
      delegaciones: [tarea('a'), tarea('b', { nivel_alcanza: false, exige_nivel: 4 })]
    });
    expect(r.actuan).toBe(1);
    expect(r.activas).toHaveLength(2);
  });

  it('sin catálogo lo dice, en vez de mostrar un bloque vacío', () => {
    const r = loQueHaceSolo({ interruptor_permite: true, efectivo: 3 });
    expect(r.leido).toBe(true);
    expect(r.sinCatalogo).toBe(true);
  });
});
