import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Sirve un adjunto que mando el cliente por el canal (una foto del router, un
 * audio). Ver nucleo/canales/api.py: GET /media/<id>.

 *
 * Va por proxy y no con un enlace directo al motor por dos razones: el motor
 * no esta publicado en internet (solo lo alcanza el frontend por la red
 * interna), y asi la foto queda detras de la sesion del CRM -- un adjunto de
 * un cliente no puede ser una URL que cualquiera abra.
 *
 * Devuelve los bytes tal cual, con su mime, para poder usarlo directo en un
 * <img src>. Pasarlo a base64 inflaria un 33% cada foto del hilo.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ params, locals, fetch, setHeaders }) {
  if (!locals.user) {
    error(401, 'No autenticado');
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    error(500, 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)');
  }

  const resp = await fetch(
    `${baseUrl}/media/${params.id}?tenant=${encodeURIComponent(tenant)}`,
    { headers: headersMotor() }
  );
  if (!resp.ok) {
    error(resp.status === 404 ? 404 : 502, 'No se pudo leer el archivo');
  }

  // El contenido de un id no cambia nunca (se inserta una vez y se borra por
  // antiguedad), asi que revalidar seria trafico puro. 'private' porque es de
  // un cliente concreto: no puede quedar en una cache compartida.
  setHeaders({ 'cache-control': 'private, max-age=86400' });

  return new Response(resp.body, {
    headers: {
      'content-type': resp.headers.get('content-type') || 'application/octet-stream'
    }
  });
}
