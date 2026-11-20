/**
 * EL SONDEO NO PUEDE PERDER EL ORIGEN.
 *
 * Visto en produccion el 22/09/2026: un mensaje que entra mientras alguien
 * mira la conversacion se dibujaba como «ORIGEN NO REGISTRADO» -- la etiqueta
 * reservada a las filas anteriores al registro de origen. Los mismos mensajes,
 * despues de recargar, salian bien.
 *
 * La causa es estructural y por eso esta prueba mira el CABLE: el hilo se
 * llena por DOS caminos --el `load` de la pagina y el sondeo-- y cada uno pasa
 * por su propia ruta. El `load` trae la fila entera; el sondeo pasaba por la
 * ruta que se escribio para TICKETS, que remapea los campos a {quien, texto} y
 * dejaba `origen` afuera.
 *
 * Dos caminos al mismo hilo: lo que uno traiga, el otro tambien.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
const proxy = leer('../../routes/api/conversaciones/[id]/mensajes/+server.js');
const pagina = leer('../../routes/(app)/conversaciones/[id]/+page.svelte');

describe('los dos caminos al hilo traen lo mismo', () => {
  it('la ruta del sondeo reenvia el origen y el nombre del autor', () => {
    expect(proxy, 'sin origen, todo lo que entre en vivo dice «no registrado»')
      .toMatch(/origen:\s*m\.origen/);
    expect(proxy, 'y sin autor_nombre una respuesta humana pierde de quien fue')
      .toMatch(/autor_nombre:\s*m\.autor_nombre/);
  });

  it('el origen se reenvia TAL CUAL, sin deducirlo de «quien»', () => {
    /* `quien` sale de `rol`, y `rol = assistant` cubre por igual a la IA y a
       una persona -- que es justo la distincion que D30 existe para sostener.
       Deducir el origen de ahi reintroduciria por la puerta lateral lo que el
       contrato prohibe: afirmar una autoria que no se midio. */
    const linea = proxy.match(/origen:[^\n]*/)?.[0] ?? '';
    expect(linea).not.toMatch(/quien/);
    expect(linea, 'NULL se devuelve NULL: no se rellena').toMatch(/\?\?\s*null/);
  });

  it('el sondeo no pisa el origen al traducir la forma', () => {
    /* La pagina hace `{...crudo, rol, contenido}`: el spread conserva lo que
       venga, asi que basta con que la ruta lo mande. Si alguien cambiara el
       spread por una lista de campos, el origen se perderia de nuevo y sin
       que nada falle. */
    const bloque = pagina.slice(pagina.indexOf('async function sondearMensajesNuevos'));
    expect(bloque.slice(0, 2000)).toMatch(/\.\.\.crudo/);
  });
});
