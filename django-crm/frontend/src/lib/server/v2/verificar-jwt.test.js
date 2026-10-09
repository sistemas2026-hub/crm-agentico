import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import crypto from 'node:crypto';

/**
 * La verificación del JWT de sesión.
 *
 * QUÉ SE PROTEGE ACÁ, Y POR QUÉ IMPORTA MÁS QUE EN OTRA PANTALLA
 * -------------------------------------------------------------
 * De `locals.user` sale `autorDeSesion()`: el nombre y el id que el motor
 * guarda como AUTOR de cada acción del relevo — quién tomó la conversación,
 * quién aprobó la acción, quién la cerró y con qué desenlace. El motor no
 * puede comprobarlo: autentica al servicio, no al usuario.
 *
 * Así que si un token fabricado produce una sesión, el expediente entero que
 * B3–B6 construyeron para poder auditar deja de probar nada.
 *
 * Lo que se afirma es el EFECTO: qué acepta y qué rechaza, no que exista una
 * función con nombre de verificar.
 */

// El módulo lee env al importarse; hay que ponerlo antes.
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_DJANGO_API_URL: 'http://backend:8000' } }));
vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_DJANGO_API_URL: 'http://backend:8000' } }));

const get = vi.fn();
vi.mock('axios', () => ({ default: { get: (...a) => get(...a) } }));

const { verificarToken, motivoDeRechazoLocal, leerSinVerificar, _olvidarVerificados } =
  await import('./verificar-jwt.js');

/** Un JWT de verdad: HS256, como los que emite Django (SIMPLE_JWT). */
function firmar(payload, { clave = 'clave-de-prueba-de-32-bytes-o-mas!!', alg = 'HS256' } = {}) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const cuerpo = `${b64({ alg, typ: 'JWT' })}.${b64(payload)}`;
  if (alg === 'none') return `${cuerpo}.`;
  const firma = crypto.createHmac('sha256', clave).update(cuerpo).digest('base64url');
  return `${cuerpo}.${firma}`;
}

const DENTRO_DE_UNA_HORA = Math.floor(Date.now() / 1000) + 3600;
const HACE_UNA_HORA = Math.floor(Date.now() / 1000) - 3600;
const CLAIMS = {
  user_id: '11111111-2222-3333-4444-555555555555',
  user_name: 'Ana Gómez',
  user_email: 'ana@rapilink',
  org_id: '99999999-8888-7777-6666-555555555555',
  exp: DENTRO_DE_UNA_HORA
};

beforeEach(() => {
  get.mockReset();
  _olvidarVerificados();
});
afterEach(() => _olvidarVerificados());

const backendAcepta = () => get.mockResolvedValue({ status: 200, data: {} });
const backendRechaza = () => get.mockResolvedValue({ status: 401, data: {} });

describe('un token que el backend reconoce', () => {
  it('se acepta, y los claims sólo valen después de eso', async () => {
    backendAcepta();
    const payload = await verificarToken(firmar(CLAIMS));
    expect(payload?.user_id).toBe(CLAIMS.user_id);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('se le pregunta al backend con el token, no con otra cosa', async () => {
    backendAcepta();
    const token = firmar(CLAIMS);
    await verificarToken(token);
    const [url, opciones] = get.mock.calls[0];
    expect(url).toContain('/auth/me/');
    expect(opciones.headers.Authorization).toBe(`Bearer ${token}`);
  });

  it('no se le pregunta dos veces por el mismo token', async () => {
    backendAcepta();
    const token = firmar(CLAIMS);
    await verificarToken(token);
    await verificarToken(token);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('y dos pedidos simultáneos del mismo token son UNA sola consulta', async () => {
    backendAcepta();
    const token = firmar(CLAIMS);
    const [a, b] = await Promise.all([verificarToken(token), verificarToken(token)]);
    expect(a?.user_id).toBe(CLAIMS.user_id);
    expect(b?.user_id).toBe(CLAIMS.user_id);
    expect(get).toHaveBeenCalledTimes(1);
  });
});

describe('lo que NO puede producir una sesión', () => {
  it('un payload fabricado con exp futuro pero sin firma válida', async () => {
    // El caso exacto del hallazgo: cualquiera arma esto sin ninguna clave.
    backendRechaza();
    expect(await verificarToken(firmar(CLAIMS, { clave: 'la-clave-equivocada' }))).toBeNull();
  });

  it('un token legítimo con la firma alterada', async () => {
    backendRechaza();
    const token = firmar(CLAIMS);
    const alterado = token.slice(0, -4) + 'AAAA';
    expect(await verificarToken(alterado)).toBeNull();
  });

  it('claims manipulados: cambiar el user_id invalida la firma', async () => {
    backendRechaza();
    const otro = firmar({ ...CLAIMS, user_id: '00000000-0000-0000-0000-000000000000' },
                        { clave: 'otra' });
    expect(await verificarToken(otro)).toBeNull();
  });

  it('un token expirado, y ni siquiera se pregunta', async () => {
    backendAcepta();
    expect(await verificarToken(firmar({ ...CLAIMS, exp: HACE_UNA_HORA }))).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it("alg: none — se descarta sin consultar", async () => {
    backendAcepta();
    expect(await verificarToken(firmar(CLAIMS, { alg: 'none' }))).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it('un algoritmo que el backend no usa', async () => {
    backendAcepta();
    expect(await verificarToken(firmar(CLAIMS, { alg: 'RS256' }))).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it('algo que no tiene forma de token', async () => {
    backendAcepta();
    for (const basura of ['', 'abc', 'a.b', 'a.b.c.d', null, undefined]) {
      expect(await verificarToken(/** @type {any} */ (basura))).toBeNull();
    }
    expect(get).not.toHaveBeenCalled();
  });

  it('un token sin exp: no se acepta por omisión', async () => {
    backendAcepta();
    const { exp, ...sinExp } = CLAIMS;
    expect(await verificarToken(firmar(sinExp))).toBeNull();
  });
});

describe('fail-closed', () => {
  it('si el backend no responde, NO hay sesión', async () => {
    get.mockRejectedValue(new Error('ECONNREFUSED'));
    expect(await verificarToken(firmar(CLAIMS))).toBeNull();
  });

  it('un 403 tampoco alcanza', async () => {
    get.mockResolvedValue({ status: 403, data: {} });
    expect(await verificarToken(firmar(CLAIMS))).toBeNull();
  });

  it('y una caída no deja en caché el token como válido', async () => {
    get.mockRejectedValue(new Error('ECONNREFUSED'));
    const token = firmar(CLAIMS);
    await verificarToken(token);
    backendAcepta();
    expect(await verificarToken(token)).not.toBeNull();
  });
});

describe('el filtro local no es la verificación', () => {
  it('un token bien formado y vigente PASA el filtro y aún así se consulta', async () => {
    const token = firmar(CLAIMS, { clave: 'cualquiera' });
    expect(motivoDeRechazoLocal(token)).toBeNull();
    backendRechaza();
    expect(await verificarToken(token)).toBeNull();
  });

  it('cada rechazo local dice cuál fue', () => {
    expect(motivoDeRechazoLocal('a.b')).toBe('malformado');
    expect(motivoDeRechazoLocal(firmar(CLAIMS, { alg: 'none' }))).toBe('algoritmo_inesperado');
    expect(motivoDeRechazoLocal(firmar({ ...CLAIMS, exp: HACE_UNA_HORA }))).toBe('expirado');
  });

  it('leerSinVerificar NO valida: devuelve los claims de cualquier cosa firmada con cualquier clave', () => {
    const falso = firmar({ user_id: 'inventado', exp: DENTRO_DE_UNA_HORA }, { clave: 'nada' });
    expect(leerSinVerificar(falso)?.payload?.user_id).toBe('inventado');
    // Por eso su nombre lo dice, y por eso no decide nada.
  });
});

describe('el hook ya no decide por su cuenta', () => {
  it('hooks.server.js no tiene su propio decodificador', async () => {
    const fs = await import('node:fs');
    const fuente = fs.readFileSync(new URL('../../../hooks.server.js', import.meta.url), 'utf8');
    expect(fuente).not.toContain('function decodeJwtPayload');
  });

  it('y la sesión se arma llamando a la verificación', async () => {
    const fs = await import('node:fs');
    const fuente = fs.readFileSync(new URL('../../../hooks.server.js', import.meta.url), 'utf8');
    expect(fuente).toContain('verificarToken');

    // TODAS las llamadas tienen que estar AWAITED, no alguna. Sin await,
    // jwtPayload es una Promise --siempre verdadera-- y la guarda de ruta
    // deja pasar cualquier cookie.
    //
    // Se cuentan los sitios de llamada y se exige que cada uno lleve await.
    // Buscar la cadena 'await verifyTokenLocally(' no alcanzaba: con quitarle
    // el await a UNA de las dos, la otra dejaba la prueba en verde -- medido
    // con una mutacion.
    const llamadas = [...fuente.matchAll(/(await\s+)?verifyTokenLocally\s*\(/g)]
      .filter((m) => !fuente.slice(0, m.index).endsWith('function ') &&
                     !/function\s+$/.test(fuente.slice(0, m.index)));
    expect(llamadas.length).toBeGreaterThan(0);
    expect(llamadas.filter((m) => !m[1]).map((m) => m[0])).toEqual([]);
  });
});
