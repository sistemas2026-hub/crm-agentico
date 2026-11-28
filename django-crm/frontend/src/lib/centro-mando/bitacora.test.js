import { describe, it, expect } from 'vitest';
import { crearBitacora } from './bitacora.js';
import { proyectar } from './proyeccion.js';

/**
 * LO SIMULADO NO PUEDE ACABAR EN EL HISTORIAL REAL.
 *
 * Es el riesgo que la ficha marca como grave, y la protección no es una
 * bandera: son dos arreglos separados y una sola puerta de escritura que mira
 * la procedencia. La diferencia importa — una bandera se puede olvidar en un
 * `push`; para romper esto hay que cambiar la función.
 */

const T = 1_700_000_000_000;
const uuid = (n) => `3f1a2b4c-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

function proyectada(n, { simulado = false, agente = 'supervisor_noc' } = {}) {
  const eventos = [{ id: uuid(n), agente, tipo: 'consulta', herramienta: `h${n}` }];
  return proyectar(eventos, { agentes: [agente], ahora: T, simulado }).instrucciones;
}

describe('dos historiales, y no se tocan', () => {
  it('lo real va a lo real', () => {
    const b = crearBitacora();
    b.anotar(proyectada(1));
    expect(b.real).toHaveLength(1);
    expect(b.simulado).toHaveLength(0);
  });

  it('lo simulado va a lo simulado', () => {
    const b = crearBitacora();
    b.anotar(proyectada(2, { simulado: true }));
    expect(b.simulado).toHaveLength(1);
    expect(b.real).toHaveLength(0);
  });

  it('los dos juntos no se mezclan', () => {
    const b = crearBitacora();
    b.anotar([...proyectada(3), ...proyectada(4, { simulado: true })]);
    expect(b.real).toHaveLength(1);
    expect(b.simulado).toHaveLength(1);
    expect(b.real.every((a) => a.procedencia.startsWith('evento:'))).toBe(true);
    expect(b.simulado.every((a) => a.procedencia === 'simulado')).toBe(true);
  });

  it('NINGUNA anotación del historial real tiene procedencia simulada', () => {
    // La afirmación que mata la mutación: si `anotar` dejara de mirar la
    // procedencia y empujara todo a `real`, esto se pone rojo.
    const b = crearBitacora();
    for (let i = 10; i < 20; i++) b.anotar(proyectada(i, { simulado: i % 2 === 0 }));
    expect(b.real.filter((a) => a.procedencia === 'simulado')).toEqual([]);
    expect(b.real).toHaveLength(5);
    expect(b.simulado).toHaveLength(5);
  });
});

describe('lo decorativo no tiene historial', () => {
  it('una procedencia «ambiente» se descarta', () => {
    // No pasó nada. Contarlo como actividad es la afirmación que no se puede
    // hacer, y es justo la procedencia que lleva el reposo.
    const b = crearBitacora();
    b.anotar([{ id: uuid(30), agente: 'x', tipo: 'reposo', procedencia: 'ambiente' }]);
    expect(b.real).toHaveLength(0);
    expect(b.simulado).toHaveLength(0);
    expect(b.descartadas).toBe(1);
  });

  it('una instrucción sin procedencia se descarta y se cuenta', () => {
    const b = crearBitacora();
    b.anotar([{ id: uuid(31), agente: 'x', tipo: 'consulta' }, null, {}]);
    expect(b.descartadas).toBe(3);
  });
});

describe('duplicados', () => {
  it('el mismo hecho entregado dos veces se anota una', () => {
    // Duplicar es el precio de no perder ninguno en la transición foto→cursor.
    // Un historial con la misma línea repetida se lee como dos hechos.
    const b = crearBitacora();
    const i = proyectada(40);
    b.anotar(i);
    b.anotar(i);
    expect(b.real).toHaveLength(1);
  });

  it('el mismo identificador en los dos orígenes NO se confunde', () => {
    // El guion de demostración genera uuid de verdad: podrían coincidir con uno
    // real. La clave de deduplicación lleva la procedencia justamente por eso.
    const b = crearBitacora();
    b.anotar(proyectada(41));
    b.anotar(proyectada(41, { simulado: true }));
    expect(b.real).toHaveLength(1);
    expect(b.simulado).toHaveLength(1);
  });
});

describe('el tope y el olvido', () => {
  it('no crece sin límite', () => {
    // La pantalla puede quedarse abierta todo el día.
    const b = crearBitacora(5);
    for (let i = 50; i < 70; i++) b.anotar(proyectada(i));
    expect(b.real).toHaveLength(5);
  });

  it('lo más reciente queda primero', () => {
    const b = crearBitacora();
    b.anotar(proyectada(71));
    b.anotar(proyectada(72));
    expect(b.real[0].etiqueta).toBe('h72');
  });

  it('olvidar la demostración no toca lo real', () => {
    const b = crearBitacora();
    b.anotar(proyectada(80));
    b.anotar(proyectada(81, { simulado: true }));
    b.olvidarSimulado();
    expect(b.simulado).toHaveLength(0);
    expect(b.real).toHaveLength(1);
  });
});
