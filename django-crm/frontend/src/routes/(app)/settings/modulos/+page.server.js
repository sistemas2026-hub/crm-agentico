import { fail, redirect } from '@sveltejs/kit';
import { leerModulosOcultos, guardarModulosOcultos } from '$lib/server/v2/modulos.js';

/**
 * Módulos del menú (12/11/2026): qué pantallas heredadas del CRM saca esta
 * empresa de su menú. Solo ADMIN, en el servidor: un miembro que llega por la
 * URL vuelve al hub. El backend vuelve a exigir ADMIN al guardar.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, cookies }) {
  if (locals.profile?.role !== 'ADMIN') redirect(303, '/settings');
  const { ocultos } = await leerModulosOcultos({ cookies });
  return { ocultos };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, locals, cookies }) {
    const r = await guardarModulosOcultos(
      { cookies },
      locals.profile?.role,
      await request.formData()
    );
    if ('error' in r) return fail(r.status, { error: r.error });
    return { guardado: true, ocultos: r.ocultos };
  }
};
