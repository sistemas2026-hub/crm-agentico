import { fail, redirect } from '@sveltejs/kit';
import { borrarVariable, guardarVariable, leerVariables } from '$lib/server/v2/variables-empresa.js';

/*
 * Variables de la empresa (12/11/2026). Solo ADMIN, como Conectores, que es
 * desde donde se llega después de conectar un sistema: estas variables dicen a
 * qué servidor le habla cada herramienta. La puerta está acá, en el servidor,
 * en la carga y en cada acción.
 */

const SOLO_ADMIN = 'Solo un administrador puede cambiar las variables de la empresa.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals, url }) {
  if (locals.profile?.role !== 'ADMIN') redirect(303, '/settings');
  return {
    datos: await leerVariables(locals, fetch),
    //  /conectores manda acá con ?nombre=X para la que falta: llega precargada.
    sugerida: (url.searchParams.get('nombre') ?? '').toUpperCase()
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const form = await request.formData();
    const nombre = form.get('nombre')?.toString() ?? '';
    try {
      await guardarVariable(locals, fetch, nombre, form.get('valor')?.toString() ?? '');
      return { guardada: nombre.trim().toUpperCase() };
    } catch (/** @type {any} */ err) {
      return fail(400, { nombre, error: err?.message || 'No se pudo guardar.' });
    }
  },

  async borrar({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });
    const nombre = (await request.formData()).get('nombre')?.toString() ?? '';
    try {
      await borrarVariable(locals, fetch, nombre);
      return { borrada: nombre };
    } catch (/** @type {any} */ err) {
      return fail(400, { nombre, error: err?.message || 'No se pudo quitar.' });
    }
  }
};
