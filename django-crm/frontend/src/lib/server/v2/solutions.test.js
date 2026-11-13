import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La capa servidor de /solutions, en lo que agregó el 12/11/2026: que el
 * estado de la ingesta al asistente llegue a la página, y que los agentes
 * elegibles se le pidan al motor de la empresa de la SESIÓN.
 */
const { envMock } = vi.hoisted(() => ({ envMock: /** @type {Record<string, string>} */ ({}) }));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { getArticle, agentesDelAsistente, estadoEnElAsistente, updateArticle } = await import(
  './solutions.js'
);

const cookies = /** @type {any} */ ({ get: () => 'token' });

/** El detalle tal como lo devuelve SolutionDetailSerializer. */
function articulo(extra = {}) {
  return {
    id: 's1',
    title: 'Cómo reiniciar la ONT',
    description: 'Desenchufe 30 segundos.',
    status: 'approved',
    is_published: true,
    roles_asistente: 'soporte',
    estado_ingesta: 'ok',
    ingesta_detalle: null,
    ingesta_fragmentos: 2,
    case_count: 0,
    linked_cases: [],
    ...extra
  };
}

describe('getArticle lleva el estado en el asistente', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('cargado: «Dexter lo puede citar», con los agentes', async () => {
    apiRequest.mockResolvedValue(articulo());
    const { article } = await getArticle({ cookies }, 's1');
    expect(article.asistente.clave).toBe('ok');
    expect(article.asistente.texto).toContain('Dexter lo puede citar');
    expect(article.roles_asistente).toBe('soporte');
  });

  it('el error del motor llega a la pantalla', async () => {
    apiRequest.mockResolvedValue(
      articulo({ estado_ingesta: 'error', ingesta_detalle: 'rol(es) inexistente(s): soporte' })
    );
    const { article } = await getArticle({ cookies }, 's1');
    expect(article.asistente.clave).toBe('error');
    expect(article.asistente.detalle).toContain('inexistente');
  });

  it('un borrador no promete nada', () => {
    const e = estadoEnElAsistente({ status: 'draft', is_published: false, estado_ingesta: '' });
    expect(e.clave).toBe('fuera');
    expect(e.texto).toContain('no lo usa');
  });

  it('updateArticle manda los agentes elegidos', async () => {
    apiRequest.mockResolvedValue({});
    await updateArticle({ cookies }, 's1', { roles_asistente: 'soporte, ventas' });
    expect(apiRequest.mock.calls[0][1].body).toEqual({ roles_asistente: 'soporte, ventas' });
  });
});

describe('agentesDelAsistente', () => {
  beforeEach(() => {
    for (const k of Object.keys(envMock)) delete envMock[k];
  });

  it('le pregunta al motor de la empresa de la sesión', async () => {
    envMock.PRIVATE_ASISTENTE_URL = 'http://motor:5000';
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        agentes: [
          { nombre: 'soporte', cargo: 'Soporte', orientado_a: 'cliente_final' },
          { nombre: 'noc', cargo: 'NOC', orientado_a: 'colaborador' }
        ]
      })
    });
    const lista = await agentesDelAsistente({ locals: { tenant: 'empresa-a' }, fetch });
    expect(fetch.mock.calls[0][0]).toBe('http://motor:5000/agentes?tenant=empresa-a');
    expect(lista).toEqual([
      { nombre: 'soporte', cargo: 'Soporte', esCliente: true },
      { nombre: 'noc', cargo: 'NOC', esCliente: false }
    ]);
  });

  it('sin motor configurado, lista vacía y sin pedir nada', async () => {
    const fetch = vi.fn();
    expect(await agentesDelAsistente({ locals: { tenant: 'empresa-a' }, fetch })).toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });
});
