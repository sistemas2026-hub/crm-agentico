import { describe, it, expect, vi, beforeEach } from 'vitest';
import crypto from 'node:crypto';

/**
 * LA SESIÓN NO SE CIERRA SOLA.
 *
 * Reportado el 11/11/2026: «se cierra sesión en la plataforma después de un
 * tiempo». Lo que se afirma acá es el EFECTO sobre las cookies y sobre la
 * respuesta, recorriendo `atenderSesion()` entera —la misma función que
 * ejecuta el hook— con un backend doblado. Dos escenarios reproducen el
 * cierre, y los dos tienen que terminar con la persona adentro:
 *
 *   1. LA CARRERA: dos pedidos con el mismo access vencido; el segundo llega
 *      DESPUÉS de que el primero renovó, con el refresh ya quemado.
 *   2. LA DEMORA: el backend no contesta a tiempo. Ni se renueva a ciegas ni
 *      se borra nada.
 *
 * Y lo que SÍ debe cerrar la sesión sigue cerrándola: un refresh que el
 * backend rechaza sin que nadie lo haya rotado antes.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_DJANGO_API_URL: 'http://backend:8000' } }));
vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_DJANGO_API_URL: 'http://backend:8000' } }));

const get = vi.fn();
const post = vi.fn();
vi.mock('axios', () => ({ default: { get: (...a) => get(...a), post: (...a) => post(...a) } }));

const { atenderSesion, refrescar, _olvidarRotaciones, VENTANA_RENOVACION_MS } =
  await import('./sesion.js');
const { _olvidarVerificados } = await import('./v2/verificar-jwt.js');

/** Un JWT con la forma de los que emite Django (HS256). El backend está doblado: la firma no se comprueba acá. */
function firmar(payload) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const cuerpo = `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(payload)}`;
  const firma = crypto.createHmac('sha256', 'clave-de-prueba-de-32-bytes-o-mas!!').update(cuerpo).digest('base64url');
  return `${cuerpo}.${firma}`;
}

const ahora = () => Math.floor(Date.now() / 1000);
const ORG = '99999999-8888-7777-6666-555555555555';
const CLAIMS = {
  user_id: '11111111-2222-3333-4444-555555555555',
  user_name: 'Ana Gómez',
  user_email: 'ana@rapilink',
  org_id: ORG,
  org_name: 'Rapilink',
  role: 'ADMIN'
};
const vigente = (extra = {}) => firmar({ ...CLAIMS, exp: ahora() + 3600, ...extra });
const vencido = () => firmar({ ...CLAIMS, exp: ahora() - 60 });
const porVencer = () => firmar({ ...CLAIMS, exp: ahora() + Math.floor(VENTANA_RENOVACION_MS / 1000) - 30 });
const refresh = (n) => firmar({ token_type: 'refresh', jti: `jti-${n}`, exp: ahora() + 14 * 86400 });

/**
 * Un evento de SvelteKit reducido a lo que la sesión usa, con un frasco de
 * cookies que registra cada escritura y cada borrado.
 */
function evento({ cookies = {}, ruta = '/conversaciones' } = {}) {
  const frasco = new Map(Object.entries(cookies));
  /** @type {Array<{ nombre: string, valor: string | null }>} */
  const escrituras = [];
  return {
    cookies: {
      get: (n) => frasco.get(n),
      set: (n, v) => { frasco.set(n, v); escrituras.push({ nombre: n, valor: v }); },
      delete: (n) => { frasco.delete(n); escrituras.push({ nombre: n, valor: null }); }
    },
    url: new URL(`http://plataforma${ruta}`),
    locals: {},
    frasco,
    escrituras,
    borradas: () => escrituras.filter((e) => e.valor === null).map((e) => e.nombre)
  };
}

const conSesion = (access, r = refresh(1)) => ({ jwt_access: access, jwt_refresh: r, org: ORG });

/** El backend acepta cualquier access en /auth/me/. */
const backendReconoce = () => get.mockResolvedValue({ status: 200, data: {} });

/** El backend renueva: emite el par N y, a partir de ahí, rechaza el refresh que se gastó. */
function backendRenueva() {
  const quemados = new Set();
  let n = 10;
  post.mockImplementation(async (url, body) => {
    if (!url.includes('/auth/refresh-token/')) throw new Error(`inesperado: ${url}`);
    if (quemados.has(body.refresh)) return { status: 401, data: { error: 'Invalid or expired token' } };
    quemados.add(body.refresh);
    n += 1;
    return { status: 200, data: { access: vigente({ emitido: n }), refresh: refresh(n) } };
  });
}

/** Qué lanzó atenderSesion, si lanzó algo. */
async function resultado(ev) {
  try {
    await atenderSesion(ev);
    return { paso: true };
  } catch (e) {
    return { paso: false, status: e?.status, location: e?.location, mensaje: e?.body?.message };
  }
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  _olvidarRotaciones();
  _olvidarVerificados();
});

describe('con el access vigente', () => {
  it('hay sesión, y no se renueva ni se escribe ninguna cookie', async () => {
    backendReconoce();
    const ev = evento({ cookies: conSesion(vigente()) });
    expect(await resultado(ev)).toEqual({ paso: true });
    expect(ev.locals.user?.name).toBe('Ana Gómez');
    expect(ev.locals.org?.id).toBe(ORG);
    expect(post).not.toHaveBeenCalled();
    expect(ev.escrituras).toEqual([]);
  });
});

describe('con el access vencido', () => {
  it('se renueva con el refresh y las DOS cookies quedan con el par nuevo', async () => {
    backendReconoce();
    backendRenueva();
    const viejo = refresh(1);
    const ev = evento({ cookies: conSesion(vencido(), viejo) });
    expect(await resultado(ev)).toEqual({ paso: true });
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1]).toEqual({ refresh: viejo });
    expect(ev.frasco.get('jwt_refresh')).not.toBe(viejo);
    expect(ev.frasco.get('jwt_access')).toBeTruthy();
    expect(ev.locals.user?.id).toBe(CLAIMS.user_id);
    expect(ev.borradas()).toEqual([]);
  });

  it('LA CARRERA: el pedido que llega con el refresh ya quemado recibe el mismo par nuevo y NO borra nada', async () => {
    backendReconoce();
    backendRenueva();
    const viejo = refresh(1);

    // A sale primero y termina: el backend quemó `viejo`.
    const a = evento({ cookies: conSesion(vencido(), viejo) });
    expect(await resultado(a)).toEqual({ paso: true });

    // B había SALIDO del navegador con las cookies viejas y llega recién ahora.
    // Hasta el 11/11/2026 esto era un 401 del backend y tres cookies borradas:
    // la sesión que A acababa de renovar, cerrada por B.
    const b = evento({ cookies: conSesion(vencido(), viejo) });
    expect(await resultado(b)).toEqual({ paso: true });

    expect(b.borradas()).toEqual([]);
    expect(b.frasco.get('jwt_access')).toBe(a.frasco.get('jwt_access'));
    expect(b.frasco.get('jwt_refresh')).toBe(a.frasco.get('jwt_refresh'));
    expect(b.locals.user?.id).toBe(CLAIMS.user_id);
    // Y el backend vio UNA renovación, no dos.
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('dos pedidos que se solapan comparten la misma renovación', async () => {
    backendReconoce();
    backendRenueva();
    const viejo = refresh(1);
    const [a, b] = [evento({ cookies: conSesion(vencido(), viejo) }), evento({ cookies: conSesion(vencido(), viejo) })];
    const [ra, rb] = await Promise.all([resultado(a), resultado(b)]);
    expect(ra).toEqual({ paso: true });
    expect(rb).toEqual({ paso: true });
    expect(post).toHaveBeenCalledTimes(1);
    expect(a.frasco.get('jwt_refresh')).toBe(b.frasco.get('jwt_refresh'));
  });

  it('un refresh que el backend rechaza SIN rotación previa sí cierra la sesión', async () => {
    backendReconoce();
    post.mockResolvedValue({ status: 401, data: { error: 'Invalid or expired token' } });
    const ev = evento({ cookies: conSesion(vencido()), ruta: '/tickets/7' });
    const r = await resultado(ev);
    expect(r.paso).toBe(false);
    expect(r.status).toBe(307);
    expect(r.location).toBe('/login?redirect=%2Ftickets%2F7');
    expect(ev.borradas().sort()).toEqual(['jwt_access', 'jwt_refresh', 'org']);
  });

  it('LA DEMORA: si el backend no contesta la renovación, las cookies quedan y el pedido dice 503, no /login', async () => {
    backendReconoce();
    post.mockRejectedValue(Object.assign(new Error('timeout of 10000ms exceeded'), { code: 'ECONNABORTED' }));
    const ev = evento({ cookies: conSesion(vencido()) });
    const r = await resultado(ev);
    expect(r.paso).toBe(false);
    expect(r.status).toBe(503);
    expect(r.location).toBeUndefined();
    expect(ev.borradas()).toEqual([]);
    expect(ev.frasco.has('jwt_refresh')).toBe(true);
  });
});

describe('cuando el backend no contesta la verificación', () => {
  it('no se renueva a ciegas, no se borra nada, y el pedido dice 503', async () => {
    get.mockRejectedValue(Object.assign(new Error('timeout of 8000ms exceeded'), { code: 'ECONNABORTED' }));
    backendRenueva();
    const ev = evento({ cookies: conSesion(vigente()) });
    const r = await resultado(ev);
    expect(r.status).toBe(503);
    expect(post).not.toHaveBeenCalled();
    expect(ev.borradas()).toEqual([]);
  });

  it('y al volver el backend, el siguiente pedido entra con las mismas cookies', async () => {
    const cookies = conSesion(vigente());
    get.mockRejectedValueOnce(new Error('ECONNREFUSED'));
    expect((await resultado(evento({ cookies }))).status).toBe(503);
    backendReconoce();
    const ev = evento({ cookies });
    expect(await resultado(ev)).toEqual({ paso: true });
    expect(ev.locals.user?.id).toBe(CLAIMS.user_id);
  });

  it('una ruta pública no se ve afectada', async () => {
    get.mockRejectedValue(new Error('ECONNREFUSED'));
    expect(await resultado(evento({ cookies: conSesion(vigente()), ruta: '/login' }))).toEqual({ paso: true });
    expect(await resultado(evento({ cookies: conSesion(vigente()), ruta: '/solicitud/abc' }))).toEqual({ paso: true });
  });
});

describe('se renueva ANTES de vencer', () => {
  it('con el access vigente pero por vencer, se rota en este pedido y las cookies quedan nuevas', async () => {
    backendReconoce();
    backendRenueva();
    const viejo = refresh(1);
    const ev = evento({ cookies: conSesion(porVencer(), viejo) });
    expect(await resultado(ev)).toEqual({ paso: true });
    expect(post).toHaveBeenCalledTimes(1);
    expect(ev.frasco.get('jwt_refresh')).not.toBe(viejo);
    expect(ev.locals.user?.id).toBe(CLAIMS.user_id);
  });

  it('y si esa renovación anticipada falla, la sesión vigente sigue: nada se borra ni se corta', async () => {
    backendReconoce();
    post.mockResolvedValue({ status: 401, data: {} });
    const ev = evento({ cookies: conSesion(porVencer()) });
    expect(await resultado(ev)).toEqual({ paso: true });
    expect(ev.borradas()).toEqual([]);
    expect(ev.locals.user?.id).toBe(CLAIMS.user_id);

    post.mockRejectedValue(new Error('ECONNREFUSED'));
    const ev2 = evento({ cookies: conSesion(porVencer()) });
    expect(await resultado(ev2)).toEqual({ paso: true });
    expect(ev2.borradas()).toEqual([]);
  });
});

describe('la guarda de ruta sigue igual', () => {
  it('sin cookies: ruta protegida -> /login con el destino; pública -> pasa', async () => {
    const r = await resultado(evento({ ruta: '/tickets?estado=abierto' }));
    expect(r.status).toBe(307);
    expect(r.location).toBe('/login?redirect=%2Ftickets%3Festado%3Dabierto');
    expect(await resultado(evento({ ruta: '/portal/xyz' }))).toEqual({ paso: true });
  });

  it('con sesión pero sin empresa, una ruta de la app manda a /org y /org deja pasar', async () => {
    backendReconoce();
    const sinOrg = { jwt_access: vigente(), jwt_refresh: refresh(1) };
    const r = await resultado(evento({ cookies: sinOrg, ruta: '/conversaciones' }));
    expect(r.status).toBe(307);
    expect(r.location).toBe('/org?redirect=%2Fconversaciones');
    expect(await resultado(evento({ cookies: sinOrg, ruta: '/org' }))).toEqual({ paso: true });
  });

  it('un token sin la empresa de la cookie cambia de empresa y guarda el par nuevo', async () => {
    backendReconoce();
    const otraOrg = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
    const nuevoAccess = vigente({ org_id: otraOrg, org_name: 'Otra', role: 'USER' });
    post.mockResolvedValue({
      status: 200,
      data: { access_token: nuevoAccess, refresh_token: refresh(2), current_org: { id: otraOrg, name: 'Otra' } }
    });
    const ev = evento({ cookies: { jwt_access: vigente(), jwt_refresh: refresh(1), org: otraOrg } });
    expect(await resultado(ev)).toEqual({ paso: true });
    expect(post.mock.calls[0][0]).toContain('/auth/switch-org/');
    expect(post.mock.calls[0][1]).toEqual({ org_id: otraOrg, refresh: refresh(1) });
    expect(ev.frasco.get('jwt_access')).toBe(nuevoAccess);
    expect(ev.locals.org).toEqual({ id: otraOrg, name: 'Otra' });
    expect(ev.locals.profile?.role).toBe('USER');
  });
});

describe('refrescar() por sí sola', () => {
  it('recuerda la rotación solo un rato y solo si salió bien', async () => {
    post.mockResolvedValueOnce({ status: 401, data: {} });
    expect(await refrescar('r-rechazado')).toEqual({ estado: 'rechazado' });
    post.mockResolvedValueOnce({ status: 401, data: {} });
    expect(await refrescar('r-rechazado')).toEqual({ estado: 'rechazado' });
    expect(post).toHaveBeenCalledTimes(2);

    post.mockResolvedValueOnce({ status: 200, data: { access: 'a1', refresh: 'r1' } });
    expect(await refrescar('r0')).toEqual({ estado: 'renovado', access: 'a1', refresh: 'r1' });
    expect(await refrescar('r0')).toEqual({ estado: 'renovado', access: 'a1', refresh: 'r1' });
    expect(post).toHaveBeenCalledTimes(3);
  });

  it('un 200 sin access cuenta como rechazo, no como renovación', async () => {
    post.mockResolvedValueOnce({ status: 200, data: {} });
    expect(await refrescar('r-raro')).toEqual({ estado: 'rechazado' });
  });
});
