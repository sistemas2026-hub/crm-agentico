/**
 * La ruta que deja ver una foto de campo en la bitácora.
 *
 * Se prueba el EFECTO: qué le llega al navegador, y qué NO. Antes de esta ruta
 * ninguna foto se podía abrir en producción; si se rompe, se vuelve a eso sin
 * ningún error visible —la bitácora mostraría un hueco y nada más—.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_DJANGO_API_URL: 'http://backend:8000' } }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const { GET } = await import('./+server.js');

const ID = '0b6f5a2e-1c3d-4e5f-8a9b-0c1d2e3f4a5b';
const cookies = { get: (/** @type {string} */ k) => (k === 'jwt_access' ? 'tok' : undefined) };
const evento = (rol = 'SUPERVISOR', id = ID) => ({
  params: { id },
  cookies,
  locals: { user: { id: 'u' }, profile: { role: rol } },
  request: new Request('http://x')
});

const fetchOriginal = globalThis.fetch;
let llamadas = /** @type {any[]} */ ([]);
beforeEach(() => {
  llamadas = [];
});
afterEach(() => {
  globalThis.fetch = fetchOriginal;
});

/** @param {Response} r */
function backendDevuelve(r) {
  globalThis.fetch = /** @type {any} */ (
    vi.fn(async (url, init) => {
      llamadas.push({ url, init });
      return r;
    })
  );
}

describe('archivo de una evidencia', () => {
  it('pasa la foto con su tipo y sin caché compartida', async () => {
    backendDevuelve(
      new Response(new Uint8Array([1, 2, 3]), {
        status: 200,
        headers: { 'Content-Type': 'image/jpeg', 'Content-Disposition': 'inline; filename="a.jpg"' }
      })
    );
    const r = await GET(/** @type {any} */ (evento()));
    expect(r.status).toBe(200);
    expect(r.headers.get('Content-Type')).toBe('image/jpeg');
    expect(r.headers.get('Cache-Control')).toBe('private, no-store');
    expect(new Uint8Array(await r.arrayBuffer())).toEqual(new Uint8Array([1, 2, 3]));
    expect(llamadas[0].url).toBe(`http://backend:8000/api/campo/evidencias/${ID}/archivo/`);
    expect(llamadas[0].init.headers.Authorization).toBe('Bearer tok');
  });

  it('un rol sin gestión no llega ni a preguntarle al backend', async () => {
    backendDevuelve(new Response('x'));
    const r = await GET(/** @type {any} */ (evento('USER')));
    expect(r.status).toBe(403);
    expect(llamadas).toHaveLength(0);
  });

  it('un id que no es UUID no se convierte en otra ruta del backend', async () => {
    backendDevuelve(new Response('x'));
    const r = await GET(/** @type {any} */ (evento('ADMIN', '../../cases/analytics/export')));
    expect(r.status).toBe(404);
    expect(llamadas).toHaveLength(0);
  });

  it('el 404 del backend —otra empresa, técnico no asignado— sigue siendo 404', async () => {
    backendDevuelve(new Response('{}', { status: 404 }));
    const r = await GET(/** @type {any} */ (evento()));
    expect(r.status).toBe(404);
  });
});
