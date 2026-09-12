import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Server load: solo trae la lista fija de casos (tenant_config.manual.casos)
 * para poder marcar una respuesta como buen ejemplo (ver
 * MarcarEjemplo.svelte). El resto de esta pagina es puramente client-side
 * (habla con /api/simulador-whatsapp por su cuenta) -- mismo criterio que
 * /agentes: si esto falla, el boton de marcar simplemente no tiene
 * opciones, no se cae el simulador.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return { casos: [] };

  try {
    const resp = await fetch(`${baseUrl}/manual/casos?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() });
    return { casos: resp.ok ? (await resp.json()).casos : [] };
  } catch {
    return { casos: [] };
  }
}
