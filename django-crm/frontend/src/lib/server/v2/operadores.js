/**
 * Las personas a las que un ADMIN puede reasignar una conversacion (B3.4, T4).
 *
 * Server-only. El relevo identifica a una persona por su User.id -- el mismo
 * 'user_id' del JWT que usa autorDeSesion() --, NO por el Profile.id que usan
 * los pickers de tickets. Son tablas distintas y mezclarlas ya rompio cosas en
 * este codigo (ver org-people.js, resolveMe).
 *
 * `GET /users/get-teams-and-users/` devuelve solo perfiles activos de la
 * organizacion de quien pregunta. Por eso sirve dos veces: para armar el
 * selector, y para VALIDAR el destino en el proxy antes de ir al motor -- un
 * id que no esta en esta lista (de otra organizacion, inactivo, inventado) no
 * se reasigna. El nombre tambien sale de aca, nunca del navegador.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * @param {import('@sveltejs/kit').Cookies} cookies
 * @returns {Promise<{ usuario_id: string, nombre: string }[]>}
 */
export async function operadoresDeLaOrg(cookies) {
  const resp = await apiRequest('/users/get-teams-and-users/', {}, { cookies });
  return (resp?.profiles ?? [])
    .filter((/** @type {any} */ p) => p?.is_active !== false && p?.user_details?.id
      && p.user_details.is_active !== false)
    .map((/** @type {any} */ p) => ({
      usuario_id: String(p.user_details.id),
      nombre: (p.user_details.name || p.user_details.email || '').trim()
    }))
    .filter((o) => o.nombre)
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
}

/** El rol de quien pregunta, del JWT verificado en hooks.server.js. */
export function rolDeSesion(/** @type {any} */ locals) {
  return String(locals?.profile?.role ?? 'USER').toUpperCase();
}

/**
 * Lo que decide el proxy de reasignar ANTES de ir al motor. Pura, para poder
 * probarla sin SvelteKit.
 *
 * El rol viene de la sesion; el destino tiene que estar entre las personas
 * activas de la organizacion, y su nombre sale de esa lista, no del navegador.
 *
 * @param {{ rol: string, motivo: unknown, destinoId: unknown, operadores: { usuario_id: string, nombre: string }[] }} p
 * @returns {{ ok: true, motivo: string, destino: { usuario_id: string, nombre: string } }
 *   | { ok: false, status: number, codigo: string, error: string }}
 */
export function validarReasignacion({ rol, motivo, destinoId, operadores }) {
  if (String(rol ?? '').toUpperCase() !== 'ADMIN') {
    return { ok: false, status: 403, codigo: 'no_es_admin',
      error: 'Solo un administrador puede reasignar una conversación.' };
  }
  const texto = typeof motivo === 'string' ? motivo.trim() : '';
  if (!texto) {
    return { ok: false, status: 400, codigo: 'sin_motivo', error: 'Escribí el motivo de la reasignación.' };
  }
  const destino = (operadores ?? []).find((o) => o.usuario_id === String(destinoId ?? ''));
  if (!destino) {
    return { ok: false, status: 400, codigo: 'destino_invalido',
      error: 'Esa persona no es un operador activo de la organización.' };
  }
  return { ok: true, motivo: texto, destino };
}
