import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Qué formatos y tamaños acepta el canal, para validar en el navegador ANTES
 * de subir. Ver nucleo/canales/api.py: GET /canales/limites-media.
 *
 * Sale del motor y no de una constante en el frontend a propósito: el día que
 * Meta cambie un tope, una copia acá se desincroniza en silencio y el síntoma
 * sería un archivo que se sube entero para que lo rechacen al final.
 *
 * Si el motor no responde se devuelve vacío en vez de un error: sin límites la
 * validación local no corre y decide el servidor, que es el que manda igual.
 * Una pantalla que no deja adjuntar nada porque no pudo leer una tabla de
 * topes es peor que una que intenta y recibe el rechazo real.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  if (!baseUrl) return json({ limites: null });

  try {
    const resp = await fetch(`${baseUrl}/canales/limites-media`, { headers: headersMotor() });
    if (!resp.ok) return json({ limites: null });
    return json(await resp.json());
  } catch {
    return json({ limites: null });
  }
}
