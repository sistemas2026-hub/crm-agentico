import { describe, it, expect, vi } from 'vitest';

/**
 * Un caso nuevo de /manual viaja con su rótulo (29/10/2026). Es el salto que
 * ninguna prueba del motor ve: si este intermediario dejara caer `rotulos`,
 * los casos se guardarían igual y nacerían sin rótulo, sin ningún error.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));

const { PUT } = await import('./+server.js');

function evento(cuerpo, rol = 'ADMIN') {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ casos: cuerpo.casos }), { status: 200 }));
  return {
    fetch,
    ev: /** @type {any} */ ({
      request: { json: async () => cuerpo },
      locals: { user: { id: 'u' }, profile: { role: rol } },
      fetch
    })
  };
}

describe('PUT /api/manual/casos', () => {
  it('reenvía los rótulos al motor junto con los casos', async () => {
    const { fetch, ev } = evento({ casos: ['otro', 'problema_de_tv'], rotulos: { problema_de_tv: 'Problema de TV' } });
    await PUT(ev);
    const enviado = JSON.parse(fetch.mock.calls[0][1].body);
    expect(enviado.rotulos).toEqual({ problema_de_tv: 'Problema de TV' });
    expect(enviado.casos).toEqual(['otro', 'problema_de_tv']);
  });

  it('sin rótulos manda un mapa vacío, no se cae', async () => {
    const { fetch, ev } = evento({ casos: ['otro'] });
    await PUT(ev);
    expect(JSON.parse(fetch.mock.calls[0][1].body).rotulos).toEqual({});
  });

  it('quien no es administrador no llega al motor', async () => {
    const { fetch, ev } = evento({ casos: ['otro'] }, 'USER');
    const r = await PUT(ev);
    expect(r.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('la pantalla de /manual manda lo escrito, leído del código', () => {
  // Test de texto: el harness no compila esta página (importa $app/*). Sin
  // esto, el intermediario de arriba podría estar en verde y la pantalla no
  // mandar nunca `rotulos`.
  it('guardarCasos incluye los rótulos de los casos nuevos', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const pagina = readFileSync(
      fileURLToPath(new URL('../../../(app)/manual/+page.svelte', import.meta.url)), 'utf-8');
    const guardar = pagina.slice(pagina.indexOf('async function guardarCasos'));
    expect(guardar.slice(0, 900)).toMatch(/rotulos:\s*Object\.fromEntries/);
    expect(pagina).toMatch(/rotulosNuevos = \{ \.\.\.rotulosNuevos, \[limpio\]: escrito/);
  });
});
