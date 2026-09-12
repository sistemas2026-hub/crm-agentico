import { fail } from '@sveltejs/kit';
import {
  guardarPlanesVenta,
  leerPlanesVenta,
  sincronizarLocalidades
} from '$lib/server/v2/planes-venta.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const datos = await leerPlanesVenta();
  return {
    catalogo: datos?.catalogo ?? [],
    errorCatalogo: datos?.error_catalogo ?? null,
    planesVenta: datos?.planes_venta ?? [],
    localidades: datos?.localidades ?? [],
    localidadesActualizadoEn: datos?.localidades_actualizado_en ?? null,
    huboRespuesta: datos !== null,
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN, action: 'guardar' });

    const form = await request.formData();
    const crudo = form.get('datos')?.toString() ?? '[]';
    /** @type {any[]} */
    let planes;
    try {
      planes = JSON.parse(crudo);
    } catch {
      return fail(400, {
        error: 'Los datos del formulario llegaron mal formados.',
        action: 'guardar'
      });
    }

    try {
      await guardarPlanesVenta(planes);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudo guardar la lista de planes.',
        action: 'guardar'
      });
    }
    return { guardado: true };
  },

  async sincronizar({ locals }) {
    if (locals.profile?.role !== 'ADMIN')
      return fail(403, { error: SOLO_ADMIN, action: 'sincronizar' });

    try {
      await sincronizarLocalidades();
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudo sincronizar las localidades.',
        action: 'sincronizar'
      });
    }
    return { sincronizado: true };
  }
};
