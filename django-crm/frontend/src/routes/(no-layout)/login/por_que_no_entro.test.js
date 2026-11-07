/**
 * EL LOGIN DEJA DE CULPAR A LA CONTRASEÑA POR TODO.
 *
 * EL DEFECTO, medido contra producción el 06/11/2026
 * --------------------------------------------------
 * El usuario quedó diez minutos probando contraseñas correctas. El `catch` de
 * la acción decía esto para cualquier fallo:
 *
 *     error.response?.data?.error || 'Correo o contraseña incorrectos'
 *
 * Un timeout, un 500, un DNS caído y una clave mal escrita salían con la
 * MISMA frase. Y el plazo de axios era de 10 s cuando el backend, medido con
 * tres ingresos seguidos, tardaba 10,7 s · 3,2 s · 1,7 s: el fallo era
 * intermitente y siempre se explicaba por el lado equivocado.
 *
 * QUÉ SE AFIRMA
 * -------------
 * El TEXTO que lee quien no pudo entrar, que es lo único que decide qué hace
 * después, y el código de estado, que es lo que distingue un reintento de un
 * cambio de contraseña. No se afirma que la función exista ni que el `catch`
 * esté puesto: un `catch` puesto que igual culpa a la contraseña sería verde
 * con el síntoma vivo.
 */
import { describe, expect, it, vi } from 'vitest';

const entorno = vi.hoisted(() => ({ env: { PRIVATE_DJANGO_API_URL: 'http://api.test' } }));
vi.mock('$env/dynamic/private', () => entorno);

const axios = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: axios }));

const { actions } = await import('./+page.server.js');

/** El evento que SvelteKit arma para la acción. @returns {any} */
function evento(email = 'quien@rapilinksas.co', password = 'la-que-si-es') {
  const datos = new Map([
    ['email', email],
    ['password', password]
  ]);
  return {
    request: { formData: async () => ({ get: (k) => datos.get(k) ?? null }) },
    cookies: { set: () => {}, get: () => undefined },
    url: new URL('https://dexter.example/login')
  };
}

/** Un error de axios con respuesta del servidor. */
const conRespuesta = (status, data = {}) =>
  Object.assign(new Error('falló'), { response: { status, data } });

/** Un error de axios SIN respuesta: nunca llegó. */
const sinRespuesta = (code = 'ECONNABORTED') =>
  Object.assign(new Error('timeout of 30000ms exceeded'), { code });

const intentar = async (error) => {
  axios.post.mockRejectedValueOnce(error);
  return /** @type {any} */ (await actions.password(evento()));
};

describe('cuando el servidor NO contestó', () => {
  //  EL DEFECTO. Es el caso que costó los diez minutos.
  it('un timeout no dice que la contraseña está mal', async () => {
    const r = await intentar(sinRespuesta());
    expect(r.data.error).not.toMatch(/contraseña incorrecta|incorrectos/i);
    expect(r.data.error).toMatch(/servidor/i);
  });

  it('y dice que los datos pueden estar bien, que es lo que destraba', async () => {
    const r = await intentar(sinRespuesta());
    expect(r.data.error).toMatch(/pueden estar bien/i);
  });

  it('no es 401: nadie rechazó estas credenciales', async () => {
    expect((await intentar(sinRespuesta())).status).toBe(503);
  });

  it('una conexión rechazada se trata igual que un timeout', async () => {
    const r = await intentar(sinRespuesta('ECONNREFUSED'));
    expect(r.status).toBe(503);
    expect(r.data.error).toMatch(/servidor/i);
  });
});

describe('cuando el servidor se rompió', () => {
  it('un 500 dice que no es la contraseña', async () => {
    const r = await intentar(conRespuesta(500));
    expect(r.data.error).toMatch(/No es tu contraseña/i);
    expect(r.status).toBe(502);
  });

  it('un 502 del proxy también', async () => {
    expect((await intentar(conRespuesta(502))).status).toBe(502);
  });
});

describe('cuando de verdad son las credenciales', () => {
  //  EL CONTROL: es la mitad que no se puede romper al arreglar la otra. Si
  //  un 401 dejara de decirlo, quien escribió mal la clave no sabría qué
  //  corregir.
  it('un 401 sí lo dice', async () => {
    const r = await intentar(conRespuesta(401));
    expect(r.status).toBe(401);
    expect(r.data.error).toMatch(/incorrectos/i);
  });

  it('y no nombra si falló el correo o la contraseña', async () => {
    //  Nombrarlo le confirmaría a cualquiera que ese correo tiene cuenta.
    const r = await intentar(conRespuesta(401));
    expect(r.data.error).not.toMatch(/ese correo no|no existe|usuario no/i);
  });

  it('el mensaje del backend gana sobre el genérico', async () => {
    const r = await intentar(conRespuesta(401, { error: 'Tu cuenta está desactivada' }));
    expect(r.data.error).toBe('Tu cuenta está desactivada');
  });
});

describe('los demás rechazos', () => {
  it('un 400 con motivo lo muestra', async () => {
    const r = await intentar(conRespuesta(400, { error: 'Falta el correo' }));
    expect(r.status).toBe(400);
    expect(r.data.error).toBe('Falta el correo');
  });

  it('un 400 sin motivo no inventa que es la contraseña', async () => {
    const r = await intentar(conRespuesta(400));
    expect(r.data.error).not.toMatch(/contraseña incorrect|incorrectos/i);
  });

  it('un 429 conserva su código, para que la pantalla pueda esperar', async () => {
    expect((await intentar(conRespuesta(429))).status).toBe(429);
  });
});

describe('los cuatro motivos se leen distinto', () => {
  //  Que cada rama exista no alcanza: si dos dijeran lo mismo, separarlas no
  //  habría servido de nada.
  it('timeout, 500, 401 y 400 dan cuatro frases distintas', async () => {
    const frases = [
      (await intentar(sinRespuesta())).data.error,
      (await intentar(conRespuesta(500))).data.error,
      (await intentar(conRespuesta(401))).data.error,
      (await intentar(conRespuesta(400))).data.error
    ];
    expect(new Set(frases).size).toBe(4);
  });
});

describe('el plazo alcanza para el backend real', () => {
  //  Medido: 10,7 s el peor de tres. Con 10 s se cortaba justo ahí.
  it('axios espera más de los 10,7 s que tardó el peor ingreso medido', async () => {
    axios.post.mockRejectedValueOnce(conRespuesta(401));
    await actions.password(evento());
    const opciones = axios.post.mock.lastCall[2];
    expect(opciones.timeout).toBeGreaterThan(10700);
  });
});
