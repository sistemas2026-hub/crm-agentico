import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Ver y cambiar cuánto puede hacer solo el Supervisor.
 *
 * POR QUE EXISTE
 * --------------
 * Hasta el 08/10/2026 el nivel de autonomía solo se podía tocar desde una
 * consola del servidor: `autonomia.cambiar` no tenía ningún llamador. La
 * pantalla mostraba el estado del interruptor en solo lectura, y su propio
 * archivo declaraba que mover el interruptor "no existe en este archivo", por
 * diseño.
 *
 * Esa decisión era correcta cuando el Supervisor solo observaba. Dejó de serlo
 * el día que pudo cerrar casos solo: un freno que nadie puede tocar desde la
 * pantalla no es un freno, y el momento en que hace falta es justo cuando
 * nadie quiere estar buscando cómo abrir una terminal.
 *
 * NO ES UN PROXY ABIERTO. Sabe hacer tres cosas y ninguna más: leer el estado,
 * cambiar el nivel y mover el interruptor. El JWT del colaborador viaja en la
 * cookie, así que el 403 de 'EsJefeDeOperaciones' lo sigue decidiendo el
 * backend.
 *
 * EL GATE DE ROL SE REPITE ACA, como en el resto del CRM: dos capas. Una ruta
 * que solo dependiera de que el botón esté oculto no sería una barrera.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

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
 * @param {{ cookies: any, metodo: string, cuerpo?: any }} opciones
 */
async function alBackend({ cookies, metodo, cuerpo }) {
  const base = env.PRIVATE_DJANGO_API_URL;
  if (!base) {
    return { datos: null, error: 'El backend no está configurado en este entorno.', status: 500 };
  }
  const token = cookies.get('access_token');
  /** @type {Record<string, string>} */
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const r = await fetch(`${base}/api/operaciones/supervisor/autonomia/`, {
      method: metodo,
      headers,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo)
    });
    const datos = await r.json().catch(() => ({}));
    if (!r.ok) {
      //  El 'detail' del backend viaja TAL CUAL: ya explica cuál de los
      //  requisitos falta --motivo, criterios, persona-- y reescribirlo acá
      //  sería mantener dos textos que se desincronizan.
      return {
        datos: null,
        error: datos?.detail || `El backend respondió ${r.status}.`,
        status: r.status
      };
    }
    return { datos, error: null, status: 200 };
  } catch (/** @type {any} */ err) {
    return {
      datos: null,
      error: `No se pudo hablar con el backend: ${err?.message ?? err}`,
      status: 502
    };
  }
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, locals }) {
  const cerrada = puerta(locals);
  if (cerrada) return json({ error: cerrada.error }, { status: cerrada.status });

  const { datos, error, status } = await alBackend({ cookies, metodo: 'GET' });
  if (error) return json({ error }, { status });
  return json(datos);
}

/** Cambia el NIVEL. Exige motivo y criterios; los valida el backend. */
export async function PUT({ cookies, locals, request }) {
  const cerrada = puerta(locals);
  if (cerrada) return json({ error: cerrada.error }, { status: cerrada.status });

  const cuerpo = await request.json().catch(() => ({}));
  const { datos, error, status } = await alBackend({ cookies, metodo: 'PUT', cuerpo });
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
  const { datos, error, status } = await alBackend({ cookies, metodo: 'POST', cuerpo });
  if (error) return json({ error }, { status });
  return json(datos);
}
