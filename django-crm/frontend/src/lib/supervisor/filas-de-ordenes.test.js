import { describe, expect, it } from 'vitest';
import {
  TOPE_VISIBLE,
  arrancaAbierta,
  cuentasDeLosFiltros,
  motivosDeAtencion,
  partirLasFilas,
  pasaElFiltro
} from './filas-de-ordenes.js';

const DIA = '2026-11-22';
/** @param {object} [x] */
const o = (x = {}) => ({ id: 'o1', numero: 167, asunto: 'Problemas De Conexión', cliente: 'Mario Pérez',
  barrio: 'CACARAMOA', estado: 'asignada', vence_en: '2026-11-25', ...x });

describe('lo que pide atención se nombra en la fila', () => {
  it('cada bloque de la tarjeta tiene su palabra', () => {
    expect(motivosDeAtencion(o({ bloqueo: { desde: '10:12' } }))).toEqual(['Detenida']);
    expect(motivosDeAtencion(o({ devolucion: { quien: 'Ana' } }))).toEqual(['Devuelta']);
    expect(motivosDeAtencion(o({ estado: 'completada_campo', revision: { id: 'r' } }))).toEqual(['Por revisar']);
    expect(motivosDeAtencion(o({ estado: 'completada_campo', validacion: 'aprobado' }))).toEqual(['Lista para cerrar']);
    //  27/11/2026: una instalación que valida una persona la cierra el técnico.
    expect(motivosDeAtencion(o({ estado: 'completada_campo', validacion: 'aprobado', la_cierra_el_tecnico: true })))
      .toEqual(['Falta que el técnico finalice']);
    expect(motivosDeAtencion(o({ seguimiento: { tipo: 'vencido' } }))).toEqual(['Sin reporte']);
    expect(motivosDeAtencion(o({ aviso: 'no_llego' }))).toEqual(['No llegó al teléfono']);
  });

  it('una orden en regla no pide nada, y la fila arranca cerrada', () => {
    expect(motivosDeAtencion(o())).toEqual([]);
    expect(arrancaAbierta(o())).toBe(false);
  });

  it('arranca abierta si pide atención o si el resultado de una acción es suyo', () => {
    expect(arrancaAbierta(o({ bloqueo: {} }))).toBe(true);
    expect(arrancaAbierta(o(), { de: 'mover', orden: 'o1' })).toBe(true);
    expect(arrancaAbierta(o(), { de: 'mover', orden: 'otra' })).toBe(false);
  });
});

describe('el filtro y el buscador', () => {
  it('vencidas usa la misma cuenta que el color de la tarjeta', () => {
    expect(pasaElFiltro(o({ vence_en: '2026-11-06' }), 'vencidas', '', DIA)).toBe(true);
    expect(pasaElFiltro(o(), 'vencidas', '', DIA)).toBe(false);
  });

  it('sin terminar deja afuera lo cerrado y lo cancelado', () => {
    expect(pasaElFiltro(o({ estado: 'cerrada' }), 'sin_terminar', '', DIA)).toBe(false);
    expect(pasaElFiltro(o({ estado: 'en_sitio' }), 'sin_terminar', '', DIA)).toBe(true);
  });

  it('busca por número, cliente o barrio, sin mirar tildes ni mayúsculas', () => {
    expect(pasaElFiltro(o(), 'todas', '167', DIA)).toBe(true);
    expect(pasaElFiltro(o(), 'todas', 'ot 167', DIA)).toBe(true);
    expect(pasaElFiltro(o(), 'todas', 'perez', DIA)).toBe(true);
    expect(pasaElFiltro(o(), 'todas', 'cacaramoa', DIA)).toBe(true);
    expect(pasaElFiltro(o(), 'todas', 'conexion', DIA)).toBe(true);
    expect(pasaElFiltro(o(), 'todas', 'soledad', DIA)).toBe(false);
  });

  it('cuenta cuántas entran en cada filtro', () => {
    const c = [{ ordenes: [o(), o({ id: 'o2', vence_en: '2026-10-07', bloqueo: {} }), o({ id: 'o3', estado: 'cerrada' })] }];
    expect(cuentasDeLosFiltros(c, DIA)).toEqual({ todas: 3, atencion: 1, vencidas: 1, sin_terminar: 2 });
  });
});

describe('una cuadrilla larga se pliega sin esconder lo que pide atención', () => {
  const veinte = Array.from({ length: 20 }, (_, i) => o({ id: `o${i}`, numero: i + 1 }));

  it(`muestra ${TOPE_VISIBLE} en el orden del día y pliega el resto`, () => {
    const p = partirLasFilas(veinte, { dia: DIA });
    expect(p.visibles.map((x) => x.numero)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(p.plegadas).toHaveLength(12);
    expect(p.atencionPlegada).toBe(0);
  });

  it('dice cuántas de las plegadas piden atención', () => {
    const l = veinte.map((x, i) => (i === 15 ? { ...x, bloqueo: {} } : x));
    expect(partirLasFilas(l, { dia: DIA }).atencionPlegada).toBe(1);
  });

  it('con un filtro o una búsqueda no pliega nada', () => {
    expect(partirLasFilas(veinte, { dia: DIA, filtro: 'sin_terminar' }).plegadas).toHaveLength(0);
    expect(partirLasFilas(veinte, { dia: DIA, texto: 'conexion' }).visibles).toHaveLength(20);
  });

  it('no pliega una o dos: no ahorra nada y suma un clic', () => {
    expect(partirLasFilas(veinte.slice(0, TOPE_VISIBLE + 2), { dia: DIA }).plegadas).toHaveLength(0);
    expect(partirLasFilas(veinte.slice(0, TOPE_VISIBLE + 3), { dia: DIA }).plegadas).toHaveLength(3);
  });
});
