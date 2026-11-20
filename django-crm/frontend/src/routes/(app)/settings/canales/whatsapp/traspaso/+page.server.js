import { fail } from '@sveltejs/kit';
import {
  armarCierre,
  armarTextos,
  guardarCierreInactividad,
  guardarTextosTraspaso,
  leerTraspaso
} from '$lib/server/v2/traspaso-config.js';
import { leerRotulosBandeja } from '$lib/server/v2/bandeja-config.js';

/*
 * Traspaso a una persona y cierre por inactividad (12/11/2026). Hasta este día
 * solo se cambiaban por YAML (CLAUDE.md §3.3). Cualquiera puede leerlos; solo
 * un administrador los cambia, y eso se decide ACÁ, en el servidor: ocultar el
 * botón no es un control de acceso.
 */

const SOLO_ADMIN = 'Solo un administrador puede cambiar estos textos.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  //  Los rótulos son cómo se lee cada motivo en la Bandeja: la misma palabra
  //  acá, para que nadie tenga que traducir «tres_fallos_seguidos».
  const [traspaso, rotulos] = await Promise.all([
    leerTraspaso(locals, fetch),
    leerRotulosBandeja(locals, fetch)
  ]);
  return {
    traspaso,
    rotulos: rotulos?.rotulos ?? {},
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async textos({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { textos: { error: SOLO_ADMIN } });
    const valores = armarTextos(await request.formData());
    if (!valores.mensaje) {
      return fail(400, { textos: { error: 'El mensaje general no puede quedar vacío.' } });
    }
    try {
      await guardarTextosTraspaso(locals, fetch, valores);
      return { textos: { ok: true } };
    } catch (/** @type {any} */ err) {
      return fail(400, { textos: { error: err?.message || 'No se pudo guardar.' } });
    }
  },

  async cierre({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { cierre: { error: SOLO_ADMIN } });
    const armado = armarCierre(await request.formData());
    if (armado.ok === false) return fail(400, { cierre: { error: armado.error } });
    try {
      await guardarCierreInactividad(locals, fetch, armado.cierre);
      return { cierre: { ok: true } };
    } catch (/** @type {any} */ err) {
      return fail(400, { cierre: { error: err?.message || 'No se pudo guardar.' } });
    }
  }
};
