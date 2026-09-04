import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * El hilo de una conversación del asistente, para pantallas que lo miran
 * mientras pasa.
 *
 * Existe porque la conversación sigue viva después de que el caso llega a la
 * bandeja: el cliente escribe, y quien atiende está mirando el ticket. La
 * transcripción que guarda el caso es una FOTO del momento en que se escaló
 * -- es el registro que se audita y no se toca -- así que lo que viene
 * después hay que pedirlo aparte.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ mensajes: [] });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${params.id}/mensajes?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(8000) }
    );
    if (!resp.ok) return json({ mensajes: [] });
    const datos = await resp.json();
    return json({
      mensajes: (datos.mensajes ?? []).map((/** @type {any} */ m) => ({
        id: m.id,
        // 'humano' distingue lo que escribió una persona del equipo de lo que
        // escribió el asistente. Los dos salen por el mismo lado del canal
        // --el cliente ve un solo interlocutor-- pero quien atiende necesita
        // saber cuál es cuál para no responder dos veces lo mismo.
        quien: m.rol === 'user' ? 'cliente' : m.rol === 'humano' ? 'humano' : 'asistente',
        texto: m.contenido,
        creado_en: m.creado_en
      })),
      atendida_por: datos.conversacion?.atendida_por ?? '',
      cerrada: datos.conversacion?.estado === 'cerrada'
    });
  } catch {
    // Sin ruido: la pantalla lo pregunta cada pocos segundos y un fallo
    // puntual se resuelve en la siguiente.
    return json({ mensajes: [] });
  }
}
