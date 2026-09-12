/**
 * Credenciales del asistente.
 *
 * El valor se manda en un solo sentido y nunca vuelve: la carga se hace desde
 * el servidor para que el secreto no pase por el navegador más que en el envío
 * del formulario, igual que hace la pantalla de tokens de API.
 */
import { fail } from '@sveltejs/kit';

import {
  borrarCredencial,
  guardarCredencial,
  leerCredenciales
} from '$lib/server/v2/credenciales.js';

export async function load() {
  return await leerCredenciales();
}

export const actions = {
  guardar: async ({ request }) => {
    const form = await request.formData();
    const nombre = (form.get('nombre') ?? '').toString().trim();
    const valor = (form.get('valor') ?? '').toString().trim();
    const descripcion = (form.get('descripcion') ?? '').toString().trim();
    if (!nombre) return fail(400, { error: 'Falta el nombre de la credencial.' });
    if (!valor) return fail(400, { error: 'Pegá el valor de la credencial.' });

    const r = await guardarCredencial(nombre, valor, descripcion);
    if (!r.ok) return fail(400, { error: r.error });
    return { guardado: nombre };
  },

  borrar: async ({ request }) => {
    const form = await request.formData();
    const nombre = (form.get('nombre') ?? '').toString().trim();
    if (!nombre) return fail(400, { error: 'Falta el nombre.' });
    const r = await borrarCredencial(nombre);
    if (!r.ok) return fail(400, { error: r.error });
    return { borrado: nombre };
  }
};
