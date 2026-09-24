import { json } from '@sveltejs/kit';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { destinoDelAsistente } from '$lib/server/v2/tenant.js';

/**
 * Proxy hacia el motor para el consumo: cuánto gasta la empresa y en qué punto
 * del tope está. Ver nucleo/observabilidad/consumo.py.
 *
 * Solo ADMIN, lectura incluida. El gasto de la empresa y su tope son datos de
 * administración, no de operación: un colaborador de soporte no tiene por qué
 * ver la factura, y el PUT cambia cuánto puede gastar el asistente antes de
 * frenar — eso es dinero, no una preferencia.
 *
 * El tenant sale del entorno del servidor, nunca del cliente.
 */

async function guardia(locals, fetch) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede ver el consumo.' }, { status: 403 });
  }
  if (!(await destinoDelAsistente(locals, fetch))) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }
  return null;
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ locals, fetch, url }) {
  const negado = await guardia(locals, fetch);
  if (negado) return negado;
  const { baseUrl, tenant } = /** @type {any} */ (await destinoDelAsistente(locals, fetch));
  const dias = url.searchParams.get('dias') || '30';

  try {
    const resp = await fetch(
      `${baseUrl}/consumo?tenant=${encodeURIComponent(tenant)}&dias=${encodeURIComponent(dias)}`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) return json({ error: datos.error || 'No se pudo leer.' }, { status: resp.status });
    return json(datos);
  } catch (/** @type {any} */ err) {
    console.error('[consumo] motor inalcanzable:', err?.message);
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}

/**
 * Guarda la tarifa de un modelo o el tope mensual, según `accion`. Una sola
 * ruta porque son la misma pantalla y el mismo gate; separarlas serían dos
 * archivos con el mismo encabezado.
 */
export async function PUT({ locals, request, fetch }) {
  const negado = await guardia(locals, fetch);
  if (negado) return negado;
  const { baseUrl, tenant } = /** @type {any} */ (await destinoDelAsistente(locals, fetch));

  const cuerpo = await request.json().catch(() => ({}));
  const { accion, ...resto } = cuerpo ?? {};
  const ruta = accion === 'tarifa' ? '/consumo/tarifa' : accion === 'tope' ? '/consumo/tope' : null;
  if (!ruta) return json({ error: 'Acción desconocida.' }, { status: 400 });

  try {
    const resp = await fetch(`${baseUrl}${ruta}`, {
      method: 'PUT',
      headers: { ...headersMotor(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...resto, tenant })
    });
    const datos = await resp.json();
    if (!resp.ok) return json({ error: datos.error || 'No se pudo guardar.' }, { status: resp.status });
    return json(datos);
  } catch (/** @type {any} */ err) {
    console.error('[consumo] motor inalcanzable:', err?.message);
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
