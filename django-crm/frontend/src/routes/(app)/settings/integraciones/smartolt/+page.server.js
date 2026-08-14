import { fail } from '@sveltejs/kit';
import { borrarSecreto, guardarSecreto, listarSecretos } from '$lib/server/v2/canal-whatsapp.js';
import { probarConexionSmartolt } from '$lib/server/v2/integracion-smartolt.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

// Nombres de secreto fijos para esta integracion -- todavia no hay una
// Herramienta en el catalogo del tenant que los declare (a diferencia de
// WhatsApp, donde los nombres salen de config.canales.whatsapp.*_ref),
// porque esto es el sondeo previo, no la integracion terminada.
const NOMBRE_BASE_URL = 'SMARTOLT_BASE_URL';
const NOMBRE_API_KEY = 'SMARTOLT_API_KEY';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const secretos = await listarSecretos();
  return {
    baseUrl: secretos.find((s) => s.nombre === NOMBRE_BASE_URL) ?? null,
    apiKey: secretos.find((s) => s.nombre === NOMBRE_API_KEY) ?? null,
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardarCredencial({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    const nombre = form.get('nombre')?.toString().trim() ?? '';
    const valor = form.get('valor')?.toString() ?? '';
    const descripcion = form.get('descripcion')?.toString() ?? undefined;

    if (!nombre || !valor.trim()) {
      return fail(400, { error: 'Falta el nombre o el valor.', campo: nombre });
    }

    try {
      await guardarSecreto(nombre, valor.trim(), descripcion);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar la credencial.', campo: nombre });
    }
    return { guardado: nombre };
  },

  async borrarCredencial({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    const nombre = form.get('nombre')?.toString().trim() ?? '';
    if (!nombre) return fail(400, { error: 'Falta el nombre.' });

    try {
      await borrarSecreto(nombre);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo borrar.', campo: nombre });
    }
    return { borrado: nombre };
  },

  /**
   * Prueba con lo que la persona tiene escrito en pantalla en ESE momento,
   * no con lo ya guardado -- asi se puede corregir un dato mal pegado sin
   * guardar primero. Ver nucleo/canales/api.py: POST /diagnostico/smartolt.
   */
  async probarConexion({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { pruebaError: SOLO_ADMIN });

    const form = await request.formData();
    const baseUrl = form.get('base_url')?.toString().trim() ?? '';
    const apiKey = form.get('api_key')?.toString().trim() ?? '';
    if (!baseUrl || !apiKey) {
      return fail(400, { pruebaError: 'Pega el subdominio y la API key antes de probar.' });
    }

    try {
      const resultado = await probarConexionSmartolt(baseUrl, apiKey);
      return { prueba: resultado };
    } catch (/** @type {any} */ err) {
      return fail(400, { pruebaError: err?.message || 'No se pudo probar la conexion.' });
    }
  }
};
