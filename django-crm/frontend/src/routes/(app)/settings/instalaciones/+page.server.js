/**
 * Ajustes → Instalaciones: los dos equipos de WispHub del flujo.
 *
 * Uno recibe la solicitud nueva (valida si el servicio llega a esa dirección),
 * el otro la ejecuta. Se eligen de una lista traída de WispHub, no se
 * escriben: un id tipeado mal es un ticket a nombre de nadie.
 */
import { fail } from '@sveltejs/kit';
import { guardarAjustes, leerAjustes, leerTecnicos } from '$lib/server/v2/solicitudes.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  const [ajustes, tecnicos] = await Promise.all([leerAjustes(fetch), leerTecnicos(fetch)]);
  return { ajustes, tecnicos, can_edit: locals.profile?.role === 'ADMIN' };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, fetch, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    const valores = {
      tecnico_solicitudes: form.get('tecnico_solicitudes')?.toString() ?? '',
      email_solicitudes: form.get('email_solicitudes')?.toString() ?? '',
      tecnico_aprobadas: form.get('tecnico_aprobadas')?.toString() ?? '',
      email_aprobadas: form.get('email_aprobadas')?.toString() ?? ''
    };
    if (!valores.tecnico_solicitudes || !valores.tecnico_aprobadas) {
      return fail(400, { error: 'Hay que elegir los dos equipos.' });
    }
    try {
      await guardarAjustes(fetch, valores);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar.' });
    }
    return { guardado: true };
  }
};
