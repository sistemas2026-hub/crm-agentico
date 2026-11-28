import { fail } from '@sveltejs/kit';
import { leerAjustes, cambiarTarea } from '$lib/server/v2/ajustes-supervisor.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';
import { zonaDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';

/**
 * Ajustes del Supervisor — Supervisor NOC (27/10/2026).
 *
 * Cada tarea que se le puede delegar al Supervisor, con un interruptor para
 * delegarla o quitarla. Hasta hoy eso solo se hacía hablándole al chat, y un
 * Supervisor que va a publicar solo tiene que poder apagarse con un clic, por
 * alguien que no quiere pedírselo a una IA.
 *
 * QUIÉN PUEDE: la gestión, como el resto del Supervisor. El backend lo exige
 * con un 403; acá se repite para no pedir nada que va a fallar, y para que la
 * pantalla diga el motivo en vez de un error.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @param {any} locals */
const gestiona = (locals) => ROLES_GESTION.has(locals?.profile?.role);

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals }) {
  if (!gestiona(locals)) return { puedeVer: false, ajustes: null, error: null, zona: 'UTC' };
  //  Las fechas de «delegada el…» en el reloj de la EMPRESA, no fijas en
  //  Bogotá: esto es multi-empresa (CLAUDE.md §3.3).
  const zona = await zonaDeLaEmpresa(locals, cookies);
  try {
    return { puedeVer: true, ajustes: await leerAjustes({ cookies }), error: null, zona };
  } catch (e) {
    return {
      puedeVer: true,
      ajustes: null,
      error: mensajeDeError(e, 'No se pudieron leer las tareas del Supervisor.'),
      zona
    };
  }
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Delegar o quitar UNA tarea. Viaja el estado que se quiere, no «invertir»:
   * si alguien la cambió mientras tanto, el backend contesta 409 y no pisa su
   * registro.
   */
  cambiar: async ({ request, cookies, locals }) => {
    if (!gestiona(locals)) {
      return fail(403, {
        error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede cambiar las tareas del Supervisor.'
      });
    }
    const f = await request.formData();
    const clave = String(f.get('clave') ?? '');
    const delegar = String(f.get('delegar') ?? '');
    //  SOLO 'si' o 'no'. Cualquier otra cosa no se adivina: leerla como verdad
    //  encendería una tarea que alguien quiso apagar.
    if (delegar !== 'si' && delegar !== 'no') {
      return fail(400, { error: 'Falta decir si se delega o se quita.', clave });
    }
    const motivo = String(f.get('motivo') ?? '').trim();
    if (!motivo) {
      return fail(400, { error: 'Escribí el motivo: queda registrado con tu nombre.', clave });
    }
    try {
      await cambiarTarea({ cookies }, { clave, delegar: delegar === 'si', motivo });
    } catch (e) {
      return fail(/** @type {any} */ (e)?.status ?? 502, {
        error: mensajeDeError(e, 'No se pudo cambiar la tarea.'),
        clave
      });
    }
    return {
      hecho: delegar === 'si'
        ? 'La tarea quedó delegada.'
        : 'La tarea quedó quitada: el Supervisor deja de hacerla desde la próxima vuelta.',
      clave
    };
  }
};
