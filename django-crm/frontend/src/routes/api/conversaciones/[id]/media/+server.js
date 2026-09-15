import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy para mandarle un archivo al cliente desde la bandeja. Ver
 * nucleo/canales/api.py: POST /conversaciones/<id>/humano/media.
 *
 * El multipart se REENVIA tal cual: no se lee el archivo en memoria acá para
 * volver a armarlo, que con un documento de 100 MB sería tener los bytes tres
 * veces (el que llega, el que se arma, el que sale). Lo único que se toca del
 * formulario son los dos campos que NO pueden venir del navegador -- el tenant
 * y el autor, que salen del entorno y de la sesión.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch, request }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json(
      { error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 }
    );
  }

  let entrante;
  try {
    entrante = await request.formData();
  } catch {
    return json({ error: 'No se pudo leer el archivo.' }, { status: 400 });
  }

  const salida = new FormData();
  const archivo = entrante.get('archivo');
  if (!archivo) {
    return json({ error: 'No llegó ningún archivo.' }, { status: 400 });
  }
  salida.set('archivo', archivo);
  salida.set('tipo', String(entrante.get('tipo') ?? ''));
  salida.set('pie', String(entrante.get('pie') ?? ''));
  // Estos dos NUNCA salen del navegador: el tenant es del entorno y el autor
  // de la sesión, igual que en la ruta de texto.
  salida.set('tenant', tenant);
  salida.set('autor', locals.user.email ?? '');

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/humano/media`, {
      method: 'POST',
      // Sin Content-Type a propósito: fetch pone el boundary del multipart, y
      // fijarlo a mano lo rompe de una forma que no da un error claro.
      headers: headersMotor(),
      body: salida
    });
    const datos = await resp.json();
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
