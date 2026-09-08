/**
 * El expediente en PDF de una solicitud de instalación.
 *
 * Existe porque ese archivo NO se puede servir por `/media/`: trae la foto del
 * documento de identidad, el recibo de servicios con la dirección, la foto del
 * solicitante y la firma. Django lo entrega sólo a quien está autenticado y es
 * de esa organización (ver `ExpedienteView`), y el navegador no tiene el Bearer
 * — tiene la cookie de este dominio. Este proxy hace la traducción.
 *
 * Mismo patrón que el export de casos: se lee el JWT de la cookie, se llama a
 * Django con él, y se pasa la respuesta tal cual.
 */
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

// PRIVATE_ antes que PUBLIC_: esto corre del lado del servidor.
const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, params, request }) {
  const accessToken = cookies.get('jwt_access');
  if (!accessToken) return new Response('No autenticado', { status: 401 });

  const upstream = await fetch(
    `${API_BASE_URL}/solicitudes/${encodeURIComponent(params.id)}/expediente/`,
    {
      method: 'GET',
      headers: { Authorization: `Bearer ${accessToken}`, Accept: 'application/pdf' },
      signal: request.signal
    }
  );

  if (!upstream.ok || !upstream.body) {
    // El motivo de Django se pasa tal cual: distingue "no existe esa
    // solicitud" de "no tiene expediente generado", y esa diferencia le dice a
    // quien mira si esperar el archivo o revisar por qué no se armó.
    const cuerpo = await upstream.json().catch(() => ({}));
    return new Response(cuerpo?.error || `El servidor respondió ${upstream.status}`, {
      status: upstream.status || 502
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'application/pdf',
      'Content-Disposition':
        upstream.headers.get('Content-Disposition') || 'inline; filename="expediente.pdf"',
      // Es un documento de identidad: que no quede en cachés intermedias.
      'Cache-Control': 'private, no-store'
    }
  });
}
