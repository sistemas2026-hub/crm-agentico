import { fail } from '@sveltejs/kit';
import { borrarSecreto, guardarSecreto, listarSecretos } from '$lib/server/v2/canal-whatsapp.js';
import {
  guardarVariable,
  leerSmartOlt,
  probarConexion as probarConexionSmartolt,
  REF_API_KEY
} from '$lib/server/v2/smartolt.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const [smartolt, secretos] = await Promise.all([leerSmartOlt(), listarSecretos()]);
  return {
    smartolt,
    secretoApiKey: secretos.find((s) => s.nombre === REF_API_KEY),
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    const valor = form.get('valor')?.toString() ?? '';
    if (!valor.trim()) return fail(400, { error: 'Falta la clave.' });

    try {
      await guardarSecreto(REF_API_KEY, valor.trim(), 'SmartOLT — control de ONUs');
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar la clave.' });
    }
    return { guardado: true };
  },

  async borrar({ locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    try {
      await borrarSecreto(REF_API_KEY);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo borrar la clave.' });
    }
    return { borrado: true };
  },

  /**
   * El subdominio SI se persiste (a diferencia de la clave, no es secreto):
   * PUT /configuracion/variables/<nombre>, con 'nombre' viajando en un input
   * hidden que arma la pantalla a partir de smartolt.subdominio_ref -- este
   * archivo no lo hardcodea, lo lee de lo que declaro la herramienta.
   */
  async guardarSubdominio({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { subdominioError: SOLO_ADMIN });

    const form = await request.formData();
    const nombre = form.get('nombre')?.toString().trim() ?? '';
    const valor = form.get('valor')?.toString().trim() ?? '';
    if (!nombre) return fail(400, { subdominioError: 'Esta herramienta no declara base_url_ref.' });
    if (!valor) return fail(400, { subdominioError: 'Falta el subdominio.' });

    try {
      await guardarVariable(nombre, valor);
    } catch (/** @type {any} */ err) {
      return fail(400, { subdominioError: err?.message || 'No se pudo guardar el subdominio.' });
    }
    return { subdominioGuardado: true };
  },

  /**
   * Prueba con lo que la persona tiene escrito en ESE momento (subdominio +
   * clave), no con lo ya guardado -- asi se corrige un dato mal pegado sin
   * guardar primero. Ver smartolt.js::probarConexion().
   */
  async probarConexion({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { pruebaError: SOLO_ADMIN });

    const form = await request.formData();
    const subdominio = form.get('subdominio')?.toString().trim() ?? '';
    const apiKey = form.get('api_key')?.toString().trim() ?? '';
    if (!subdominio || !apiKey) {
      return fail(400, { pruebaError: 'Pegá el subdominio y la clave antes de probar.' });
    }

    try {
      const resultado = await probarConexionSmartolt(subdominio, apiKey);
      return { prueba: resultado };
    } catch (/** @type {any} */ err) {
      return fail(400, { pruebaError: err?.message || 'No se pudo probar la conexión.' });
    }
  }
};
