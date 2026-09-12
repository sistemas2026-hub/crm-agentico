import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Conectores: conectar un sistema conocido eligiéndolo de una lista, en vez de
 * describir su API y sondearla. Ver nucleo/conectores/catalogo.py.
 *
 * Solo ADMIN. Aplicar un conector escribe herramientas que acceden a datos de
 * clientes y decide qué campos ve cada rol.
 *
 * Se cargan los conectores y los roles del tenant: el mapeo área → rol es la
 * decisión que toma la persona, y no se puede ofrecer sin saber qué roles hay.
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
    return { conectores: [], roles: [], error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  /** Los roles del tenant, para mapear cada área del conector a uno. */
  let roles = [];
  try {
    const resp = await fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() });
    if (resp.ok) {
      const datos = await resp.json();
      roles = (datos.agentes ?? [])
        .map((/** @type {any} */ a) => ({ nombre: a.nombre, orientado_a: a.orientado_a }))
        .filter((/** @type {any} */ r) => r.nombre);
    }
  } catch (/** @type {any} */ err) {
    console.error('[conectores] no se pudieron leer los roles:', err?.message);
  }

  try {
    const resp = await fetch(`${baseUrl}/conectores`, { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) return { conectores: [], roles, error: datos.error || 'No se pudieron cargar.' };
    return { conectores: datos.conectores ?? [], roles };
  } catch (/** @type {any} */ err) {
    console.error('[conectores] motor inalcanzable:', err?.message);
    return { conectores: [], roles, error: 'No se pudo contactar al asistente.' };
  }
}
