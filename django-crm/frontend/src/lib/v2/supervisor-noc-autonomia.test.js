import { describe, it, expect } from 'vitest';
import {
  loQueHaceSolo,
  tarjetasDeSolo,
  resumenAutonomiaGanada,
  CLAVE_DESINCRONIZADOS,
  CLAVE_ORDENES,
  nombreDeAccion
} from './supervisor-noc-autonomia.js';

describe('nombreDeAccion', () => {
  it('traduce las acciones conocidas y no inventa las demás', () => {
    expect(nombreDeAccion('reiniciar_ont')).toBe('Reiniciar el equipo del cliente');
    expect(nombreDeAccion('algo_nuevo_del_motor')).toBe('algo nuevo del motor');
  });
});

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

describe('tarjetasDeSolo', () => {
  const alcance = (delegaciones) => ({ interruptor_permite: true, efectivo: 3, delegaciones });

  it('las claves son las del catálogo del backend', () => {
    //  Si alguien renombra la clave en tareas_delegadas.py, la tarjeta queda
    //  sin dato en vez de mostrar otra tarea: esta prueba lo recuerda.
    expect(CLAVE_DESINCRONIZADOS).toBe('cerrar_desincronizados_con_diagnostico');
    expect(CLAVE_ORDENES).toBe('aprobar_y_cerrar_lo_que_dio_por_bueno');
  });

  it('una tarea no delegada es "apagada", no "no actúa"', () => {
    const t = tarjetasDeSolo(alcance([tarea(CLAVE_DESINCRONIZADOS, { delegada: false })]));
    expect(t.desincronizados?.estado).toBe('apagada');
  });

  it('delegada y corriendo es "encendida"; delegada sin correr es "no_actua" con motivo', () => {
    const t = tarjetasDeSolo(alcance([
      tarea(CLAVE_DESINCRONIZADOS),
      tarea(CLAVE_ORDENES, { nivel_alcanza: false, exige_nivel: 4 })
    ]));
    expect(t.desincronizados?.estado).toBe('encendida');
    expect(t.ordenes?.estado).toBe('no_actua');
    expect(t.ordenes?.porQue).toBe('Necesita nivel 4 y el que aplica hoy es 3.');
  });

  it('una tarea que el catálogo no trae queda sin dato, no apagada', () => {
    expect(tarjetasDeSolo(alcance([tarea('otra')])).desincronizados).toBeNull();
  });

  it('las demás delegadas van aparte, para no esconderlas', () => {
    const t = tarjetasDeSolo(alcance([tarea(CLAVE_DESINCRONIZADOS), tarea('revisar'), tarea('armar', { delegada: false })]));
    expect(t.otras.map((x) => x.clave)).toEqual(['revisar']);
  });

  it('sin respuesta, nada', () => {
    expect(tarjetasDeSolo(null)).toEqual({ desincronizados: null, ordenes: null, otras: [], frenado: null });
  });
});

describe('resumenAutonomiaGanada', () => {
  it('sin respuesta del motor no afirma "ninguna"', () => {
    expect(resumenAutonomiaGanada(null).leido).toBe(false);
    expect(resumenAutonomiaGanada({ autonomia: null, error: 'x' })).toMatchObject({ leido: true, error: 'x' });
  });

  it('separa autónomas, degradadas y elegibles, solo entre las candidatas', () => {
    const r = resumenAutonomiaGanada({
      autonomia: {
        acciones: [
          { accion: 'reiniciar_ont', candidata: true, elegible: true, autonomia: { autonoma: true } },
          { accion: 'activar_catv', candidata: true, elegible: false, autonomia: { estado: 'degradada' } },
          { accion: 'cambiar_plan', candidata: true, elegible: true },
          { accion: 'registrar_pago', candidata: false, elegible: false }
        ]
      }
    });
    expect(r.autonomas).toEqual(['reiniciar_ont']);
    expect(r.degradadas).toEqual(['activar_catv']);
    expect(r.elegibles).toEqual(['cambiar_plan']);
    expect(r.candidatas).toBe(3);
  });
});
