import { describe, it, expect } from 'vitest';
import {
  armarPulso,
  fichaActiva,
  fichaDeCaidas,
  fichaDeKits,
  fichaDeReportando,
  fichaDeSinRepartir,
  fichaDeSla,
  fichaDelSupervisor
} from './pulso.js';

describe('el Pulso no inventa ceros', () => {
  it('una fuente que no respondió da «sin dato», no 0', () => {
    const fichas = armarPulso({});
    expect(fichas).toHaveLength(6);
    for (const f of fichas) {
      expect(f.valor).toBeNull();
      expect(f.texto).toContain('sin dato');
      expect(f.tono).toBe('neutro');
    }
  });

  it('cada ficha lleva a su pantalla', () => {
    expect(armarPulso({}).map((f) => f.href)).toEqual([
      '/supervisor-noc',
      '/supervisor-noc/fallas',
      '/supervisor-noc/programacion',
      '/supervisor-noc/despacho',
      '/supervisor-noc/programacion',
      '/supervisor-noc/ajustes'
    ]);
  });
});

describe('SLA', () => {
  it('cuenta vencidas y por vencer, sin las desincronizadas que cierra el Supervisor', () => {
    const f = fichaDeSla([
      { sla_estado: 'VENCIDA', tipo_senal: 'orden_sin_programar' },
      { sla_estado: 'VENCE_PRONTO', tipo_senal: 'caso_requiere_visita' },
      { sla_estado: 'VENCE_PRONTO', tipo_senal: 'caso_requiere_visita' },
      { sla_estado: 'VENCIDA', tipo_senal: 'caso_desincronizado' },
      { sla_estado: 'A_TIEMPO', tipo_senal: 'x' }
    ]);
    expect(f.valor).toBe('1');
    expect(f.texto).toBe('SLA vencido · 2 por vencer');
    expect(f.tono).toBe('critico');
  });

  it('solo por vencer es ámbar; nada es verde', () => {
    expect(fichaDeSla([{ sla_estado: 'VENCE_PRONTO' }]).tono).toBe('alerta');
    expect(fichaDeSla([]).tono).toBe('ok');
  });
});

describe('caídas, cuadrillas, reparto y kits', () => {
  it('solo cuentan las caídas vivas', () => {
    const f = fichaDeCaidas([{ estado: 'confirmada' }, { estado: 'resuelta' }, { estado: 'detectada' }]);
    expect(f.valor).toBe('2');
    expect(f.tono).toBe('critico');
    expect(fichaDeCaidas([]).tono).toBe('ok');
  });

  it('reportando es «con posición de total»', () => {
    const f = fichaDeReportando({ cuadrillas: [{ posicion: {} }, {}, {}, {}, {}] });
    expect(f.valor).toBe('1/5');
    expect(f.tono).toBe('alerta');
    expect(fichaDeReportando({ cuadrillas: [] }).texto).toBe('Sin cuadrillas armadas hoy');
  });

  it('sin repartir y kits usan las cuentas que ya trae el servidor', () => {
    expect(fichaDeSinRepartir({ cuentas: { esperan: 334 } }).valor).toBe('334');
    expect(fichaDeSinRepartir({ cuentas: {} }).valor).toBeNull();
    expect(fichaDeKits({ cuentas: { con_faltantes: 5 } }).tono).toBe('critico');
    expect(fichaDeKits({ cuentas: { con_faltantes: 0 } }).tono).toBe('ok');
  });
});

describe('el Supervisor', () => {
  it('frenado es rojo y lleva el motivo', () => {
    const f = fichaDelSupervisor({ permitido: false, motivo: 'freno de mano: algo raro' });
    expect(f.valor).toBe('Frenado');
    expect(f.tono).toBe('critico');
    expect(f.motivo).toBe('freno de mano: algo raro');
  });

  it('libre es índigo; sin respuesta del motor, sin dato', () => {
    expect(fichaDelSupervisor({ permitido: true }).tono).toBe('accion');
    expect(fichaDelSupervisor({ permitido: null }).valor).toBeNull();
  });
});

describe('la ficha de la pantalla abierta', () => {
  const fichas = armarPulso({});
  it('Pendientes solo en su ruta exacta', () => {
    expect(fichaActiva(fichas, '/supervisor-noc')).toBe('sla');
    expect(fichaActiva(fichas, '/supervisor-noc/')).toBe('sla');
  });
  it('las demás por prefijo, y Planes semanales es parte de Programación', () => {
    expect(fichaActiva(fichas, '/supervisor-noc/fallas')).toBe('caidas');
    expect(fichaActiva(fichas, '/supervisor-noc/despacho')).toBe('sin_repartir');
    expect(fichaActiva(fichas, '/supervisor-noc/planes-semanales')).toBe('reportando');
    expect(fichaActiva(fichas, '/supervisor-noc/plantillas')).toBeNull();
  });
});
