import { describe, it, expect } from 'vitest';
import { opcionesDeLider } from './lider-de-cuadrilla.js';

/**
 * QUIÉNES SE OFRECEN COMO LÍDER
 * =============================
 *
 * El defecto (17/10/2026): en Rapilink ninguna persona de campo tenía la
 * cuenta enlazada, el selector salía con «— sin líder —» y nada más, y
 * guardar la ficha le borró el líder a una cuadrilla. Se siembra ese mismo
 * caso: personas SIN cuenta, el equipo como cuentas sueltas, y un líder que
 * ya existía.
 */

const SIN_CUENTA = [
  { id: 'pc-1', nombre: 'JEIDER AMELL', tiene_cuenta: false, profile: null },
  { id: 'pc-2', nombre: 'ISAIAS MORENO', tiene_cuenta: false, profile: null }
];
const CUENTAS = [
  { profile: 'pr-jeider', nombre: 'Jeider Amell' },
  { profile: 'pr-admin', nombre: 'Administración' }
];

describe('opcionesDeLider', () => {
  it('sin ninguna persona de campo con cuenta, ofrece igual las cuentas del equipo', () => {
    const o = opcionesDeLider(SIN_CUENTA, CUENTAS, null);
    expect(o.deCampo).toEqual([]);
    expect(o.cuentas.map((c) => c.profile)).toEqual(['pr-jeider', 'pr-admin']);
    expect(o.actual).toBeNull();
  });

  it('el líder que ya tiene se ofrece SIEMPRE, aunque no esté en ninguna lista', () => {
    // Una cuenta dada de baja, por ejemplo: no viene en las cuentas sueltas
    // ni entre las personas activas. Sin esta opción el selector queda en
    // blanco y guardar lo borraba.
    const o = opcionesDeLider(SIN_CUENTA, CUENTAS, { id: 'pr-viejo', nombre: 'Líder de antes' });
    expect(o.actual).toEqual({ profile: 'pr-viejo', nombre: 'Líder de antes' });
  });

  it('si el líder ya está en una lista, no se repite arriba', () => {
    const o = opcionesDeLider(SIN_CUENTA, CUENTAS, { id: 'pr-jeider', nombre: 'Jeider Amell' });
    expect(o.actual).toBeNull();
    expect(o.cuentas.some((c) => c.profile === 'pr-jeider')).toBe(true);
  });

  it('una persona de campo con cuenta va en su grupo, y la que no tiene cuenta no se ofrece', () => {
    const personas = [
      { id: 'pc-3', nombre: 'JULIO MORENO', tiene_cuenta: true, profile: 'pr-julio' },
      ...SIN_CUENTA
    ];
    const o = opcionesDeLider(personas, CUENTAS, { id: 'pr-julio', nombre: 'Julio' });
    // El valor es la CUENTA, no la persona: el líder es un Profile.
    expect(o.deCampo).toEqual([{ profile: 'pr-julio', nombre: 'JULIO MORENO' }]);
    expect(o.actual).toBeNull();
  });

  it('sin datos no rompe: listas vacías y sin líder', () => {
    expect(opcionesDeLider(undefined, null, undefined)).toEqual({
      actual: null, deCampo: [], cuentas: []
    });
  });
});
