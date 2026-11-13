import { describe, expect, it } from 'vitest';

import { textoDeLosTotales, totalesDeLoQueCrearia } from './lo-que-crearia.js';

describe('los totales de lo que crearía el Supervisor', () => {
  const crear = [
    { por: 'asunto', nivel: 'programable', nivel_nombre: 'Programable' },
    { por: 'asunto', nivel: 'urgente', nivel_nombre: 'Inmediato', equipo_caido: true },
    { por: 'labor', nivel: '', equipo_caido: true },
    { por: 'labor' },
    { por: 'asunto', nivel: 'urgente', nivel_nombre: 'Inmediato' }
  ];

  it('cuenta plantilla, nivel y caída', () => {
    const t = totalesDeLoQueCrearia(crear);
    expect([t.porAsunto, t.porLabor, t.conNivel, t.sinNivel, t.equipoCaido])
      .toEqual([3, 2, 3, 2, 2]);
  });

  it('dice el nombre que eligió la empresa, en el orden de los niveles', () => {
    expect(textoDeLosTotales(totalesDeLoQueCrearia(crear))).toEqual([
      'Plantilla por el asunto 3 · por la labor 2',
      'Con nivel 3 (Inmediato 2, Programable 1) · sin nivel 2 · equipo caído 2'
    ]);
  });

  it('sin niveles lo dice, porque entonces la prioridad no cambió', () => {
    expect(textoDeLosTotales(totalesDeLoQueCrearia([{ por: 'labor' }]))).toEqual([
      'Plantilla por el asunto 0 · por la labor 1',
      'Ningún asunto tiene nivel todavía: la prioridad sale del plazo de la plantilla'
    ]);
  });

  it('sin filas no se rompe', () => {
    expect(totalesDeLoQueCrearia(undefined).porAsunto).toBe(0);
  });
});
