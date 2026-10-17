import { json } from '@sveltejs/kit';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { destinoDelAsistente } from '$lib/server/v2/tenant.js';

/**
 * Proxy hacia el motor para los conectores: conectar un sistema conocido
 * eligiéndolo de una lista. Ver nucleo/conectores/catalogo.py.
 *
 * Solo ADMIN. Aplicar un conector escribe herramientas que acceden a datos de
 * clientes y decide qué rol ve qué campos — es la superficie más sensible de
 * toda la configuración.
 *
 * Dos acciones distintas a propósito:
 *   preparar  dice qué va a pasar, sin escribir nada
 *   aplicar   escribe
 *
 * Que se pueda mirar antes no es cortesía: es lo que hace que la decisión sea
 * de una persona y no del que apretó el botón.
 */

async function guardia(locals, fetch) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede conectar sistemas.' }, { status: 403 });
  }
  if (!(await destinoDelAsistente(locals, fetch))) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }
  return null;
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ locals, fetch }) {
  const negado = await guardia(locals, fetch);
  if (negado) return negado;
  const { baseUrl } = /** @type {any} */ (await destinoDelAsistente(locals, fetch));

  try {
    const resp = await fetch(`${baseUrl}/conectores`, { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) return json({ error: datos.error || 'No se pudo leer.' }, { status: resp.status });
    return json(datos);
  } catch (/** @type {any} */ err) {
    console.error('[conectores] motor inalcanzable:', err?.message);
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}

export async function POST({ locals, request, fetch }) {
  const negado = await guardia(locals, fetch);
  if (negado) return negado;
  const { baseUrl, tenant } = /** @type {any} */ (await destinoDelAsistente(locals, fetch));

  const cuerpo = await request.json().catch(() => ({}));
  const { accion, id, areas } = cuerpo ?? {};
  if (!id || (accion !== 'preparar' && accion !== 'aplicar')) {
    return json({ error: 'Acción desconocida.' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conectores/${encodeURIComponent(id)}/${accion}`, {
      method: 'POST',
      headers: { ...headersMotor(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenant, areas: areas ?? {} })
    });
    const datos = await resp.json();
    if (!resp.ok) return json({ error: datos.error || 'No se pudo procesar.' }, { status: resp.status });
    return json(datos);
  } catch (/** @type {any} */ err) {
    console.error('[conectores] motor inalcanzable:', err?.message);
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
