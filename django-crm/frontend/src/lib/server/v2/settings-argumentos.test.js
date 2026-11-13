import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

/**
 * QUE NADIE LLAME SIN ARGUMENTOS A UNA FUNCION QUE LOS NECESITA
 * ==============================================================
 *
 * EL DEFECTO, medido en produccion el 07/10/2026
 * -----------------------------------------------
 * En 'getSettingsHub' habia OCHO llamadas asi:
 *
 *     leerConfiguracionAsistente(),      // la firma es (locals, fetch)
 *     leerOferta(),
 *     leerGuiasTV(),
 *     ...
 *
 * Sin 'locals' no hay tenant, sin tenant no hay destino, y cada una devolvia
 * null por su propio catch. La pantalla de Ajustes perdia las tarjetas que
 * dependen del asistente -- "Servicios y canales" (la parrilla de TV) y
 * "Planes de venta" (las localidades) ni se dibujaban, porque su condicion es
 * que el tenant tenga el rol 'ventas' y la lista de roles llegaba vacia.
 *
 * POR QUE NO SE VEIA
 * -------------------
 * Los catch estan para que el motor caido no tumbe el hub entero, y eso sigue
 * siendo correcto. Pero producen EL MISMO sintoma que una llamada mal escrita
 * --todo en null-- asi que el defecto se veia igual que una degradacion
 * normal. Un error que se disfraza de comportamiento esperado no lo encuentra
 * nadie mirando la pantalla.
 *
 * POR QUE ESTA PRUEBA LEE EL CODIGO
 * ----------------------------------
 * Porque el defecto no esta en lo que las funciones HACEN sino en como se las
 * LLAMA, y eso ninguna prueba de comportamiento lo toca: cada funcion anda
 * perfecto cuando se la prueba sola. La lista de funciones se DERIVA de los
 * modulos importados, no se escribe a mano: una lista fija se desactualiza y
 * la proxima funcion con esa firma volveria a pasar.
 */

const aqui = dirname(fileURLToPath(import.meta.url));
const CRUDO = readFileSync(resolve(aqui, 'settings.js'), 'utf8');

/** Sin comentarios: un nombre citado en una nota no es una llamada.
 *  Sin esto, '// ver contarPlanesVenta()' se contaba como defecto. */
const FUENTE = CRUDO
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/\/\/.*/g, '');

/** Las funciones exportadas de este directorio cuya firma empieza con 'locals'. */
function exigenContexto() {
  const modulos = [...FUENTE.matchAll(/from '\.\/([\w-]+\.js)'/g)].map((m) => m[1]);
  const encontradas = new Map();
  for (const mod of modulos) {
    const ruta = resolve(aqui, mod);
    if (!existsSync(ruta)) continue;
    const txt = readFileSync(ruta, 'utf8');
    for (const m of txt.matchAll(/export (?:async )?function (\w+)\(\s*locals\b/g)) {
      encontradas.set(m[1], mod);
    }
  }
  return encontradas;
}

describe('settings.js pasa el contexto a quien lo necesita', () => {
  const exigen = exigenContexto();

  it('hay funciones con esa firma para vigilar', () => {
    //  Si esto da cero, la prueba no esta midiendo nada -- cambio el patron de
    //  los modulos y hay que revisarla, no borrarla.
    expect(exigen.size).toBeGreaterThan(0);
  });

  it('EL EFECTO: ninguna se llama con los parentesis vacios', () => {
    const vacias = [];
    for (const [fn, mod] of exigen) {
      //  'fn()' con nada adentro. Se excluye la definicion misma buscando
      //  solo donde NO viene precedida de 'function'.
      //  Se arma por concatenacion y NO con un template literal: ahi \( no es
      //  un escape valido y JavaScript lo colapsa a '(', dejando un patron que
      //  no matchea nada. Paso exactamente eso al escribir esta prueba: daba
      //  verde sin medir, y solo se vio porque la mutacion no la mataba.
      const re = new RegExp('(?<!function )\\b' + fn + '\\(\\s*\\)', 'g');
      if (re.test(FUENTE)) vacias.push(`${fn}()  (definida en ${mod}, espera locals y fetch)`);
    }
    expect(vacias, 'sin locals no hay tenant, y estas devolverian null en silencio')
      .toEqual([]);
  });

  it('y las que se llaman reciben locals Y fetch, no solo uno', () => {
    const incompletas = [];
    for (const fn of exigen.keys()) {
      const re = new RegExp('(?<!function )\\b' + fn + '\\(([^)]*)\\)', 'g');
      for (const m of FUENTE.matchAll(re)) {
        const args = m[1].trim();
        if (args && !args.includes(',')) incompletas.push(`${fn}(${args})`);
      }
    }
    //  'fetch' solo es opcional cuando 'locals.tenant' ya esta resuelto, y
    //  eso no se puede garantizar desde aca: pedir los dos es lo barato.
    expect(incompletas).toEqual([]);
  });
});
