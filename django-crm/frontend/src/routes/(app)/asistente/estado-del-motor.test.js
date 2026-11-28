import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * EL ASISTENTE DICE SI HAY CON QUIÉN HABLAR ANTES DE ESCRIBIR  --  12/11/2026
 *
 * Atraviesa el load con el motor doblado y afirma sobre `estado`, que es lo que
 * la página convierte en aviso y en cuadro deshabilitado.
 */
const m = vi.hoisted(() => ({ env: /** @type {any} */ ({}), tenant: /** @type {any} */ (null) }));
vi.mock('$env/dynamic/private', () => ({ env: m.env }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => m.tenant }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));

const modulo = await import('./+page.server.js');
const { _PLAZO_ASISTENTE_MS } = modulo;
/** @type {(e: any) => Promise<any>} */
const load = /** @type {any} */ (modulo.load);

/** @param {(url: string) => any} responder @param {string} [rol] */
const ev = (responder, rol = 'USER') =>
  /** @type {any} */ ({
    locals: { profile: { role: rol } },
    fetch: async (/** @type {string} */ url, /** @type {any} */ init) => {
      const r = responder(String(url));
      if (r === 'colgado') {
        return new Promise((_, rechazar) =>
          init?.signal?.addEventListener('abort', () => rechazar(new Error('abortado')))
        );
      }
      if (r instanceof Error) throw r;
      return { ok: true, status: 200, json: async () => r };
    }
  });

beforeEach(() => {
  m.env.PRIVATE_ASISTENTE_URL = 'http://motor';
  m.tenant = 'demo';
});

describe('estado del asistente', () => {
  it('sin asistente desplegado lo dice sin preguntarle nada al motor', async () => {
    delete m.env.PRIVATE_ASISTENTE_URL;
    const d = await load(ev(() => { throw new Error('no debía preguntar'); }));
    expect(d.estado).toBe('sin_instalacion');
  });

  it('sin empresa confirmada lo dice', async () => {
    m.tenant = null;
    expect((await load(ev(() => ({})))).estado).toBe('sin_empresa');
  });

  it('con el motor caído es «sin respuesta», no una página vacía que finge estar lista', async () => {
    expect((await load(ev(() => new Error('ECONNREFUSED'))))).toMatchObject({
      estado: 'sin_respuesta',
      fotoHabilitada: false
    });
  });

  it('con el motor colgado no retiene la página más que el plazo', async () => {
    vi.useFakeTimers();
    try {
      const p = load(ev(() => 'colgado'));
      await vi.advanceTimersByTimeAsync(_PLAZO_ASISTENTE_MS + 10);
      expect((await p).estado).toBe('sin_respuesta');
    } finally {
      vi.useRealTimers();
    }
  });

  it('con el motor arriba está listo, con foto y agentes para un ADMIN', async () => {
    const d = await load(
      ev(
        (url) =>
          url.includes('/agentes')
            ? { agentes: [{ nombre: 'soporte', area: 'Soporte', cargo: 'Técnico', prompt: 'no viaja' }] }
            : { habilitada: true },
        'ADMIN'
      )
    );
    expect(d).toEqual({
      estado: 'listo',
      puedeElegir: true,
      fotoHabilitada: true,
      agentes: [{ nombre: 'soporte', area: 'Soporte', cargo: 'Técnico' }]
    });
  });
});
