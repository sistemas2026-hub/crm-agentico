import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy hacia el motor para continuar una conversación abierta desde la
 * bandeja -- mismo patrón que /api/simulador-whatsapp, pero la identidad
 * (usuario_externo, rol_efectivo, canal) viene de la conversación ya
 * cargada en la página, no de un campo de teléfono a mano: seguimos EL
 * MISMO hilo, no arrancamos uno nuevo.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { mensaje, usuario_externo, rol_efectivo, canal } = await request.json();
  // Sin canal no se adivina. Antes caía en 'whatsapp-simulado', que
  // re-etiquetaba en silencio cualquier hilo; y un hilo real de WhatsApp lo
  // rechaza el motor (403): /chat no le escribe al cliente, solo guardaría un
  // mensaje que el cliente no mandó (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D3).
  if (!mensaje || !usuario_externo || !canal) {
    return json({ error: 'Falta mensaje, usuario_externo o canal' }, { status: 400 });
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
        rol: rol_efectivo || 'cliente_final',
        identificador_sesion: usuario_externo,
        mensaje,
        // El canal original de la conversacion, tal cual: el motor es quien
        // decide si ese canal se puede atender por /chat.
        canal
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

/**
 * SOLO PARA PRUEBAS -- borra la conversacion entera para poder reescribirle
 * al bot desde el WhatsApp real sin arrastrar el contexto de la prueba
 * anterior (rol derivado, si ya escalo, el historial). Ver el boton
 * "Reiniciar (prueba)" en +page.svelte y nucleo/canales/api.py:
 * conversaciones_borrar -- sacar los dos cuando termine esa etapa.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function DELETE({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}?tenant=${tenant}`, {
      method: 'DELETE', headers: headersMotor()
    });
    if (!resp.ok) {
      const datos = await resp.json().catch(() => ({}));
      return json({ error: datos.error || 'No se pudo borrar' }, { status: resp.status });
    }
    return new Response(null, { status: 204 });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
