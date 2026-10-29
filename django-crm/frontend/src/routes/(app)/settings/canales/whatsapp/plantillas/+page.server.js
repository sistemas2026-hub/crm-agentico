import { fail } from '@sveltejs/kit';
import {
  borrarPlantilla,
  cambiarUsoDePlantilla,
  crearPlantilla,
  leerMensajesAutomaticos,
  listarPlantillas
} from '$lib/server/v2/canal-whatsapp.js';

/*
 * Plantillas de WhatsApp desde Ajustes (28/10/2026): verlas en cualquier
 * estado, mandar una nueva a revisión de Meta y borrarlas. Antes se hacía
 * desde el panel de Meta, y Dexter solo podía leer las aprobadas.
 */

const SOLO_ADMIN = 'Solo un administrador puede cambiar las plantillas.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals, url }) {
  const [plantillas, mensajes] = await Promise.all([
    listarPlantillas(locals, fetch),
    leerMensajesAutomaticos(locals, fetch)
  ]);
  //  Una plantilla de partida por momento (29/10/2026), menos las que la
  //  empresa ya tiene con ese nombre. Si Meta no contesta no se sabe cuáles
  //  existen, y tampoco se podría crear: no se ofrece ninguna.
  const existentes = new Set((plantillas ?? []).map((/** @type {any} */ p) => p.nombre));
  const sugeridas =
    plantillas === null
      ? []
      : (mensajes?.eventos ?? [])
          .filter((/** @type {any} */ e) => e.sugerencia && !existentes.has(e.sugerencia.nombre))
          .map((/** @type {any} */ e) => ({
            clave: e.clave,
            grupo: e.grupo,
            etiqueta: e.etiqueta,
            sugerencia: e.sugerencia
          }));
  return {
    plantillas,
    sugeridas,
    //  Desde Mensajes automáticos: abre el formulario con la de ese momento.
    sugerida: url?.searchParams.get('sugerida') ?? null,
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

  /** Activar o desactivar una plantilla para esta empresa (28/10/2026). */
  async uso({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const form = await request.formData();
    const nombre = form.get('nombre')?.toString().trim() ?? '';
    if (!nombre) return fail(400, { error: 'Falta el nombre.' });
    try {
      const r = await cambiarUsoDePlantilla(locals, fetch, nombre, form.get('en_uso') === '1');
      return { uso: { nombre, enUso: r.en_uso, momentos: r.momentos_que_la_usan ?? [] } };
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo cambiar.' });
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
