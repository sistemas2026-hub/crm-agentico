import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { filtrosDeLaCola, sinLosFiltros, FILTROS_QUE_RECORTAN } from './filtros-de-la-cola.js';

const en = (query) => new URL(`https://x/tickets${query}`);

describe('que esta recortando la cola', () => {
  it('sin parametros no hay nada que avisar', () => {
    expect(filtrosDeLaCola(en('')).hay).toBe(false);
  });

  //  EL DEFECTO QUE ORIGINO ESTE MODULO, DEL LADO DEL FALSO POSITIVO.
  //  La pantalla miraba 'url.search' -- la query string entera -- asi que
  //  elegir un area, pasar de pagina o cambiar el orden disparaba "estos
  //  numeros describen la cola filtrada" sin que nada estuviera filtrado.
  it('elegir un area no es filtrar la cola', () => {
    expect(filtrosDeLaCola(en('?area=soporte_tecnico')).hay).toBe(false);
  });

  it('la vista, el orden, la pagina y el tamano tampoco recortan', () => {
    const u = en('?area=cartera&vista=mios&orden=recientes&offset=50&limit=100&all=1');
    expect(filtrosDeLaCola(u).hay).toBe(false);
  });

  //  Y DEL LADO DEL FALSO NEGATIVO: esto es lo que el usuario vio.
  it('una busqueda recorta, y se dice cual', () => {
    const r = filtrosDeLaCola(en('?search=mario'));
    expect(r.hay).toBe(true);
    expect(r.busqueda).toBe('mario');
  });

  it('un buscador enviado vacio no es un filtro', () => {
    expect(filtrosDeLaCola(en('?search=')).hay).toBe(false);
    expect(filtrosDeLaCola(en('?search=%20%20')).hay).toBe(false);
  });

  //  Lo mismo para los selectores de la barra: enviada sin elegir nada, cada
  //  uno deja su clave con valor vacio. Si la PRESENCIA de la clave contara,
  //  abrir y cerrar el filtro sin tocar nada dejaria el aviso puesto -- y un
  //  aviso que sale cuando no pasa nada es el que se aprende a ignorar.
  //  (Esta mutacion sobrevivia el 06/11/2026: 'p.has(clave)' pasaba la suite.)
  it('un selector de la barra enviado vacio no es un filtro', () => {
    expect(filtrosDeLaCola(en('?priority=&assigned_to=&tags=')).hay).toBe(false);
    expect(filtrosDeLaCola(en('?priority=%20')).hay).toBe(false);
  });

  it('los filtros de la barra tambien recortan, por su nombre visible', () => {
    const r = filtrosDeLaCola(en('?priority=high&assigned_to=7'));
    expect(r.hay).toBe(true);
    expect(r.otros).toEqual(['responsable', 'prioridad']);
    expect(r.busqueda).toBe('');
  });

  it('un filtro repetible se nombra una sola vez', () => {
    expect(filtrosDeLaCola(en('?tags=a&tags=b')).otros).toEqual(['etiqueta']);
  });

  //  Lo que deja el selector de etiquetas: una opcion vacia primero y la
  //  elegida despues. Mirar solo la PRIMERA ('get' en vez de 'getAll') lee ''
  //  y no avisa de un filtro que si esta recortando.
  it('un repetible cuyo primer valor es vacio igual recorta', () => {
    expect(filtrosDeLaCola(en('?tags=&tags=soporte')).hay).toBe(true);
  });

  it('la busqueda y los demas se avisan juntos', () => {
    const r = filtrosDeLaCola(en('?search=mario&priority=high'));
    expect(r.busqueda).toBe('mario');
    expect(r.otros).toEqual(['prioridad']);
  });

  it('una url sin searchParams no rompe la pantalla', () => {
    expect(filtrosDeLaCola(undefined).hay).toBe(false);
    expect(filtrosDeLaCola({}).hay).toBe(false);
  });
});

describe('la salida del filtro', () => {
  it('quita lo que recorta y conserva donde estabas parado', () => {
    const salida = sinLosFiltros(en('?area=cartera&vista=mios&orden=recientes&search=mario&priority=high'));
    const p = new URL(`https://x${salida}`).searchParams;
    expect(p.get('search')).toBe(null);
    expect(p.get('priority')).toBe(null);
    expect(p.get('area')).toBe('cartera');
    expect(p.get('vista')).toBe('mios');
    expect(p.get('orden')).toBe('recientes');
  });

  //  Quitar el filtro agranda la cola: la pagina 4 de la cola vieja es otro
  //  lugar. Se vuelve al principio.
  it('vuelve al principio de la cola', () => {
    const salida = sinLosFiltros(en('?search=mario&offset=75'));
    expect(new URL(`https://x${salida}`).searchParams.get('offset')).toBe(null);
  });

  it('sin nada que quitar deja la ruta limpia, sin ? colgando', () => {
    expect(sinLosFiltros(en('?search=mario'))).toBe('/tickets');
  });
});

//  LA GUARDA QUE IMPIDE QUE LAS DOS LISTAS SE SEPAREN EN SILENCIO.
//  Un filtro agregado a FILTER_FIELDS viaja a las dos consultas y recorta las
//  tarjetas; si no esta aca, recorta sin avisar -- que es exactamente el
//  defecto que este modulo cierra, reaparecido por otra puerta.
//  Se lee el archivo como texto a proposito: importar lib/server trae
//  '$env/dynamic/public' y la guarda pasaria a depender del bundler.
describe('no se separa de FILTER_FIELDS', () => {
  it('todo filtro que el cargador manda al API tiene su aviso', () => {
    const fuente = readFileSync(
      fileURLToPath(new URL('../server/v2/tickets.js', import.meta.url)), 'utf8');
    const linea = /export const FILTER_FIELDS = \[([^\]]*)\]/.exec(fuente);
    expect(linea, 'FILTER_FIELDS cambio de forma en tickets.js').not.toBe(null);
    const campos = [...linea[1].matchAll(/'([^']+)'/g)].map((m) => m[1]);
    expect(campos.length).toBeGreaterThan(0);
    for (const campo of campos) expect(FILTROS_QUE_RECORTAN).toContain(campo);
  });
});
