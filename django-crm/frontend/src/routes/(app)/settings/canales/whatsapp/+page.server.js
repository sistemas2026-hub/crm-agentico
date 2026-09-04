import { fail } from '@sveltejs/kit';
import {
  borrarSecreto,
  guardarCanalWhatsapp,
  guardarSecreto,
  leerCanalWhatsapp,
  listarSecretos
} from '$lib/server/v2/canal-whatsapp.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const [canal, secretos] = await Promise.all([leerCanalWhatsapp(), listarSecretos()]);
  return {
    canal,
    secretos,
    // Mismo criterio que /settings/asistente: esto decide la afordancia
    // (esconder los botones), no el permiso -- cada action lo vuelve a
    // comprobar, porque ocultar un boton no es control de acceso.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Guarda (o actualiza) una credencial. 'nombre' es el NOMBRE del secreto
   * (ej. 'WHATSAPP_TOKEN'), no la clave interna -- viaja en un input hidden
   * que arma la pantalla a partir de canal.refs, para que este archivo no
   * tenga que conocer los cinco nombres de memoria.
   */
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
      return fail(400, {
        error: err?.message || 'No se pudo guardar la credencial.',
        campo: nombre
      });
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
   * El verify_token no lo pide Meta: lo INVENTA la empresa y Meta lo devuelve
   * una sola vez, en el handshake de alta. Generarlo con una cadena al azar
   * en vez de pedir que alguien tipee algo es mas seguro (nadie elige
   * "1234") y mas rapido. Se guarda igual que cualquier otro secreto -- lo
   * unico especial es que ESTA respuesta trae el valor en claro, porque es
   * el unico momento en que hace falta mostrarlo: para copiarlo en Meta.
   */
  async generarVerifyToken({ locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const token = crypto.randomUUID().replaceAll('-', '');
    try {
      await guardarSecreto('WHATSAPP_VERIFY_TOKEN', token, 'Generado desde ajustes');
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo generar el token.' });
    }
    return { generado: { nombre: 'WHATSAPP_VERIFY_TOKEN', valor: token } };
  },

  async guardarCanal({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { canalError: SOLO_ADMIN });

    const form = await request.formData();
    const activo = form.get('activo') === 'true';
    const numeroVisible = form.get('numero_visible')?.toString().trim() || null;

    try {
      await guardarCanalWhatsapp({ activo, numero_visible: numeroVisible });
    } catch (/** @type {any} */ err) {
      return fail(400, { canalError: err?.message || 'No se pudo guardar.' });
    }
    return { canalGuardado: true };
  }
};
