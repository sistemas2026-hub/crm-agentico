import { json } from '@sveltejs/kit';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { destinoDelAsistente } from '$lib/server/v2/tenant.js';

/**
 * Proxy hacia el motor para las habilidades: los procedimientos que un agente
 * carga cuando le hacen falta (ver nucleo/habilidades/catalogo.py).
 *
 * TODO es solo ADMIN, lectura incluida -- a diferencia de /api/agentes, donde
 * el catalogo se puede leer sin ser admin. Motivo: una habilidad vigente es lo
 * que un agente va a seguir "al pie de la letra" frente a un cliente, y las
 * propuestas del analista traen los identificadores de las conversaciones que
 * las motivaron. Es superficie de configuracion y de auditoria, no una
 * pantalla de consulta.
 *
 * El tenant sale del entorno del servidor, nunca del cliente -- mismo patron
 * que /api/agentes y /api/configuracion-guiada.
 */

/** Gate comun: ADMIN autenticado y motor configurado. */
async function guardia(locals, fetch) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede ver los procedimientos.' },
      { status: 403 });
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

  // 'huecos' no es una habilidad: es el analisis de que le falta a cada
  // agente. Se sirve por la misma ruta para no multiplicar proxies, pero
  // pega contra otro endpoint del motor.
  const quiereHuecos = url.searchParams.get('huecos') === '1';
  const dias = url.searchParams.get('dias') || '30';
  const destino = quiereHuecos
    ? `${baseUrl}/habilidades/huecos?tenant=${encodeURIComponent(tenant)}&dias=${encodeURIComponent(dias)}`
    : `${baseUrl}/habilidades?tenant=${encodeURIComponent(tenant)}`;

  try {
    const resp = await fetch(destino, { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer.' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    console.error('[habilidades] motor inalcanzable:', err?.message);
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}

/**
 * Crear, aprobar, retirar y pedir propuestas. Una sola ruta con 'accion' en el
 * cuerpo en vez de cuatro archivos: son cuatro llamadas a la misma entidad, y
 * el gate de ADMIN es identico en todas.
 */
export async function POST({ locals, request, fetch }) {
  const negado = await guardia(locals, fetch);
  if (negado) return negado;
  const { baseUrl, tenant } = /** @type {any} */ (await destinoDelAsistente(locals, fetch));

  const cuerpo = await request.json().catch(() => ({}));
  const { accion, id, ...resto } = cuerpo ?? {};

  const rutas = {
    crear: '/habilidades',
    aprobar: `/habilidades/${id}/aprobar`,
    retirar: `/habilidades/${id}/retirar`,
    proponer: '/habilidades/proponer'
  };
  const ruta = rutas[accion];
  if (!ruta || ((accion === 'aprobar' || accion === 'retirar') && !id)) {
    return json({ error: 'Acción desconocida.' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${baseUrl}${ruta}`, {
      method: 'POST',
      headers: { ...headersMotor(), 'Content-Type': 'application/json' },
      // Quien aprueba queda registrado: una habilidad vigente es una decisión
      // de alguien, y despues hay que poder preguntar de quién.
      body: JSON.stringify({ ...resto, tenant, aprobada_por: locals.user?.email })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo guardar.' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    console.error('[habilidades] motor inalcanzable:', err?.message);
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
