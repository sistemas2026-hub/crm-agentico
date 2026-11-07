import { fail } from '@sveltejs/kit';
import { guardarLinkDePago, leerLinkDePago } from '$lib/server/v2/pagos-config.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  return {
    ajustes: await leerLinkDePago(locals, fetch),
    // El motor no tiene identidad propia: quien decide si esto se puede editar
    // es el CRM. Esto es la afordancia (esconder el botón); la acción vuelve a
    // comprobarlo, porque ocultar un botón no es un control de acceso.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { guardar: { error: 'Solo un administrador puede cambiar el link de pago.' } });
    }
    const form = await request.formData();
    const link = form.get('link_de_pago')?.toString() ?? '';
    try {
      await guardarLinkDePago(locals, fetch, link);
    } catch (/** @type {any} */ err) {
      return fail(400, { guardar: { error: err?.message || 'No se pudo guardar.' } });
    }
    return { guardado: true };
  }
};
