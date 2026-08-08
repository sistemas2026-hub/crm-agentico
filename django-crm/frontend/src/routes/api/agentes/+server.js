import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Proxy hacia el motor del asistente para listar el catalogo de herramientas
 * (GET, cualquier miembro logueado) y crear un agente nuevo (POST, solo
 * ADMIN -- elegir que datos puede ver un agente es un cambio de superficie
 * de seguridad, no una accion de cualquier miembro). Mismo patron que
 * /api/simulador-whatsapp: tenant sale de PRIVATE_ASISTENTE_TENANT en el
 * servidor, nunca del cliente.
 */

function baseUrlYTenant() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${cfg.baseUrl}/agentes/catalogo?tenant=${encodeURIComponent(cfg.tenant)}`);
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo cargar el catalogo' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede crear agentes.' }, { status: 403 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json();

  try {
    const resp = await fetch(`${cfg.baseUrl}/agentes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cuerpo, tenant: cfg.tenant })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo crear el agente' }, { status: resp.status });
    }
    return json(datos, { status: 201 });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
