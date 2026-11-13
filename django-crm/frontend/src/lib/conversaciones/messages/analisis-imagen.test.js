/**
 * ════════════════════════════════════════════════════════════════════════════
 *  Que el resumen no diga nada que el análisis no diga
 * ════════════════════════════════════════════════════════════════════════════
 *
 * El riesgo de resumir un texto que escribió un modelo no es que quede feo:
 * es que invierta el sentido. "No se observan luces rojas" resumido como
 * "luces rojas" convierte un equipo sano en uno con falla, y quien atiende lo
 * lee como un hallazgo. Por eso la mitad de estas pruebas son sobre negación.
 *
 * El caso de la sección 1 es el texto REAL que DeepSeek devolvió en
 * producción el 05/10/2026, copiado de `asistente.media`. Las pruebas sobre
 * texto inventado miden lo que uno imagina que el modelo escribe; esta mide
 * lo que escribió.
 */
import { describe, it, expect } from 'vitest';
import { esAnalisisDeImagen, partirMensaje, resumir } from './analisis-imagen.js';

/** Tal cual lo guardó producción el 05/10/2026 09:39. */
const REAL = `Se ve un equipo blanco con rejillas y dos antenas verticales, montado en una pared clara. En la parte superior tiene una fila de indicadores LED: varios están encendidos en verde y otros apagados; no se distingue si parpadean y los rótulos no se leen con claridad. Hay cables negros gruesos que pasan por delante y se cruzan, un cable blanco que baja por el lateral izquierdo y un conector metálico conectado en la parte inferior derecha, parcialmente tapado por los cables. No se observan luces rojas ni naranjas encendidas.`;

const MENSAJE_REAL = `[Foto que envio el cliente]

[Analisis automatico de la foto, no verificado]
${REAL}`;

const MENSAJE_CON_PIE = `[Foto que envio el cliente]

[Texto que escribio junto con la imagen]
Mira como esta mi modem, la lucecita roja

[Analisis automatico de la foto, no verificado]
${REAL}`;

describe('reconocer el mensaje', () => {
  it('reconoce un mensaje con análisis', () => {
    expect(esAnalisisDeImagen(MENSAJE_REAL)).toBe(true);
  });

  it('no confunde un mensaje de texto normal', () => {
    expect(esAnalisisDeImagen('Buenas, se me fue el internet')).toBe(false);
  });

  it('no confunde una nota de voz transcrita', () => {
    const voz = '[Nota de voz del cliente] Hola, se fue el internet.';
    expect(esAnalisisDeImagen(voz)).toBe(false);
    expect(partirMensaje(voz)).toBeNull();
  });

  it('no confunde una foto SIN análisis (visión apagada o falló)', () => {
    expect(esAnalisisDeImagen('[El cliente envio una foto]')).toBe(false);
    expect(partirMensaje('[El cliente envio una foto]')).toBeNull();
  });

  it('aguanta null, vacío y lo que no es texto', () => {
    for (const v of [null, undefined, '', 42, {}, []]) {
      expect(esAnalisisDeImagen(v)).toBe(false);
      expect(partirMensaje(v)).toBeNull();
    }
  });
});

describe('partir el mensaje', () => {
  it('separa el análisis del resto', () => {
    const r = partirMensaje(MENSAJE_REAL);
    expect(r.analisis).toBe(REAL);
    expect(r.pie).toBe('');
  });

  it('rescata el pie que escribió el cliente', () => {
    const r = partirMensaje(MENSAJE_CON_PIE);
    expect(r.pie).toBe('Mira como esta mi modem, la lucecita roja');
    expect(r.analisis).toBe(REAL);
  });

  it('el análisis NO se modifica al partirlo', () => {
    // Lo guardado y lo mostrado tienen que ser el mismo texto, carácter por
    // carácter: si acá se recortara algo, la bandeja mostraría una versión
    // distinta de la que leyó el modelo.
    expect(partirMensaje(MENSAJE_CON_PIE).analisis).toBe(REAL);
  });

  it('devuelve null si el rótulo está pero el análisis quedó vacío', () => {
    expect(partirMensaje('[Analisis automatico de la foto, no verificado]   ')).toBeNull();
  });
});

describe('resumir sin inventar', () => {
  it('resume el análisis real sin invertir las luces', () => {
    const r = resumir(REAL);
    // Dice que hay verdes…
    expect(r).toMatch(/verde/i);
    // …y que NO hay rojas ni naranjas. Esto es lo que no puede fallar.
    expect(r).toMatch(/sin luces/i);
    expect(r).not.toMatch(/luz roja visible|luces rojas visibles/i);
  });

  it('NUNCA afirma un color que el análisis niega', () => {
    const casos = [
      'No se observan luces rojas encendidas.',
      'No se ven luces rojas ni naranjas.',
      'No hay luces rojas en el equipo.',
      'No se aprecian luces rojas.'
    ];
    for (const c of casos) {
      const r = resumir(c);
      expect(r, c).not.toMatch(/luz roja visible|luces rojas visibles/i);
    }
  });

  it('sí afirma un color cuando el análisis lo afirma', () => {
    const r = resumir('Se observan dos luces verdes encendidas en el router.');
    expect(r).toMatch(/verde/i);
  });

  it('NO se come una luz roja escrita en masculino', () => {
    // El fallo real de la primera versión: el patrón buscaba sólo "roja/rojas"
    // y el análisis de una ONT dice "la luz LOS en rojo". El resumen salía
    // "ONT · luz verde visible" — un equipo con señal de falla presentado
    // como sano. Es el único error de este módulo que puede hacer daño.
    const r = resumir('Se ve una ONT con la luz LOS en rojo y POWER en verde.');
    expect(r).toMatch(/roja/i);
    expect(r).toMatch(/verde/i);
  });

  it('caza el rojo en todas sus formas', () => {
    for (const t of ['La luz está en rojo.', 'Hay una luz roja.',
                     'Dos indicadores rojos encendidos.',
                     'Se ven luces rojas.']) {
      expect(resumir(`Se ve un router. ${t}`), t).toMatch(/roja/i);
    }
  });

  it('el plural se escribe en plural', () => {
    const r = resumir('Se ve un router. No se observan luces rojas ni naranjas.');
    expect(r).toContain('sin luces rojas ni naranjas');
  });

  it('arrastra lo que no se pudo determinar', () => {
    const r = resumir('Se ve un router. No se distingue si la luz parpadea.');
    expect(r).toMatch(/no se distinguen/i);
  });

  it('nombra el equipo cuando el análisis lo nombra', () => {
    expect(resumir('Se ve una ONT con luces verdes.')).toMatch(/ONT/);
    expect(resumir('Se ve un router blanco.')).toMatch(/[Rr]outer/);
    expect(resumir('Se ve un módem con rejillas.')).toMatch(/[Mm]ódem/);
  });

  it('no nombra un equipo que el análisis no nombra', () => {
    const r = resumir('Se ve un gato sobre una mesa de madera.');
    expect(r).not.toMatch(/router|ONT|módem/i);
  });

  it('cuando no puede extraer nada, CITA en vez de inventar', () => {
    const texto = 'Se ve un gato sobre una mesa de madera. Nada más.';
    const r = resumir(texto);
    // La primera frase del original, literal.
    expect(texto).toContain(r.replace(/…$/, ''));
  });

  it('respeta el límite y no rompe el diseño', () => {
    const largo = 'Se ve un router. ' + 'texto larguísimo '.repeat(200);
    const r = resumir(largo, 110);
    expect(r.length).toBeLessThanOrEqual(110);
  });

  it('un análisis vacío da resumen vacío, no una frase inventada', () => {
    expect(resumir('')).toBe('');
    expect(resumir('   ')).toBe('');
    expect(resumir(null)).toBe('');
    expect(resumir(undefined)).toBe('');
  });

  it('el resumen siempre sale del original: no agrega diagnósticos', () => {
    // Palabras que el análisis no usa y el resumen no puede introducir.
    const r = resumir(REAL);
    for (const prohibida of ['dañado', 'roto', 'falla', 'avería', 'sin servicio',
                             'desconectado', 'no funciona']) {
      expect(r.toLowerCase(), prohibida).not.toContain(prohibida);
    }
  });
});
