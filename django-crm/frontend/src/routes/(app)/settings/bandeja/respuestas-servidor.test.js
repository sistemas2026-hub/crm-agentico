import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Las respuestas rápidas en Ajustes → Bandeja (11/11/2026), atravesando la
 * capa servidor ENTERA hasta el fetch al motor: el formulario manda los
 * renglones como pares `rr_atajo` / `rr_texto`, la acción los arma en una
 * lista, `guardarRespuestasRapidas` la manda al motor. Se mockea solo el
 * entorno y el fetch: si un salto pierde un renglón, corre los textos de
 * lugar o manda la lista sin el campo, el cuerpo que llega al motor lo dice.
 */
const { envMock } = vi.hoisted(() => ({ envMock: /** @type {Record<string, string>} */ ({}) }));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { actions, load } = await import('./+page.server.js');

let fetchMock = vi.fn();
const cuerpoAlMotor = () => {
  const llamada = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT');
  return llamada ? JSON.parse(llamada[1].body) : null;
};

/** @param {[string, string][]} pares @param {string} [rol] */
function evento(pares, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of pares) fd.append(k, v);
  return /** @type {any} */ ({
    fetch: fetchMock,
    request: { formData: async () => fd },
    locals: { profile: { role: rol }, tenant: 'empresa-x' }
  });
}

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
  envMock.PRIVATE_ASISTENTE_URL = 'http://motor:5000';
  fetchMock = vi.fn(async (/** @type {string} */ url, /** @type {any} */ init) => {
    if (init?.method === 'PUT') {
      const enviado = JSON.parse(init.body);
      return new Response(JSON.stringify({ respuestas_rapidas: enviado.respuestas_rapidas }), { status: 200 });
    }
    if (String(url).includes('/respuestas-rapidas')) {
      return new Response(
        JSON.stringify({ respuestas_rapidas: [{ atajo: 'saludo', texto: 'Hola {nombre}' }] }),
        { status: 200 }
      );
    }
    return new Response(JSON.stringify({}), { status: 200 });
  });
});

describe('respuestas rápidas en Ajustes', () => {
  it('la carga las trae del motor, con el tenant de la sesión', async () => {
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ fetch: fetchMock, locals: { tenant: 'empresa-x' } })));
    expect(d.respuestasRapidas).toEqual([{ atajo: 'saludo', texto: 'Hola {nombre}' }]);
    const url = fetchMock.mock.calls.map(([u]) => String(u)).find((u) => u.includes('respuestas-rapidas'));
    expect(url).toContain('tenant=empresa-x');
  });

  it('EL EFECTO: cada atajo llega al motor con SU texto, en orden, incluido el renglón vacío', async () => {
    const r = /** @type {any} */ (
      await actions.respuestas(
        evento([
          ['rr_atajo', ' saludo '],
          ['rr_texto', 'Hola {nombre}, ¿en qué te ayudo?'],
          ['rr_atajo', 'reinicio'],
          ['rr_texto', 'Desconectá el equipo 30 segundos.'],
          ['rr_atajo', ''],
          ['rr_texto', '']
        ])
      )
    );
    expect(r.respuestasGuardadas).toBe(true);
    expect(cuerpoAlMotor()).toEqual({
      tenant: 'empresa-x',
      respuestas_rapidas: [
        { atajo: 'saludo', texto: 'Hola {nombre}, ¿en qué te ayudo?' },
        { atajo: 'reinicio', texto: 'Desconectá el equipo 30 segundos.' },
        { atajo: '', texto: '' }
      ]
    });
  });

  it('quitar todas manda la lista VACÍA, no la omite', async () => {
    await actions.respuestas(evento([]));
    expect(cuerpoAlMotor()).toEqual({ tenant: 'empresa-x', respuestas_rapidas: [] });
  });

  it('el rechazo del motor vuelve con su texto, y el panel queda abierto (400)', async () => {
    fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ error: "el atajo '/hola' está dos veces" }), { status: 400 })
    );
    const r = /** @type {any} */ (
      await actions.respuestas(evento([['rr_atajo', 'hola'], ['rr_texto', 'a'], ['rr_atajo', 'hola'], ['rr_texto', 'b']]))
    );
    expect(r.status).toBe(400);
    expect(r.data.respuestas.error).toMatch(/dos veces/);
  });

  it('un formulario con renglones desparejos no llega al motor', async () => {
    const r = /** @type {any} */ (await actions.respuestas(evento([['rr_atajo', 'hola']])));
    expect(r.status).toBe(400);
    expect(cuerpoAlMotor()).toBeNull();
  });

  it('quien no es administrador no escribe', async () => {
    const r = /** @type {any} */ (await actions.respuestas(evento([['rr_atajo', 'a'], ['rr_texto', 'b']], 'USER')));
    expect(r.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
