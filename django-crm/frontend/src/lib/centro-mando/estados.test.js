import { describe, it, expect } from 'vitest';
import {
  ESTADOS,
  EMITIDOS,
  TRANSICIONES,
  normalizar,
  rotuloDe,
  colorDe,
  transicionValida,
  ordenar,
  repartoPorEstado
} from './estados.js';

/**
 * Lo que se afirma es el EFECTO: que estado sale, en que orden se leen, que
 * transicion se acepta. Nunca que la tabla exista -- un test que solo
 * comprueba que hay ocho claves sobrevive intacto a que alguien intercambie
 * el color del error con el de disponible.
 */

describe('la tabla de estados', () => {
  it('cubre los ocho estados del contrato', () => {
    expect(Object.keys(ESTADOS).sort()).toEqual(
      ['completed', 'error', 'idle', 'offline', 'waiting_approval', 'waiting_tool', 'waiting_user', 'working'].sort()
    );
  });

  it('declara cuales emite el motor hoy y cuales no', () => {
    // Si alguien empieza a emitir 'waiting_tool' sin registrar la llamada al
    // invocarla, este test obliga a actualizar la bandera y a explicarse.
    expect(EMITIDOS).toContain('working');
    expect(EMITIDOS).toContain('waiting_approval');
    expect(EMITIDOS).not.toContain('waiting_tool');
    expect(EMITIDOS).not.toContain('offline');
    expect(EMITIDOS).not.toContain('completed');
  });

  it('el error se ve distinto de lo normal', () => {
    expect(colorDe('error')).not.toBe(colorDe('idle'));
    expect(colorDe('error')).not.toBe(colorDe('working'));
    expect(rotuloDe('error')).toMatch(/error/i);
  });

  it('un estado desconocido no rompe la pantalla', () => {
    expect(normalizar('inventado')).toBe('idle');
    expect(normalizar(undefined)).toBe('idle');
    expect(colorDe(null)).toBe(ESTADOS.idle.color);
  });
});

describe('las transiciones', () => {
  it('toda transicion apunta a un estado que existe', () => {
    for (const [desde, hacia] of Object.entries(TRANSICIONES)) {
      for (const destino of hacia) {
        expect(ESTADOS[destino], `${desde} -> ${destino}`).toBeDefined();
      }
    }
  });

  it('acepta los pasos reales de un turno', () => {
    expect(transicionValida('idle', 'working')).toBe(true);
    expect(transicionValida('working', 'waiting_approval')).toBe(true);
    expect(transicionValida('waiting_approval', 'completed')).toBe(true);
    expect(transicionValida('error', 'working')).toBe(true);
  });

  it('quedarse donde esta siempre vale', () => {
    for (const e of Object.keys(ESTADOS)) {
      expect(transicionValida(e, e)).toBe(true);
    }
  });

  it('rechaza un salto que no ocurre', () => {
    // Un agente sin conversaciones no puede quedar 'esperando respuesta'.
    expect(transicionValida('idle', 'waiting_user')).toBe(false);
    expect(transicionValida('offline', 'error')).toBe(false);
  });
});

describe('el orden de lectura', () => {
  const agentes = [
    { nombre: 'ventas', estado: 'idle', conversaciones: 0 },
    { nombre: 'soporte', estado: 'error', conversaciones: 2 },
    { nombre: 'facturacion', estado: 'working', conversaciones: 3 },
    { nombre: 'campo', estado: 'waiting_approval', conversaciones: 1 },
    { nombre: 'router', estado: 'working', conversaciones: 9 }
  ];

  it('pone primero lo que exige atencion', () => {
    expect(ordenar(agentes).map((a) => a.nombre)).toEqual([
      'soporte', // error
      'campo', // espera aprobacion
      'router', // trabajando, mas carga
      'facturacion', // trabajando, menos carga
      'ventas' // disponible
    ]);
  });

  it('no modifica la lista que recibe', () => {
    const copia = [...agentes];
    ordenar(agentes);
    expect(agentes).toEqual(copia);
  });

  it('cuenta cuantos hay en cada estado', () => {
    expect(repartoPorEstado(agentes)).toEqual({
      idle: 1,
      error: 1,
      working: 2,
      waiting_approval: 1
    });
  });
});
