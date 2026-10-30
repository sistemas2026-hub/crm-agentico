import { describe, it, expect } from 'vitest';
import { horaDeEspera } from './espera.js';

/** La hora del «en espera» (C22). Sin elección no se inventa una hora. */
describe('horaDeEspera', () => {
  const ahora = new Date('2026-10-30T15:00:00Z');
  it('en 1 h y en 4 h cuentan desde ahora', () => {
    expect(horaDeEspera('1h', ahora)).toBe('2026-10-30T16:00:00.000Z');
    expect(horaDeEspera('4h', ahora)).toBe('2026-10-30T19:00:00.000Z');
  });
  it('mañana es a las 8 del día siguiente, en la hora local', () => {
    const d = new Date(/** @type {string} */ (horaDeEspera('manana', ahora)));
    expect(d.getHours()).toBe(8);
    expect(d.getDate()).toBe(new Date(ahora.getTime() + 86400_000).getDate());
  });
  it('sin elección, sin hora', () => {
    expect(horaDeEspera('', ahora)).toBeNull();
    expect(horaDeEspera('otra', ahora)).toBeNull();
  });
});
