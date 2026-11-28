import { describe, it, expect, vi } from 'vitest';

/**
 * «Convertir en caso dorado» (12/11/2026). El motor arma el caso desde la
 * traza; este intermediario es el salto que ninguna prueba del motor ve: si
 * pegara a otra ruta, dejara pasar un id que cambia el camino, o dejara caer
 * los avisos, la pantalla mostraría otra cosa sin ningún error.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));

const { GET } = await import('./+server.js');

const ID = '0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0';
const YAML = '  - nombre: desde conversacion real\n    manual: true\n';

function evento(query, { rol = 'ADMIN', status = 200, cuerpo = null } = {}) {
  const fetch = vi.fn(async (/** @type {any} */ _url, /** @type {any} */ _init) => new Response(JSON.stringify(cuerpo ?? {
    caso_dorado: YAML, avisos: ['un aviso'], origen: `ejemplo:${ID}`
  }), { status }));
  return {
    fetch,
    ev: /** @type {any} */ ({
      url: new URL(`http://crm/api/manual/caso-dorado${query}`),
      locals: { user: { id: 'u' }, profile: { role: rol } },
      fetch
    })
  };
}

describe('GET /api/manual/caso-dorado', () => {
  it('pide el caso del ejemplo al motor y la página recibe el YAML y los avisos', async () => {
    const { fetch, ev } = evento(`?tipo=ejemplos&id=${ID}`);
    const r = await GET(ev);
    expect(fetch.mock.calls[0][0]).toBe(`http://motor/manual/ejemplos/${ID}/caso-dorado?tenant=empresa`);
    const cuerpo = await r.json();
    expect(cuerpo.caso_dorado).toBe(YAML);
    expect(cuerpo.avisos).toEqual(['un aviso']);
  });

  it('también de una revisión', async () => {
    const { fetch, ev } = evento(`?tipo=revisiones&id=${ID}`);
    await GET(ev);
    expect(fetch.mock.calls[0][0]).toBe(`http://motor/manual/revisiones/${ID}/caso-dorado?tenant=empresa`);
  });

  it('un tipo o un id inventados no llegan al motor', async () => {
    for (const q of ['?tipo=casos&id=' + ID, '?tipo=ejemplos&id=..%2Fcasos', '?tipo=ejemplos']) {
      const { fetch, ev } = evento(q);
      const r = await GET(ev);
      expect(r.status).toBe(400);
      expect(fetch).not.toHaveBeenCalled();
    }
  });

  it('quien no es administrador no lo genera', async () => {
    const { fetch, ev } = evento(`?tipo=ejemplos&id=${ID}`, { rol: 'USER' });
    const r = await GET(ev);
    expect(r.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('el motivo del motor cuando no hay caso llega a la pantalla, con su código', async () => {
    const { ev } = evento(`?tipo=revisiones&id=${ID}`,
      { status: 422, cuerpo: { error: 'La revision dice que la conversacion tuvo problemas' } });
    const r = await GET(ev);
    expect(r.status).toBe(422);
    expect((await r.json()).error).toMatch(/tuvo problemas/);
  });
});

describe('la pantalla de /manual usa el caso dorado, leído del código', () => {
  // El harness no compila .svelte: se fija que la página llame a este proxy y
  // que aprobar ya no sea un botón sin efecto.
  it('convertir, aprobar como caso dorado y rotular lo simulado', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const pagina = readFileSync(
      fileURLToPath(new URL('../../../(app)/manual/+page.svelte', import.meta.url)), 'utf-8');
    expect(pagina).toMatch(/\/api\/manual\/caso-dorado\?tipo=\$\{tipo\}&id=/);
    expect(pagina).toMatch(/\{#if r\.es_buen_ejemplo\}[\s\S]{0,900}Aprobar como caso dorado/);
    expect(pagina).toMatch(/datos\.caso_dorado/);
    expect(pagina).toMatch(/r\.real === false/);
    expect(pagina).toMatch(/\/simulador-whatsapp\?reproducir=\{e\.conversation_id\}/);
  });
});
