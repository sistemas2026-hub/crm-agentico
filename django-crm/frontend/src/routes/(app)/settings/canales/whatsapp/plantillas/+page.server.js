import { fail } from '@sveltejs/kit';
import {
  borrarPlantilla,
  crearPlantilla,
  listarPlantillas
} from '$lib/server/v2/canal-whatsapp.js';

/*
 * Plantillas de WhatsApp desde Ajustes (28/10/2026): verlas en cualquier
 * estado, mandar una nueva a revisión de Meta y borrarlas. Antes se hacía
 * desde el panel de Meta, y Dexter solo podía leer las aprobadas.
 */

const SOLO_ADMIN = 'Solo un administrador puede cambiar las plantillas.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  return {
    plantillas: await listarPlantillas(locals, fetch),
    // Afordancia, no permiso: cada action lo vuelve a comprobar.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @param {FormData} form */
function leer(form) {
  const texto = (/** @type {string} */ k) => form.get(k)?.toString() ?? '';
  return {
    nombre: texto('nombre').trim(),
    categoria: texto('categoria'),
    idioma: texto('idioma').trim() || 'es',
    encabezado: texto('encabezado'),
    cuerpo: texto('cuerpo'),
    pie: texto('pie'),
    ejemplos: form.getAll('ejemplo').map((v) => v.toString()),
    botones: form.getAll('boton').map((v) => v.toString()).filter((b) => b.trim())
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async crear({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const plantilla = leer(await request.formData());
    try {
      const creada = await crearPlantilla(locals, fetch, plantilla);
      return { creada };
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'Meta no aceptó la plantilla.', valores: plantilla });
    }
  },

  async borrar({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const nombre = (await request.formData()).get('nombre')?.toString().trim() ?? '';
    if (!nombre) return fail(400, { error: 'Falta el nombre.' });
    try {
      await borrarPlantilla(locals, fetch, nombre);
      return { borrada: nombre };
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'Meta no borró la plantilla.' });
    }
  }
};
