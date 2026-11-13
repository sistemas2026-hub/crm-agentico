import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

/**
 * LA ESCENA NO CONOCE EL NEGOCIO, Y ESTO LO MIDE.
 *
 * Es el criterio A11 de la ficha, convertido en algo que se puede ejecutar. El
 * valor no es teórico: el día que alguien resuelva un caso particular metiendo
 * un `if` con el nombre de un sistema externo dentro de `oficina.ts`, la escena
 * deja de ser reutilizable para los otros siete departamentos y nadie se
 * entera hasta que haya que construir el segundo.
 *
 * POR QUÉ CON LÍMITES DE PALABRA, Y NO BUSCANDO LA CADENA SUELTA
 * El criterio escrito decía «`grep` no encuentra `isp`». Buscado así, marca
 * «disponible», «display» y «dispositivo»: la guarda se pondría roja por nada y
 * la primera reacción sería quitarla. Con `\bisp\b` busca la palabra y no la
 * sílaba. Es la diferencia entre una guarda que se respeta y una que se apaga.
 *
 * SOLO EL CÓDIGO DE LA ESCENA
 * Las propias pruebas sí nombran conceptos del negocio —tienen que, para montar
 * un caso— y por eso se excluyen. La guarda vigila lo que se ejecuta en
 * producción, que es donde el acoplamiento haría daño.
 */

const RAIZ = path.resolve('src/lib/centro-mando/escena');

/**
 * Las palabras que no pueden aparecer.
 *
 * Son las del criterio más dos que se agregaron al escribirlo: el nombre de los
 * sistemas externos. Si uno de ellos llega a la escena, lo que está roto no es
 * una palabra: es que la oficina virtual pasó a depender de con qué integra
 * esta empresa en concreto.
 */
const PROHIBIDAS = [
  'wisphub',
  'smartolt',
  'bottlecrm',
  'ticket',
  'herramienta',
  'isp',
  'rapilink',
  'factura',
  'suscriptor'
];

function fuentesDeLaEscena() {
  return readdirSync(RAIZ)
    .filter((f) => /\.(ts|js)$/.test(f) && !f.endsWith('.test.js') && !f.endsWith('.test.ts'))
    .map((f) => ({ archivo: f, texto: readFileSync(path.join(RAIZ, f), 'utf8') }));
}

describe('la escena no conoce el negocio', () => {
  const fuentes = fuentesDeLaEscena();

  it('hay archivos que vigilar (si no, la guarda no prueba nada)', () => {
    // Una guarda que recorre una carpeta vacía pasa siempre. Es la trampa de
    // «una prueba que dice que algo existe no prueba que funcione», aplicada a
    // la prueba misma.
    expect(fuentes.length).toBeGreaterThanOrEqual(7);
  });

  for (const palabra of PROHIBIDAS) {
    it(`no aparece «${palabra}»`, () => {
      const re = new RegExp(`\\b${palabra}\\b`, 'i');
      const culpables = fuentes.filter((f) => re.test(f.texto)).map((f) => f.archivo);
      expect(culpables, `aparece en: ${culpables.join(', ')}`).toEqual([]);
    });
  }

  it('la guarda se pondría roja si la palabra estuviera', () => {
    // La mutación, hecha explícita: con un texto que SÍ la contiene, el mismo
    // control la encuentra. Sin esto, no habría forma de distinguir «no está»
    // de «la expresión no busca nada».
    const re = new RegExp('\\bherramienta\\b', 'i');
    expect(re.test('const nombreDeLaHerramienta = 1')).toBe(false);
    expect(re.test('// la herramienta que se llamó')).toBe(true);
  });
});

describe('ninguna prueba de la escena queda fuera del corredor', () => {
  it('no hay archivos .test.ts: vitest sólo recoge *.test.js y no avisa', () => {
    //  `vitest.config.js` tiene `include: ['src/**/*.test.js']`. Una prueba
    //  escrita como `.test.ts` NO CORRE, y no da error ni advertencia: sale
    //  verde porque no existe. Pasó el 01/11/2026 con `rotulos.test.ts`, que
    //  se dio por pasada sin haberse ejecutado nunca.
    //
    //  Es exactamente lo que CLAUDE.md §6 llama «código construido no es
    //  código que corre», aplicado a una prueba.
    const sueltas = readdirSync(RAIZ).filter((f) => f.endsWith('.test.ts'));
    expect(sueltas, 'renombralas a .test.js o ampliá el include').toEqual([]);
  });
});

describe('la escena no importa el motor gráfico donde no debe', () => {
  const fuentes = fuentesDeLaEscena();

  it('los módulos puros no importan pixi', () => {
    // Si `camara.ts`, `pose.ts`, `isometria.ts` o `adaptador.ts` importaran
    // PixiJS, dejarían de poder probarse en Node — y son justo los cuatro que
    // concentran las decisiones. El día que uno lo importe, lo que se pierde no
    // es la pureza: son las pruebas.
    const puros = ['camara.ts', 'pose.ts', 'isometria.ts', 'adaptador.ts', 'paleta.ts',
                   'rotulos.ts'];
    for (const nombre of puros) {
      const f = fuentes.find((x) => x.archivo === nombre);
      expect(f, `falta ${nombre}`).toBeTruthy();
      expect(/from\s+['"]pixi\.js['"]/.test(f.texto), `${nombre} importa pixi`).toBe(false);
    }
  });

  it('y los que sí lo usan son los esperados', () => {
    //  ESTA LISTA ES LA SUPERFICIE DE ACOPLAMIENTO CON EL MOTOR GRÁFICO, y por
    //  eso se escribe a mano: es lo que habría que reescribir el día que el
    //  motor cambie, y tiene que doler agregarle un archivo.
    //
    //  Pasó de cuatro a seis el 31/10/2026, con la reconstrucción
    //  arquitectónica: `volumen.ts` son los primitivos que salieron de
    //  `oficina.ts` para no copiar el signo de la luz, y `arquitectura.ts` es
    //  la envolvente de la sede. Las dos dibujan, así que las dos importan el
    //  motor; ninguna decisión se mudó ahí.
    const conPixi = fuentes
      .filter((f) => /from\s+['"]pixi\.js['"]/.test(f.texto))
      .map((f) => f.archivo)
      .sort();
    expect(conPixi).toEqual([
      'arquitectura.ts',
      'caminante.ts', 'montar.ts', 'oficina.ts', 'personaje.ts',
      'texturas.ts', 'volumen.ts'
    ]);
  });
});
