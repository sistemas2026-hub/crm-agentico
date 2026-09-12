import { fail } from '@sveltejs/kit';
import { leerGuiasTV, guardarGuiasTV } from '$lib/server/v2/guias-tv.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const datos = await leerGuiasTV();
  return {
    guias: datos?.guias_tv ?? [],
    // Los tipos válidos los manda el motor: la pantalla no tiene por qué
    // conocer las reglas de negocio para dibujar su selector, y así agregar
    // un tipo nuevo no exige tocar dos repositorios.
    tipos: datos?.tipos_conexion ?? ['directo', 'tdt'],
    huboRespuesta: datos !== null,
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    /** @type {any[]} */
    let guias;
    try {
      guias = JSON.parse(form.get('datos')?.toString() ?? '[]');
    } catch {
      return fail(400, { error: 'Los datos del formulario llegaron mal formados.' });
    }

    try {
      await guardarGuiasTV(guias);
    } catch (/** @type {any} */ err) {
      // El motivo del motor viaja TAL CUAL. Sus mensajes no dicen solo qué
      // falló: dicen por qué esa regla existe («con TDT quien sintoniza es la
      // cajita, no el televisor»). Resumirlo dejaría a quien edita sabiendo
      // que no puede, sin saber por qué.
      return fail(400, { error: err?.message || 'No se pudieron guardar las guías.' });
    }
    return { guardado: true };
  }
};
