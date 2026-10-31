/**
 * EL INTERRUPTOR DE TEMA PONE Y SACA LA CLASE QUE ACTIVA LA PALETA OSCURA.
 *
 * Se afirma sobre el efecto -- la clase `dark` en <html>, que es lo que lee
 * `.dark .v2-root` en v2.css -- y sobre que app.html lea la misma clave, porque
 * si las dos no coinciden el tema se pierde en cada recarga sin ningun error.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { CLAVE, alternarTema, aplicarTema, leerTema } from './tema.js';

let clases;
let guardado;

beforeEach(() => {
  clases = new Set();
  guardado = new Map();
  globalThis.document = /** @type {any} */ ({
    documentElement: {
      classList: {
        toggle: (c, on) => (on ? clases.add(c) : clases.delete(c)),
        contains: (c) => clases.has(c)
      }
    }
  });
  globalThis.localStorage = /** @type {any} */ ({
    getItem: (k) => (guardado.has(k) ? guardado.get(k) : null),
    setItem: (k, v) => guardado.set(k, v)
  });
});

afterEach(() => {
  delete globalThis.document;
  delete globalThis.localStorage;
});

describe('tema', () => {
  it('arranca en claro si nadie eligio', () => {
    expect(leerTema()).toBe('claro');
  });

  it('alternar prende el oscuro, lo recuerda, y alternar de nuevo lo apaga', () => {
    expect(alternarTema()).toBe('oscuro');
    expect(clases.has('dark')).toBe(true);
    expect(guardado.get(CLAVE)).toBe('oscuro');
    expect(alternarTema()).toBe('claro');
    expect(clases.has('dark')).toBe(false);
  });

  it('si el navegador bloquea el almacenamiento, queda claro y no lanza', () => {
    globalThis.localStorage = /** @type {any} */ ({
      getItem: () => {
        throw new Error('bloqueado');
      },
      setItem: () => {
        throw new Error('bloqueado');
      }
    });
    expect(leerTema()).toBe('claro');
    expect(() => aplicarTema('oscuro')).not.toThrow();
    expect(clases.has('dark')).toBe(true);
  });

  it('app.html aplica el tema antes de pintar con la misma clave', () => {
    const plantilla = readFileSync(path.resolve('./src/app.html'), 'utf8');
    expect(plantilla).toContain(`'${CLAVE}'`);
    expect(plantilla).toContain("classList.add('dark')");
  });
});
