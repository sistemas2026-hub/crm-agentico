import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Primera pintada del centro de mando. De aqui en adelante la pantalla se
 * refresca sola contra /api/centro-mando; este load existe para que al
 * entrar no se vea el esqueleto vacio mientras llega el primer fetch.
 *
 * Si el motor no responde no se tumba la pantalla: se entrega el error y el
 * componente lo muestra en su sitio. Mismo criterio que /agentes con la
 * metrica de escalamiento -- una pantalla de operacion que desaparece cuando
 * falla una consulta es peor que una que dice que le falta un dato.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return { panorama: null, error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const resp = await fetch(
      `${baseUrl}/centro-mando?tenant=${encodeURIComponent(tenant)}&ventana=10`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return { panorama: null, error: datos.error || 'No se pudo cargar el panorama' };
    }
    return { panorama: datos };
  } catch (/** @type {any} */ err) {
    return { panorama: null, error: err?.message || 'No se pudo contactar al asistente' };
  }
}
