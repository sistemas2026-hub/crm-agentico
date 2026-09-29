import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

/**
 * La foto de un material, servida a través de la sesión del CRM.
 *
 * POR QUÉ HACE FALTA ESTE PASO Y NO UN `<img src="/media/...">`
 * ------------------------------------------------------------
 * Dos razones, las dos medidas:
 *
 *   1. `/media/` lo sirve Django SOLO en modo desarrollo. En producción no
 *      responde nadie ahí, así que la miniatura se vería rota justo donde
 *      importa.
 *   2. Una foto del catálogo es un dato de la empresa. Publicarla sin sesión la
 *      dejaría accesible a cualquiera que tenga la dirección.
 *
 * Así que la pantalla pide la imagen acá, este endpoint la pide al backend con
 * el token de quien está mirando, y devuelve el binario. Es el mismo patrón que
 * usan las otras rutas de `/api` del proyecto.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ params, cookies, fetch }) {
  const token = cookies.get('jwt_access');
  if (!token) throw error(401, 'Sin sesión');

  // La misma variable que usa `lib/api-helpers.js`: si el backend se mueve, se
  // mueve en un solo lugar.
  const base = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;
  const r = await fetch(`${base}/campo/inventario/materiales/${params.id}/imagen/`, {
    headers: { Authorization: `Bearer ${token}` }
  });

  if (!r.ok) {
    // 404 acá significa «este material no tiene foto», que es un caso normal:
    // la pantalla dibuja el icono de su clase en vez de un hueco.
    throw error(r.status === 404 ? 404 : 502, 'No se pudo leer la foto');
  }

  return new Response(r.body, {
    headers: {
      'Content-Type': r.headers.get('content-type') ?? 'image/jpeg',
      // Corto a propósito: la foto se reemplaza desde la misma pantalla y una
      // caché larga mostraría la anterior justo después de cambiarla. La clave
      // del archivo lleva un uuid, así que el navegador igual pide la nueva.
      'Cache-Control': 'private, max-age=60'
    }
  });
}
