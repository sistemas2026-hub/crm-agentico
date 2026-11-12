/**
 * /settings/modulos, del lado del servidor  --  12/11/2026
 *
 * Qué módulos heredados del CRM saca esta empresa de su menú. Se guarda en
 * `Org.modulos_ocultos` por `PATCH /api/org/settings/`, la misma ruta (y la
 * misma puerta de ADMIN) que el resto de los datos de la organización.
 *
 * DOS PUERTAS, Y LA QUE MANDA ES LA DEL BACKEND. Esta capa rechaza a quien no
 * es ADMIN sin viajar (403), y el backend lo vuelve a rechazar si alguien llega
 * por otro lado. La de acá existe para no mandar un pedido que se sabe
 * rechazado, no porque alcance sola.
 *
 * LEER ANTES DE ESCRIBIR, SIEMPRE DE LA FUENTE. La pantalla no reusa lo que
 * trajo el layout: si esa lectura venció su plazo de 2 s, llegaría «nada
 * oculto» y guardar desde ahí borraría lo que la empresa había ocultado. Si la
 * lectura propia falla, la pantalla no ofrece guardar.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { MODULOS_OCULTABLES, ocultosConocidos } from '$lib/v2/modulos.js';

export const SOLO_ADMIN = 'Solo un administrador puede cambiar qué se ve en el menú.';

/**
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @returns {Promise<{ ocultos: string[] | null }>}  null = no se pudo leer
 */
export async function leerModulosOcultos({ cookies }) {
  try {
    const org = await apiRequest('/org/settings/', {}, { cookies });
    return { ocultos: [...ocultosConocidos(org?.modulos_ocultos)] };
  } catch {
    return { ocultos: null };
  }
}

/**
 * Guarda la selección del formulario: una casilla `oculto` por módulo marcado.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string | null | undefined} rol  del JWT, leído en el servidor
 * @param {FormData} form
 * @returns {Promise<{ ok: true, ocultos: string[] } | { ok: false, status: number, error: string }>}
 */
export async function guardarModulosOcultos({ cookies }, rol, form) {
  if (rol !== 'ADMIN') return { ok: false, status: 403, error: SOLO_ADMIN };
  const claves = new Set(MODULOS_OCULTABLES.map((m) => m.clave));
  const pedidos = form.getAll('oculto').map(String);
  // Una clave que esta pantalla no ofreció no viaja: es un formulario
  // fabricado o una pantalla vieja, y en los dos casos no hay que adivinar.
  if (pedidos.some((p) => !claves.has(p))) {
    return { ok: false, status: 400, error: 'Llegó un módulo que esta pantalla no ofrece.' };
  }
  try {
    const org = await apiRequest(
      '/org/settings/',
      { method: 'PATCH', body: { modulos_ocultos: pedidos } },
      { cookies }
    );
    return { ok: true, ocultos: [...ocultosConocidos(org?.modulos_ocultos)] };
  } catch (/** @type {any} */ err) {
    if (err?.status === 403) return { ok: false, status: 403, error: SOLO_ADMIN };
    return { ok: false, status: 400, error: 'No se pudo guardar. Probá de nuevo en un momento.' };
  }
}
