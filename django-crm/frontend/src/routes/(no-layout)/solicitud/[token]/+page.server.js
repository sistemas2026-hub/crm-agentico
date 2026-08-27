/**
 * Solicitud de servicio, pública.
 *
 * Anónima: el token de la URL es la única credencial. Mismo patrón que la
 * página de CSAT — el fetch se hace del lado del servidor para que la página
 * pinte con los datos ya adentro y sin exponerle la URL de la API al navegador.
 *
 * La diferencia con CSAT es que acá viajan archivos (tres fotos y la firma),
 * así que la acción reenvía el multipart tal como llegó en vez de armar un
 * JSON: volver a leer y re-serializar imágenes de 5 MB en el medio no aporta
 * nada y multiplica la memoria del proceso por cada solicitud simultánea.
 */

import { fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

/** @type {import('./$types').PageServerLoad} */
export async function load({ params, fetch }) {
  const res = await fetch(`${API_BASE_URL}/public/solicitud/${params.token}/`);
  if (res.status === 410) return { vencida: true };
  if (res.status === 400) return { invalida: true };
  if (!res.ok) return { error: `El servidor respondió ${res.status}` };

  const data = await res.json();
  return {
    yaEnviada: data.ya_enviada,
    enviadaEn: data.enviada_en,
    // Lo que la persona ya le dijo al asistente por WhatsApp. Que el
    // formulario se lo vuelva a preguntar es la forma más rápida de que
    // abandone: son 20 campos y ya escribió parte de esto una vez.
    prellenado: data.prellenado ?? {}
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  enviar: async ({ request, params, fetch }) => {
    const recibido = await request.formData();

    // Se reenvía tal cual. No se valida acá a propósito: la validación de
    // verdad está en Django (obligatorios, tamaño de imagen, autorización), y
    // duplicarla en el medio sólo garantiza que un día las dos digan cosas
    // distintas. Esto es transporte.
    const res = await fetch(`${API_BASE_URL}/public/solicitud/${params.token}/`, {
      method: 'POST',
      body: recibido
    });

    if (res.status === 410) {
      return fail(410, { error: 'Este enlace venció. Escribinos por WhatsApp y te pasamos uno nuevo.' });
    }
    if (res.status === 409) {
      return fail(409, { error: 'Esta solicitud ya fue enviada. Si necesitás corregir algo, escribinos por WhatsApp.' });
    }
    if (res.status === 413) {
      return fail(413, { error: 'Alguna de las fotos pesa más de 5 MB. Sacala de nuevo con menos calidad o recortala.' });
    }
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => ({}));
      return fail(res.status, {
        error: cuerpo?.error || `El servidor respondió ${res.status}`,
        campos: cuerpo?.campos ?? []
      });
    }

    const ok = await res.json();
    return { enviada: true, mensaje: ok?.mensaje };
  }
};
