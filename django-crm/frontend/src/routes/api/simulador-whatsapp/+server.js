import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy hacia el motor del asistente, mismo patron que /api/asistente, pero
 * simulando un remitente de WhatsApp: la identidad no sale de la sesion
 * logueada (locals.user) sino del numero de telefono que ingresa quien
 * prueba -- eso es justamente lo que hay que poder variar para probar
 * distintos clientes. Sigue exigiendo estar logueado en BottleCRM: es una
 * herramienta de prueba para el equipo, no un endpoint publico.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  // Los mensajes de una conversacion, para que el simulador vea llegar lo que
  // escribe un colaborador desde el ticket sin recargar la pagina.
  //
  // En WhatsApp de verdad ese mensaje sale por el canal y le llega al celular
  // del cliente; aca el "celular" es esta pantalla, y nadie le avisa. Antes
  // habia que recargar para enterarse, y probando una conversacion a dos
  // manos eso hace perder el hilo justo en el momento que se quiere mirar.
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const conversacion = url.searchParams.get('conversacion');
  if (!conversacion) {
    return json({ error: 'Falta el parametro conversacion' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado' }, { status: 500 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${conversacion}/mensajes?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(8000) }
    );
    if (!resp.ok) return json({ mensajes: [] });
    const datos = await resp.json();
    return json({
      mensajes: (datos.mensajes ?? []).map((/** @type {any} */ m) => ({
        id: m.id, rol: m.rol, texto: m.contenido, creado_en: m.creado_en
      })),
      cerrada: datos.conversacion?.estado === 'cerrada'
    });
  } catch (/** @type {any} */ err) {
    // Sin ruido: esto corre cada pocos segundos y un fallo puntual no tiene
    // que llenar la pantalla de errores -- el proximo intento lo resuelve.
    return json({ mensajes: [] });
  }
}

export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { telefono, mensaje } = await request.json();
  if (!telefono || !mensaje) {
    return json({ error: 'Falta telefono o mensaje' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        rol: 'cliente_final',
        identificador_sesion: telefono,
        mensaje,
        // Canal propio para que el simulador nunca se confunda con trafico
        // real de WhatsApp una vez que ese canal exista de verdad.
        canal: 'whatsapp-simulado'
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'El asistente no respondio' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
