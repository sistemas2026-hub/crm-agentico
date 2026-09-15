import { fail } from '@sveltejs/kit';
import {
  guardarFlujoDerivacion,
  leerFlujoDerivacion
} from '$lib/server/v2/asistente-config.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar el flujo.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  return {
    flujo: await leerFlujoDerivacion(),
    // Mismo criterio que el resto de /settings: esto esconde los controles,
    // no es el permiso -- la action lo vuelve a comprobar.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Guarda a que agentes puede derivar el router y que atiende cada uno.
   * Van juntos a proposito: conectar un agente sin decir que atiende lo
   * deja enganchado pero invisible para el router (nunca le llegaria una
   * conversacion), y ese estado a medias es dificil de diagnosticar despues.
   */
  async guardar({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    const destinos = form.getAll('destinos').map((d) => d.toString());

    /** @type {Record<string, string>} */
    const atiende = {};
    for (const [clave, valor] of form.entries()) {
      if (clave.startsWith('atiende:')) {
        atiende[clave.slice('atiende:'.length)] = valor.toString();
      }
    }

    try {
      await guardarFlujoDerivacion(destinos, atiende);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar el flujo.' });
    }
    return { guardado: true };
  }
};
