import { describe, it, expect } from 'vitest';
import { calcularPaginacion } from './paginacion.js';

/**
 * EL DEFECTO, medido en produccion el 07/10/2026: la cola de Cartera tenia 47
 * tickets abiertos, la pantalla mostraba 25 y no habia forma de ver los otros
 * 22. Se afirma sobre el EFECTO -- que exista un enlace que lleve a ellos --
 * y sobre que ese enlace no pierda el resto de los filtros, porque perder uno
 * manda a la persona a otra cola sin avisar.
 */

const u = (s) => new URL('https://x.test' + s);

describe('el caso de produccion: 47 tickets, paginas de 25', () => {
  it('la primera pagina ofrece un enlace a los que faltan', () => {
    const p = calcularPaginacion(u('/tickets?area=cartera'), 47, 0, 25);
    expect(p.siguiente).toBe('/tickets?area=cartera&offset=25');
    expect(p.previa).toBeNull();
  });

  it('y dice que esta mostrando del 1 al 25 de 47', () => {
    const p = calcularPaginacion(u('/tickets'), 47, 0, 25);
    expect([p.desde, p.hasta, p.total]).toEqual([1, 25, 47]);
    expect([p.pagina, p.paginas]).toEqual([1, 2]);
  });

  it('en la segunda se ven los 22 restantes, y se puede volver', () => {
    const p = calcularPaginacion(u('/tickets?area=cartera&offset=25'), 47, 25, 25);
    expect([p.desde, p.hasta]).toEqual([26, 47]);
    expect(p.siguiente).toBeNull();
    expect(p.previa).toBe('/tickets?area=cartera');
  });
});

describe('los enlaces conservan lo demas', () => {
  it('no pierde el area, la vista ni los filtros', () => {
    const p = calcularPaginacion(
      u('/tickets?area=soporte_tecnico&vista=mios&priority=High&all=1'), 90, 0, 25);
    const s = new URL('https://x.test' + p.siguiente);
    expect(s.searchParams.get('area')).toBe('soporte_tecnico');
    expect(s.searchParams.get('vista')).toBe('mios');
    expect(s.searchParams.get('priority')).toBe('High');
    expect(s.searchParams.get('all')).toBe('1');
    expect(s.searchParams.get('offset')).toBe('25');
  });

  it('volver a la primera pagina QUITA el offset, no lo deja en 0', () => {
    //  '?offset=0' y sin offset son la misma pagina; dejar el parametro
    //  ensucia la URL y hace que dos enlaces a lo mismo se vean distintos.
    const p = calcularPaginacion(u('/tickets?area=cartera&offset=25'), 47, 25, 25);
    expect(p.previa).toBe('/tickets?area=cartera');
    expect(p.previa).not.toContain('offset');
  });

  it('respeta un limit distinto', () => {
    const p = calcularPaginacion(u('/tickets?limit=100'), 300, 0, 100);
    expect(p.hasta).toBe(100);
    expect(p.siguiente).toContain('limit=100');
    expect(p.siguiente).toContain('offset=100');
  });
});

describe('los bordes, que son donde una paginacion se rompe', () => {
  it('una cola vacia no ofrece enlaces ni dice "del 1 al 0"', () => {
    const p = calcularPaginacion(u('/tickets'), 0, 0, 25);
    expect([p.desde, p.hasta, p.total]).toEqual([0, 0, 0]);
    expect([p.previa, p.siguiente]).toEqual([null, null]);
    expect(p.paginas).toBe(1);
  });

  it('una cola que entra justa en una pagina no ofrece siguiente', () => {
    const p = calcularPaginacion(u('/tickets'), 25, 0, 25);
    expect(p.siguiente).toBeNull();
    expect(p.hasta).toBe(25);
  });

  it('un offset mas alla del final trae a la ultima pagina real', () => {
    //  Pasa al borrar tickets o al seguir un enlace viejo. Sin esto la
    //  pantalla queda en blanco y parece que no hay nada.
    const p = calcularPaginacion(u('/tickets?offset=500'), 47, 500, 25);
    expect([p.desde, p.hasta]).toEqual([26, 47]);
    expect(p.siguiente).toBeNull();
  });

  it('un offset negativo o basura se trata como la primera pagina', () => {
    for (const malo of [-10, NaN, undefined]) {
      const p = calcularPaginacion(u('/tickets'), 47, malo, 25);
      expect(p.desde).toBe(1);
      expect(p.previa).toBeNull();
    }
  });

  it('el total exacto de dos paginas da dos paginas, no tres', () => {
    const p = calcularPaginacion(u('/tickets'), 50, 25, 25);
    expect(p.paginas).toBe(2);
    expect(p.siguiente).toBeNull();
  });
});
