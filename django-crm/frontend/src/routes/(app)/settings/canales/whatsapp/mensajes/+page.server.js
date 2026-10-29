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
  /**
   * El interruptor de la cabecera (28/10/2026): enciende o apaga AL INSTANTE,
   * con la plantilla y los datos que ya estaban guardados. Encender un armado
   * incompleto lo rechaza el motor, y el motivo vuelve a su momento.
   */
  async encender({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const form = await request.formData();
    const evento = form.get('evento')?.toString() ?? '';
    if (!evento) return fail(400, { error: 'Falta el momento.' });
    const valores = {
      activo: form.get('activo') === '1',
      plantilla: form.get('plantilla')?.toString() ?? '',
      datos: form.getAll('dato').map((d) => d.toString())
    };
    try {
      await guardarMensajeAutomatico(locals, fetch, evento, valores);
      return { guardado: evento };
    } catch (/** @type {any} */ err) {
      return fail(400, { evento, error: err?.message || 'No se pudo cambiar.' });
    }
  },

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
