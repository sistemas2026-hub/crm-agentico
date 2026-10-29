/**
 * El eco de lo que ESTA pestaña acaba de enviar (29/10/2026).
 *
 * Lo que protege: que quien responde vea su mensaje UNA vez, y firmado. Visto
 * en producción: «muchas gracias ya procedemos con el cambio» salía dos veces
 * en el mismo minuto, una como «Origen no registrado» sin palomitas y otra como
 * ADMIN con ✓✓. El operador lee eso como que al cliente le llegó doble.
 *
 * Las aserciones que importan son las negativas: un eco reconocido NO puede
 * sumar una fila, y la burbuja local NO puede quedarse sin el origen y el
 * estado de entrega que el motor ya sabe.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { incorporarMensaje } from './eco_local.js';

const AHORA = Date.parse('2026-10-29T18:43:30Z');

/** @returns {any} */
const local = (extra = {}) => ({
  rol: 'assistant',
  origen: 'humano',
  contenido: 'muchas gracias ya procedemos con el cambio',
  creado_en: '2026-10-29T18:43:00Z',
  clave_idempotencia: 'c1',
  sinEntregar: null,
  ...extra
});

/** @returns {any} */
const remoto = (extra = {}) => ({
  id: 'm-9',
  rol: 'assistant',
  origen: 'humano',
  autor_nombre: 'admin',
  contenido: 'muchas gracias ya procedemos con el cambio',
  creado_en: '2026-10-29T18:43:02Z',
  estado_entrega: 'entregado',
  clave_idempotencia: 'c1',
  ...extra
});

describe('la burbuja local y su fila en la base', () => {
  it('se reconocen por la clave y quedan en UNA sola', () => {
    const hilo = [local()];
    expect(incorporarMensaje(hilo, remoto(), AHORA)).toBe('reconciliado');
    expect(hilo).toHaveLength(1);
  });

  it('por la clave aunque hayan pasado más de 15 segundos', () => {
    // El caso de producción: el envío espera a que WhatsApp confirme, y el
    // sondeo trae la fila cuando la ventana de rol + texto ya se cerró.
    const hilo = [local()];
    const muchoDespues = AHORA + 5 * 60_000;
    expect(incorporarMensaje(hilo, remoto(), muchoDespues)).toBe('reconciliado');
    expect(hilo).toHaveLength(1);
  });

  it('la burbuja toma lo que sabe la base: id, autor y entrega', () => {
    const hilo = [local()];
    incorporarMensaje(hilo, remoto(), AHORA);
    expect(hilo[0].id).toBe('m-9');
    expect(hilo[0].autor_nombre).toBe('admin');
    expect(hilo[0].estado_entrega).toBe('entregado');
  });

  it('y no pierde el aviso de que no salió', () => {
    const hilo = [local({ sinEntregar: 'Ventana de 24 h cerrada' })];
    incorporarMensaje(hilo, remoto({ estado_entrega: null }), AHORA);
    expect(hilo[0].sinEntregar).toBe('Ventana de 24 h cerrada');
  });

  it('una vez reconciliada, el siguiente sondeo no la vuelve a sumar', () => {
    const hilo = [local()];
    incorporarMensaje(hilo, remoto(), AHORA);
    expect(incorporarMensaje(hilo, remoto(), AHORA + 3000)).toBe('repetido');
    expect(hilo).toHaveLength(1);
  });
});

describe('lo que NO es un eco', () => {
  it('el mismo texto con otra clave es otro mensaje', () => {
    // Dos respuestas iguales seguidas son dos envíos: juntarlas escondería
    // que el cliente recibió dos.
    const hilo = [local()];
    expect(incorporarMensaje(hilo, remoto({ clave_idempotencia: 'c2' }), AHORA)).toBe('nuevo');
    expect(hilo).toHaveLength(2);
  });

  it('una fila que ya tiene id no se pisa', () => {
    const hilo = [{ ...remoto(), id: 'm-1', clave_idempotencia: 'c1' }];
    expect(incorporarMensaje(hilo, remoto({ id: 'm-2', clave_idempotencia: 'c9' }), AHORA))
      .toBe('nuevo');
    expect(hilo[0].id).toBe('m-1');
  });

  it('un mensaje sin id no entra', () => {
    const hilo = [];
    expect(incorporarMensaje(hilo, remoto({ id: undefined }), AHORA)).toBe('ignorado');
    expect(hilo).toHaveLength(0);
  });
});

describe('las burbujas locales sin clave', () => {
  const sinClave = (extra = {}) => local({ rol: 'user', origen: undefined, clave_idempotencia: undefined, ...extra });

  it('se reconocen por rol y texto si es reciente', () => {
    const hilo = [sinClave()];
    const alRato = Date.parse('2026-10-29T18:43:05Z');
    expect(incorporarMensaje(hilo, remoto({ rol: 'user', origen: 'cliente', clave_idempotencia: null }), alRato))
      .toBe('reconciliado');
    expect(hilo).toHaveLength(1);
    expect(hilo[0].origen).toBe('cliente');
  });

  it('pasada la ventana, no se adivina', () => {
    const hilo = [sinClave()];
    expect(incorporarMensaje(hilo, remoto({ rol: 'user', clave_idempotencia: null }), AHORA + 60_000))
      .toBe('nuevo');
  });
});

describe('la pantalla usa esto, leído del código', () => {
  // Test de texto por lo mismo que t6_cableado.test.js: el harness no compila
  // un .svelte. Sin esto, la función de arriba podría estar en verde y la
  // pantalla seguir con la comparación de 15 segundos.
  const pagina = readFileSync(
    fileURLToPath(new URL('../../routes/(app)/conversaciones/[id]/+page.svelte', import.meta.url)),
    'utf-8'
  );

  it('el sondeo pasa por incorporarMensaje', () => {
    const sondeo = pagina.slice(pagina.indexOf('async function sondearMensajesNuevos'));
    expect(sondeo.slice(0, 2500)).toMatch(/incorporarMensaje\(mensajes, m, ahora\)/);
    expect(pagina).not.toMatch(/esEcoDeOptimista/);
  });

  it('la burbuja humana nace con su origen', () => {
    const burbuja = pagina.slice(pagina.indexOf('const burbuja = {'));
    expect(burbuja.slice(0, 600)).toMatch(/origen:\s*'humano'/);
  });
});
