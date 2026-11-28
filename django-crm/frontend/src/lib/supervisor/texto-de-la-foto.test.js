/**
 * ============================================================================
 *  EL POR QUÉ DE UNA FOTO, EN UN RENGLÓN  --  21/11/2026
 * ============================================================================
 * Los textos de estas guardas son los que el usuario tenía en la pantalla en
 * la OT #283, copiados de sus capturas. Se afirma el EFECTO sobre lo que se
 * lee: que las marcas del protocolo no aparecen, que el renglón es corto, y
 * que acortar no rompe un número.
 * ============================================================================
 */
import { describe, it, expect } from 'vitest';
import { porQue, sinMarcas, TOPE_DEL_POR_QUE } from './texto-de-la-foto.js';

//  Tal como llegan: el modelo deja las marcas en renglones propios.
const AL_LLEGAR =
  'Se ve pantalla de medidor óptico Rouhan con -50.00 dBm; es captura de ' +
  'foto de catálogo, no medición real.\nCATALOGO: no\nMUESTRA: si\nATENCION: si';
const AL_SALIR =
  'Medidor óptico Rouhan en imagen de catálogo, sobre fondo blanco. ' +
  'Pantalla legible: 1550 nm, ID, -21.0 dBm, 0.682 µW, 2kHz. Es material de ' +
  'producto, no evidencia de una medición en el trabajo.\n' +
  'CATALOGO: si\nMUESTRA: si\nATENCION: si';

describe('sinMarcas', () => {
  it('quita las tres marcas del protocolo', () => {
    const limpio = sinMarcas(AL_LLEGAR);

    expect(limpio).not.toMatch(/CATALOGO|MUESTRA|ATENCION/);
    expect(limpio).toBe(
      'Se ve pantalla de medidor óptico Rouhan con -50.00 dBm; es captura ' +
      'de foto de catálogo, no medición real.');
  });

  it('también cuando el modelo las deja todas en el mismo renglón', () => {
    //  Así se veían en la pantalla: pegadas al final de la frase.
    const limpio = sinMarcas(
      'No medición real. CATALOGO: no MUESTRA: si ATENCION: si');

    expect(limpio).toBe('No medición real.');
  });

  it('con tilde y con «no se sabe»', () => {
    expect(sinMarcas('Está oscura.\nMUESTRA: no se sabe\nATENCIÓN: sí\nCATÁLOGO: no'))
      .toBe('Está oscura.');
  });

  it('NO se come una frase que usa esas palabras para decir algo', () => {
    //  La marca es `CLAVE: valor`. «La foto muestra: un router» no lo es, y
    //  borrarla sería quitarle al supervisor justo lo que el modelo vio.
    const frase = 'La foto muestra: un router con las luces encendidas.';

    expect(sinMarcas(frase)).toBe(frase);
  });

  it('sin texto devuelve vacío, no «undefined»', () => {
    expect(sinMarcas(null)).toBe('');
    expect(sinMarcas(undefined)).toBe('');
    expect(sinMarcas('')).toBe('');
  });
});

describe('porQue', () => {
  it('lo que ya es corto sale entero, sin las marcas', () => {
    expect(porQue(AL_LLEGAR)).toBe(
      'Se ve pantalla de medidor óptico Rouhan con -50.00 dBm; es captura ' +
      'de foto de catálogo, no medición real.');
  });

  it('lo largo se queda con la primera frase, que es la conclusión', () => {
    const corto = porQue(AL_SALIR);

    expect(corto).toBe(
      'Medidor óptico Rouhan en imagen de catálogo, sobre fondo blanco.');
    expect(corto.length).toBeLessThanOrEqual(TOPE_DEL_POR_QUE);
  });

  it('NO corta un número por la mitad', () => {
    //  «-21.0 dBm» cortado en «-21.» se leería como otra lectura. El punto
    //  de un decimal no separa frases.
    const corto = porQue(
      'La pantalla marca -21.0 dBm y 0.682 µW en 1550 nm. Después sigue una ' +
      'descripción larga del fondo, del cable, de la mano que sostiene el ' +
      'equipo y de todo lo demás que no hace falta para decidir.');

    expect(corto).toBe('La pantalla marca -21.0 dBm y 0.682 µW en 1550 nm.');
  });

  it('una sola frase larguísima se corta en una palabra y dice que hay más', () => {
    const corto = porQue(`${'palabra '.repeat(60)}fin`);

    expect(corto.length).toBeLessThanOrEqual(TOPE_DEL_POR_QUE);
    expect(corto.endsWith('…')).toBe(true);
    expect(corto).not.toMatch(/\s…$/);
  });

  it('nunca pasa del tope', () => {
    for (const texto of [AL_LLEGAR, AL_SALIR, 'x'.repeat(500), 'a. '.repeat(200)]) {
      expect(porQue(texto).length).toBeLessThanOrEqual(TOPE_DEL_POR_QUE);
    }
  });
});
