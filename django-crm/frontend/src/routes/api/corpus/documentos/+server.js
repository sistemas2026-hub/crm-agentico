import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Documentos del corpus: listar (GET, cualquier miembro logueado) y subir
 * uno nuevo (POST, solo ADMIN -- decidir que documentos alimentan al bot y a
 * que roles se les muestra es un cambio de superficie de seguridad, mismo
 * criterio que crear un agente en /api/agentes).
 *
 * Proxy hacia nucleo/canales/api.py: GET /corpus/documentos, POST
 * /corpus/documentos.
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
    const resp = await fetch(`${cfg.baseUrl}/corpus/documentos?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron leer los documentos' }, { status: resp.status });
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
    return json({ error: 'Solo un administrador puede subir documentos.' }, { status: 403 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  // El unico endpoint del motor que recibe multipart en vez de JSON (trae un
  // archivo). Se reenvia el FormData tal cual llego -- swapear el 'tenant'
  // adentro, nunca confiar en uno que mande el cliente.
  const entrante = await request.formData();
  const saliente = new FormData();
  for (const [clave, valor] of entrante.entries()) {
    if (clave === 'tenant') continue;
    saliente.append(clave, valor);
  }
  saliente.append('tenant', cfg.tenant);

  try {
    const resp = await fetch(`${cfg.baseUrl}/corpus/documentos`,
      { method: 'POST', headers: headersMotor(), body: saliente });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo cargar el documento' }, { status: resp.status });
    }
    return json(datos, { status: 201 });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
