import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

/**
 * PEDIR LOS MISMOS DATOS DOS VECES, PARA NO ENTERARSE DE NADA.
 *
 * Medido en una grabacion del cliente el 14/10/2026: al apretar «Ejecutar
 * ciclo», la pantalla disparaba DOS peticiones a '__data.json' en paralelo --
 * 20,3 s y 19,9 s-- mas la recarga de la pagina en 18,6 s.
 *
 * La causa: 'update()' de SvelteKit YA recarga los datos de la pagina, y
 * encima se llamaba a 'invalidateAll()'. Dos veces lo mismo.
 *
 * Y lo peor es que ninguna de las dos servia: el ciclo se ENCOLA y tarda seis
 * minutos, asi que lo que traian era la bandeja de antes. La persona miraba
 * una pantalla trabada cuarenta segundos para ver exactamente lo que ya tenia.
 *
 * LO QUE MIDE: que en el mismo manejador no convivan las dos llamadas. No es
 * "presencia del mecanismo": cada par ES una peticion de veinte segundos de
 * mas, que es lo que se vio en la grabacion.
 */

const PANEL = new URL('../../routes/(app)/supervisor-noc/+page.svelte', import.meta.url).pathname
  .replace(/^\/([A-Za-z]:)/, '$1');

const codigo = readFileSync(PANEL, 'utf8').replace(/\/\/.*$/gm, '');

describe('no se piden los mismos datos dos veces', () => {
  it('ningun manejador llama a update() y a invalidateAll() seguidos', () => {
    //  El patron exacto que costo los 40 segundos, con lo que haya en medio
    //  salvo otra llave de cierre (que indicaria otro manejador).
    const seguidos = codigo.match(/await update\([^)]*\);[^}]*?await invalidateAll\(\)/g);
    expect(seguidos ?? [], 'update() ya recarga: el invalidateAll de atras es '
      + 'una segunda consulta de ~20 s que trae lo mismo').toEqual([]);
  });

  it('el ciclo no refresca al instante, porque todavia no hay nada que traer', () => {
    //  El ciclo tarda ~6 minutos. Refrescar al volver del acuse solo trae la
    //  bandeja de antes y deja la pantalla trabada mientras tanto.
    const manejador = codigo.slice(codigo.indexOf('const alCorrerCiclo'),
                                   codigo.indexOf('const alCorrerAsistente'));
    expect(manejador).not.toMatch(/await invalidateAll\(\)/);
    expect(manejador, 'sin esto la bandeja nunca muestra lo que el ciclo hizo')
      .toMatch(/traerLoDelCiclo\(\)/);
  });
});
