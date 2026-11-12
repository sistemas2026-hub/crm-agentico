import { describe, it, expect, vi } from 'vitest';

/**
 * Los usos de una habilidad llegan a la pantalla (12/11/2026). La tabla solo
 * decía «N usos»; el motor ya sabe en qué conversaciones se cargó y si escaló
 * igual. Este intermediario es el salto que ninguna prueba del motor ve: si
 * pegara contra otro endpoint, o dejara pasar un id que cambia la ruta, la
 * pantalla quedaría vacía o leería otra cosa sin ningún error.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'empresa' })
}));

const { GET } = await import('./+server.js');

const ID = '0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0';
const RESPUESTA_MOTOR = {
  usos: 3, usos_reales: 2, escalo_igual_reales: 1,
  detalle: [{ conversation_id: 'c1', rol: 'soporte', canal: 'whatsapp', escalo: true, real: true }]
};

function evento(query, rol = 'ADMIN') {
  const fetch = vi.fn(async (/** @type {any} */ _url, /** @type {any} */ _init) => new Response(JSON.stringify(RESPUESTA_MOTOR), { status: 200 }));
  return {
    fetch,
    ev: /** @type {any} */ ({
      url: new URL(`http://crm/api/habilidades${query}`),
      locals: { user: { id: 'u' }, profile: { role: rol } },
      fetch
    })
  };
}

describe('GET /api/habilidades?usos=<id>', () => {
  it('pide los usos de ESA habilidad al motor, con el tenant de la sesión', async () => {
    const { fetch, ev } = evento(`?usos=${ID}`);
    const r = await GET(ev);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe(`http://motor/habilidades/${ID}/usos?tenant=empresa`);
    const cuerpo = await r.json();
    // Lo que recibe la página: los totales y el «escaló igual» de cada uso.
    expect(cuerpo.escalo_igual_reales).toBe(1);
    expect(cuerpo.detalle[0].escalo).toBe(true);
  });

  it('un id que no es UUID no llega al motor (cambiaría la ruta)', async () => {
    const { fetch, ev } = evento('?usos=..%2F..%2Fconfiguracion');
    const r = await GET(ev);
    expect(r.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('quien no es administrador no los ve', async () => {
    const { fetch, ev } = evento(`?usos=${ID}`, 'USER');
    const r = await GET(ev);
    expect(r.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('sin usos sigue listando las habilidades', async () => {
    const { fetch, ev } = evento('');
    await GET(ev);
    expect(fetch.mock.calls[0][0]).toBe('http://motor/habilidades?tenant=empresa');
  });
});

describe('la pantalla enlaza la evidencia, leído del código', () => {
  // El harness no compila .svelte: se fija que la página arme los enlaces.
  it('cada conversación de la evidencia y de los usos lleva a /conversaciones/<id>', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const pagina = readFileSync(
      fileURLToPath(new URL('../../(app)/habilidades/+page.svelte', import.meta.url)), 'utf-8');
    expect(pagina).toMatch(/each h\.evidencia\.conversaciones as cid/);
    expect(pagina).toMatch(/href="\/conversaciones\/\{cid\}"/);
    expect(pagina).toMatch(/href="\/conversaciones\/\{u\.conversation_id\}"/);
    expect(pagina).toMatch(/\/api\/habilidades\?usos=/);
  });
});
