import { json } from '@sveltejs/kit';

import { apiRequest } from '$lib/api-helpers.js';

/**
 * Ver y cambiar cuánto puede hacer solo el Supervisor.
 *
 * POR QUE EXISTE
 * --------------
 * Hasta el 08/10/2026 el nivel de autonomía solo se podía tocar desde una
 * consola del servidor: `autonomia.cambiar` no tenía ningún llamador. La
 * pantalla mostraba el estado del interruptor en solo lectura, y su propio
 * archivo declaraba que mover el interruptor "no existe en este archivo, por
 * diseño".
 *
 * Esa decisión era correcta cuando el Supervisor solo observaba. Dejó de serlo
 * el día que pudo cerrar casos solo: un freno que nadie puede tocar desde la
 * pantalla no es un freno, y el momento en que hace falta es justo cuando
 * nadie quiere estar buscando cómo abrir una terminal.
 *
 * TODO PASA POR 'apiRequest', como el resto del CRM. La primera versión de
 * esta ruta armaba su propio fetch y leía la cookie 'access_token'; la que
 * lleva el JWT se llama 'jwt_access', así que el backend recibía una petición
 * sin identidad y contestaba "Organization context is required". El contexto
 * de empresa viaja DENTRO del JWT, no como cabecera -- por eso un cliente
 * propio que "casi" arma bien los headers falla de una forma que no señala la
 * causa.
 *
 * NO ES UN PROXY ABIERTO. Sabe hacer tres cosas y ninguna más: leer el estado,
 * cambiar el nivel y mover el interruptor.
 *
 * EL GATE DE ROL SE REPITE ACA, como en el resto del CRM: dos capas. Una ruta
 * que solo dependiera de que el botón esté oculto no sería una barrera.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

const RUTA = '/operaciones/supervisor/autonomia/';

const NO_AUTORIZADO =
  'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede cambiar el alcance del Supervisor.';

/**
 * @param {any} locals
 * @returns {{ error: string, status: number } | null}
 */
function puerta(locals) {
  if (!locals.user) return { error: 'Tu sesión expiró. Volvé a iniciar sesión.', status: 401 };
  if (!ROLES_GESTION.has(locals.profile?.role)) return { error: NO_AUTORIZADO, status: 403 };
  return null;
}

/**
 * Una llamada al backend, con el error traducido a algo que se pueda leer.
 *
 * El mensaje del backend viaja TAL CUAL cuando lo trae: ya explica cuál de los
 * requisitos falta --motivo, criterios, persona-- y reescribirlo acá serían dos
 * textos que se separan el día que uno cambie.
 *
 * @param {any} cookies
 * @param {{ method?: string, body?: any }} opciones
 */
async function alBackend(cookies, opciones) {
  try {
    return { datos: await apiRequest(RUTA, opciones, { cookies }), error: null, status: 200 };
  } catch (/** @type {any} */ err) {
    const detalle = err?.data?.detail || err?.message || 'No se pudo hablar con el backend.';
    return { datos: null, error: detalle, status: err?.status ?? 502 };
  }
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, locals }) {
  const cerrada = puerta(locals);
  if (cerrada) return json({ error: cerrada.error }, { status: cerrada.status });

  const { datos, error, status } = await alBackend(cookies, {});
  if (error) return json({ error }, { status });
  return json(datos);
}

/** Cambia el NIVEL. Exige motivo y criterios; los valida el backend. */
export async function PUT({ cookies, locals, request }) {
  const cerrada = puerta(locals);
  if (cerrada) return json({ error: cerrada.error }, { status: cerrada.status });

  const cuerpo = await request.json().catch(() => ({}));
  const { datos, error, status } = await alBackend(cookies, { method: 'PUT', body: cuerpo });
  if (error) return json({ error }, { status });
  return json(datos);
}

/**
 * Mueve el INTERRUPTOR. El freno de mano.
 *
 * No exige criterios, y la asimetría es deliberada: ampliar el alcance tiene
 * que demostrar que se midió algo, parar no tiene que demostrar nada.
 */
export async function POST({ cookies, locals, request }) {
  const cerrada = puerta(locals);
  if (cerrada) return json({ error: cerrada.error }, { status: cerrada.status });

  const cuerpo = await request.json().catch(() => ({}));
  const { datos, error, status } = await alBackend(cookies, { method: 'POST', body: cuerpo });
  if (error) return json({ error }, { status });
  return json(datos);
}
