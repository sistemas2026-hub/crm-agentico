import { describe, it, expect } from 'vitest';
import { resumir, LIMITE_RESUMEN } from './resumen.js';

/**
 * Cada caso de aqui es una forma concreta en que un recorte a ojo falla.
 * Se afirma sobre el EFECTO (que devuelve y que se ve), no sobre que la
 * funcion exista.
 */

describe('resumir', () => {
  it('no toca un texto que ya entra, y no dice que lo recorto', () => {
    const corto = 'Atiende consultas de facturacion.';
    expect(resumir(corto)).toEqual({ texto: corto, recortado: false });
  });

  it('el texto vacio o ausente no explota ni inventa contenido', () => {
    for (const v of ['', '   ', null, undefined]) {
      expect(resumir(/** @type {any} */ (v))).toEqual({ texto: '', recortado: false });
    }
  });

  it('recorta donde termina una frase, y ahi NO agrega suspensivos', () => {
    // '.…' se lee como un error de tipeo: la frase ya quedo cerrada.
    const texto = 'Primera frase que ocupa un buen rato y llega lejos en el limite. ' +
                  'Segunda frase que sobra. '.repeat(10);
    const r = resumir(texto);
    expect(r.recortado).toBe(true);
    expect(r.texto.endsWith('.')).toBe(true);
    expect(r.texto).not.toContain('…');
  });

  it('una sola frase larga se corta por palabra, y ahi SI lleva suspensivos', () => {
    const texto = 'palabra '.repeat(80).trim(); // sin un solo punto
    const r = resumir(texto);
    expect(r.recortado).toBe(true);
    expect(r.texto.endsWith('…')).toBe(true);
    // Lo que importa: no queda una palabra partida al medio.
    expect(r.texto.slice(0, -1).trim().split(' ').pop()).toBe('palabra');
  });

  it('un punto demasiado temprano no tira casi todo el texto', () => {
    // El caso real: descripcion que arranca corta y sigue con el protocolo.
    const texto = 'Ventas. ' + 'detalle '.repeat(60).trim();
    const r = resumir(texto);
    expect(r.recortado).toBe(true);
    // Si cortara en ese primer punto quedarian 7 caracteres.
    expect(r.texto.length).toBeGreaterThan(LIMITE_RESUMEN * 0.5);
  });

  it('nunca devuelve mas que el limite, salvo el caracter de los suspensivos', () => {
    const casos = [
      'x'.repeat(500),
      'frase corta. ' + 'y'.repeat(400),
      'a '.repeat(300).trim(),
      'Una. Dos. Tres. ' + 'z '.repeat(200).trim()
    ];
    for (const c of casos) {
      expect(resumir(c).texto.length).toBeLessThanOrEqual(LIMITE_RESUMEN + 1);
    }
  });

  it('el espacio sobrante antes del corte no queda colgando', () => {
    const r = resumir('palabra '.repeat(80).trim());
    expect(r.texto).not.toContain(' …');
  });
});
