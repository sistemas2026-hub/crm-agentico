/**
 * LOS DOS `init` DE SENTRY QUEDAN COMO DICE EL CONTRATO, Y LAS PANTALLAS CON
 * DATOS QUEDAN MARCADAS.
 *
 * Que exista el modulo de privacidad no prueba que este conectado: aqui se
 * importan hooks.client.js e instrumentation.server.js con el SDK sustituido
 * y se afirma sobre las opciones con las que llaman a Sentry.init(). Si
 * alguien vuelve a poner sendDefaultPii: true o quita un gancho, esto se pone
 * rojo sin necesitar un DSN.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, describe, expect, it, vi } from 'vitest';

const llamadas = [];

vi.mock('@sentry/sveltekit', () => ({
  init: (opts) => { llamadas.push(opts); },
  replayIntegration: (opts) => ({ name: 'Replay', opts }),
  handleErrorWithSentry: () => () => {},
  sentryHandle: () => async ({ event, resolve }) => resolve(event)
}));

let cliente;
let servidor;

beforeAll(async () => {
  await import('../../hooks.client.js');
  cliente = llamadas[0];
  await import('../../instrumentation.server.js');
  servidor = llamadas[1];
});

describe('hooks.client.js', () => {
  it('nunca datos personales por defecto', () => {
    expect(cliente.sendDefaultPii).toBe(false);
  });
  it('sin DSN, apagado', () => {
    expect(cliente.enabled).toBe(false);
  });
  it('los cuatro ganchos de limpieza estan conectados', () => {
    for (const g of ['beforeSend', 'beforeBreadcrumb', 'beforeSendTransaction', 'beforeSendLog']) {
      expect(typeof cliente[g], g).toBe('function');
    }
  });
  it('y son los del modulo de privacidad, no otros', async () => {
    const p = await import('./privacidad.js');
    expect(cliente.beforeSend).toBe(p.limpiarEvento);
    expect(cliente.beforeBreadcrumb).toBe(p.limpiarMiga);
    expect(cliente.beforeSendTransaction).toBe(p.limpiarTransaccion);
    expect(cliente.beforeSendLog).toBe(p.limpiarLog);
    expect(cliente.ignoreErrors).toBe(p.ERRORES_IGNORADOS);
  });
  it('el replay lleva las opciones de privacidad', async () => {
    const p = await import('./privacidad.js');
    const replay = cliente.integrations.find((i) => i.name === 'Replay');
    expect(replay.opts).toBe(p.OPCIONES_REPLAY);
    expect(replay.opts.maskAllText).toBe(true);
    expect(replay.opts.block).toContain('[data-privado]');
  });
});

describe('instrumentation.server.js', () => {
  it('mismo contrato que el cliente', async () => {
    const p = await import('./privacidad.js');
    expect(servidor.sendDefaultPii).toBe(false);
    expect(servidor.enabled).toBe(false);
    expect(servidor.beforeSend).toBe(p.limpiarEvento);
    expect(servidor.beforeBreadcrumb).toBe(p.limpiarMiga);
    expect(servidor.beforeSendTransaction).toBe(p.limpiarTransaccion);
    expect(servidor.beforeSendLog).toBe(p.limpiarLog);
  });
});

describe('las pantallas con datos de clientes estan marcadas para el replay', () => {
  const raiz = path.resolve('./src');
  const marcados = [
    ['routes/(app)/+layout.svelte', 'v2-main'],
    ['routes/(app)/conversaciones/+layout.svelte', 'mesa bandeja'],
    ['routes/(app)/instalaciones/+page.svelte', 'hoja'],
    ['routes/(no-layout)/solicitud/[token]/+page.svelte', 'hoja'],
    ['lib/conversaciones/composer/MessageComposer.svelte', 'textarea']
  ];
  for (const [archivo, pista] of marcados) {
    it(`${archivo} (${pista})`, () => {
      const texto = readFileSync(path.join(raiz, archivo), 'utf8');
      expect(texto).toContain('data-privado');
    });
  }
});
