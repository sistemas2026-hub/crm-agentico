import { fail } from '@sveltejs/kit';
import { guardarMensajeAutomatico, leerMensajesAutomaticos } from '$lib/server/v2/canal-whatsapp.js';

/*
 * Mensajes automáticos (28/10/2026): para cada momento en que Dexter le escribe
 * a alguien por plantilla, qué plantilla usa y qué dato va en cada {{n}}.
 * Reemplaza la pantalla de avisos del CRM anterior. Solo administradores
 * cambian; el motor valida contra Meta antes de encender.
 */

const SOLO_ADMIN = 'Solo un administrador puede cambiar los mensajes automáticos.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  return {
    mensajes: await leerMensajesAutomaticos(locals, fetch),
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const form = await request.formData();
    const evento = form.get('evento')?.toString() ?? '';
    const valores = {
      activo: form.get('activo') === 'on',
      plantilla: form.get('plantilla')?.toString() ?? '',
      //  En orden: el primero es {{1}}, el segundo {{2}}... Uno vacío no se manda.
      datos: form.getAll('dato').map((d) => d.toString())
    };
    if (!evento) return fail(400, { error: 'Falta el momento.' });
    if (valores.datos.some((d) => !d)) {
      return fail(400, { evento, error: 'Elegí qué dato va en cada lugar de la plantilla.' });
    }
    try {
      await guardarMensajeAutomatico(locals, fetch, evento, valores);
      return { guardado: evento };
    } catch (/** @type {any} */ err) {
      return fail(400, { evento, error: err?.message || 'No se pudo guardar.' });
    }
  }
};
