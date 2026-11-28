/**
 * EL DINERO DE LOS TÉCNICOS (26/11/2026). Ver campo/dinero.py.
 *
 * Cuánto tiene cada técnico por entregar, de qué órdenes, y «Recibí». Recibir
 * manda la cifra de cada orden tal como se vio: si el técnico la corrigió en el
 * medio, el servidor no recibe nada y la pantalla lo dice.
 */
import { fail } from '@sveltejs/kit';
import { leerDinero, recibirDinero } from '$lib/server/v2/dinero.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies }) {
  return leerDinero(cookies);
}

/** @type {import('./$types').Actions} */
export const actions = {
  async recibir({ request, cookies }) {
    const form = await request.formData();
    const tecnico = form.get('tecnico_id')?.toString() ?? '';
    /** @type {any} */
    let ordenes;
    try {
      ordenes = JSON.parse(form.get('ordenes')?.toString() ?? '[]');
    } catch {
      return fail(400, { error: 'No se entendió qué órdenes recibes.', tecnico });
    }
    if (!tecnico || !Array.isArray(ordenes) || !ordenes.length) {
      return fail(400, { error: 'Falta qué recibir.', tecnico });
    }
    const limpias = ordenes.map((/** @type {any} */ o) => ({
      orden_id: String(o?.orden_id ?? ''),
      monto: Number(o?.monto)
    }));
    if (limpias.some((o) => !o.orden_id || !Number.isFinite(o.monto))) {
      return fail(400, { error: 'Cada orden va con su monto.', tecnico });
    }
    const total = limpias.reduce((s, o) => s + o.monto, 0);
    try {
      const r = await recibirDinero(cookies, tecnico, limpias);
      return { recibido: true, tecnico, total, recibidas: r?.recibidas ?? limpias.length };
    } catch (err) {
      const e = /** @type {any} */ (err);
      return fail(e?.status === 409 ? 409 : 400, {
        error: mensajeDeError(e, 'No se pudo recibir.'),
        tecnico
      });
    }
  }
};
