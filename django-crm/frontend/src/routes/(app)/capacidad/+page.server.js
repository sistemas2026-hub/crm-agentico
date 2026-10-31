import { fail, redirect } from '@sveltejs/kit';
import {
  guardarDeclaracionCapacidad,
  leerAutonomiaGanada,
  leerTableroCapacidad,
  PERIODOS
} from '$lib/server/v2/capacidad.js';

/**
 * Capacidad: cuánto trabajo le resolvió Dexter a la empresa (PRD §2).
 *
 * Solo ADMIN, como Consumo: son cifras de negocio de la empresa, no de la
 * operación de un colaborador.
 *
 * Se pasa la respuesta del motor ENTERA y sin renombrar: la pantalla lee las
 * mismas claves que escribe nucleo/observabilidad/capacidad.py. Una capa que
 * traduce nombres es donde se pierde un dato con el backend en verde
 * (CLAUDE.md §6, `requiere_noc`).
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch, url }) {
  if (locals.profile?.role !== 'ADMIN') {
    redirect(303, '/');
  }
  const pedido = Number(url.searchParams.get('dias'));
  const dias = PERIODOS.includes(pedido) ? pedido : 30;
  //  Las dos en paralelo: una no espera a la otra, y si una falla la otra se
  //  muestra igual (31/10/2026: la autonomía ganada, PRD §2).
  const [{ tablero, error }, ganada] = await Promise.all([
    leerTableroCapacidad(locals, fetch, dias),
    leerAutonomiaGanada(locals, fetch)
  ]);
  return {
    tablero, dias, periodos: PERIODOS, error,
    autonomia: ganada.autonomia, errorAutonomia: ganada.error ?? null
  };
}

/** Los tres números que declara la empresa. Vacío = null = sin declarar. */
const DECLARABLES = ['minutos_por_conversacion', 'minutos_por_visita', 'personas_del_equipo'];

/** @type {import('./$types').Actions} */
export const actions = {
  async declarar({ locals, fetch, request }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { declarar: { error: 'Solo un administrador puede cambiar esto.' } });
    }
    const form = await request.formData();
    /** @type {Record<string, number|null>} */
    const valores = {};
    for (const campo of DECLARABLES) {
      const crudo = form.get(campo)?.toString().trim() ?? '';
      if (crudo === '') {
        valores[campo] = null;
        continue;
      }
      const n = Number(crudo);
      if (!Number.isInteger(n) || n < 1) {
        return fail(400, { declarar: { error: 'Cada valor tiene que ser un número entero mayor que cero, o quedar vacío.' } });
      }
      valores[campo] = n;
    }
    try {
      await guardarDeclaracionCapacidad(locals, fetch, /** @type {any} */ (valores));
    } catch (/** @type {any} */ e) {
      return fail(502, { declarar: { error: e?.message || 'No se pudo guardar.' } });
    }
    return { declarar: { ok: true } };
  }
};
