import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Consumo: cuánto gasta la empresa en el modelo y en qué punto del tope está.
 * Ver nucleo/observabilidad/consumo.py.
 *
 * Solo ADMIN. El gasto y su tope son datos de administración: un colaborador
 * de soporte no tiene por qué ver la factura.
 *
 * El ESTADO lo decide el motor, no esta pantalla. La maqueta original mostraba
 * "sin tope configurado", "0% del tope" y "asistente frenado por alcanzar el
 * tope" a la vez — tres cosas que no pueden ser ciertas juntas. Si cada
 * tarjeta decide sola si mostrarse, tarde o temprano se contradicen.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  if (locals.profile?.role !== 'ADMIN') {
    redirect(303, '/');
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return { consumo: null, error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const resp = await fetch(`${baseUrl}/consumo?tenant=${encodeURIComponent(tenant)}&dias=30`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) return { consumo: null, error: datos.error || 'No se pudo leer el consumo.' };
    return { consumo: datos };
  } catch (/** @type {any} */ err) {
    console.error('[consumo] motor inalcanzable:', err?.message);
    return { consumo: null, error: 'No se pudo contactar al asistente.' };
  }
}
