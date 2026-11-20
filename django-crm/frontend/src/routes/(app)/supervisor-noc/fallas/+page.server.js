import { fail } from '@sveltejs/kit';
import { aprobarAviso, leerFallas, prepararAviso } from '$lib/server/v2/fallas-de-red.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';
import { zonaDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';
import { textoDelError } from '$lib/supervisor/fallas.js';

/**
 * Fallas de red — Supervisor NOC (30/10/2026, PRD §8.17, Ola 2).
 *
 * Las caídas de PON vivas y, para cada una, avisarle a sus clientes. Hasta hoy
 * ninguna pantalla mostraba las situaciones de red, y el aviso de una caída
 * estaba decidido que lo APRUEBE UNA PERSONA: tiene que poder verla.
 *
 * DOS PASOS, A PROPÓSITO: «preparar» muestra a cuántos clientes y quiénes
 * quedan afuera; «aprobar» manda. El backend vuelve a armar la lista al
 * aprobar (entre mirar y aprobar pudo volver gente), y no deja aprobar dos
 * veces.
 *
 * QUIÉN PUEDE: la gestión, como el resto del Supervisor. El backend lo exige
 * con un 403; acá se repite para no pedir lo que va a fallar.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @param {any} locals */
const gestiona = (locals) => ROLES_GESTION.has(locals?.profile?.role);

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** El código del backend, venga en el error o en un 2xx con 'error' (202). @param {any} e */
const codigoDe = (e) => e?.body?.error ?? e?.error ?? null;

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals }) {
  if (!gestiona(locals)) return { puedeVer: false, fallas: [], error: null, zona: 'UTC' };
  const zona = await zonaDeLaEmpresa(locals, cookies);
  try {
    const r = await leerFallas({ cookies });
    return { puedeVer: true, fallas: Array.isArray(r?.fallas) ? r.fallas : [], error: null, zona };
  } catch (e) {
    return {
      puedeVer: true,
      fallas: [],
      error: mensajeDeError(e, 'No se pudieron leer las fallas de red.'),
      zona
    };
  }
}

/**
 * @param {Request} request
 * @param {any} locals
 */
async function situacionDe(request, locals) {
  if (!gestiona(locals)) {
    return { error: fail(403, { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede avisar una caída.' }) };
  }
  const id = String((await request.formData()).get('situacion') ?? '');
  if (!UUID.test(id)) return { error: fail(400, { error: 'Esa caída no se reconoce.' }) };
  return { id };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /** A cuántos clientes se les avisaría, y quiénes quedan afuera. No manda nada. */
  preparar: async ({ request, cookies, locals }) => {
    const { id, error } = await situacionDe(request, locals);
    if (error) return error;
    try {
      const r = await prepararAviso({ cookies }, id);
      if (codigoDe(r)) return fail(400, { situacion: id, error: textoDelError(codigoDe(r)) });
      return { situacion: id, preparada: r };
    } catch (e) {
      return fail(400, { situacion: id, error: textoDelError(codigoDe(e)) });
    }
  },

  /** Una persona aprueba: el backend arma la lista de nuevo y arranca el envío. */
  aprobar: async ({ request, cookies, locals }) => {
    const { id, error } = await situacionDe(request, locals);
    if (error) return error;
    try {
      const r = await aprobarAviso({ cookies }, id);
      if (codigoDe(r)) return fail(400, { situacion: id, error: textoDelError(codigoDe(r)) });
      return { situacion: id, aprobada: r?.aviso ?? null };
    } catch (e) {
      return fail(400, { situacion: id, error: textoDelError(codigoDe(e)) });
    }
  }
};
