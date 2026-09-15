import { fail } from '@sveltejs/kit';
import { leerOferta, guardarServicios, subirParrilla } from '$lib/server/v2/oferta.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const datos = await leerOferta();
  return {
    servicios: datos?.servicios_ofrecidos ?? [],
    canales: datos?.parrilla_canales ?? [],
    huboRespuesta: datos !== null,
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardarServicios({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN')
      return fail(403, { error: SOLO_ADMIN, action: 'guardarServicios' });

    const form = await request.formData();
    /** @type {any[]} */
    let servicios;
    try {
      servicios = JSON.parse(form.get('datos')?.toString() ?? '[]');
    } catch {
      return fail(400, {
        error: 'Los datos del formulario llegaron mal formados.',
        action: 'guardarServicios'
      });
    }

    try {
      await guardarServicios(servicios);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudieron guardar los servicios.',
        action: 'guardarServicios'
      });
    }
    return { guardado: true };
  },

  async subirParrilla({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN')
      return fail(403, { error: SOLO_ADMIN, action: 'subirParrilla' });

    const form = await request.formData();
    const archivo = form.get('archivo');
    if (!(archivo instanceof File) || archivo.size === 0) {
      return fail(400, { error: 'Elegí un archivo .xlsx primero.', action: 'subirParrilla' });
    }

    try {
      const datos = await subirParrilla(archivo);
      // Los descartados viajan de vuelta a proposito: si no se muestran,
      // quien subio el archivo cree que cargo mas canales de los que cargo.
      return {
        subido: true,
        total: datos.total,
        descartados: datos.descartados ?? []
      };
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudo cargar la parrilla.',
        action: 'subirParrilla'
      });
    }
  }
};
