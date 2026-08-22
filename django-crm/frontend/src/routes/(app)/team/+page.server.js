import { fail } from '@sveltejs/kit';
import { listTeam, inviteUser, setRole, setStatus, ROLES, perfilPorCorreo }
  from '$lib/server/v2/team.js';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { readableError } from '$lib/server/v2/form-errors.js';

/**
 * Team and access.
 *
 * Server load, so the JWT cookie stays server-side. The list, the totals and
 * the per-person token counts all arrive from the real org; a non-admin gets
 * `forbidden` back rather than a broken page, because the underlying endpoints
 * are admin-only.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ cookies, fetch }) {
  const equipo = await listTeam({ cookies });

  // Las areas de trabajo salen del asistente, no de una lista fija aca: son
  // sus agentes internos, y cambian cuando alguien crea uno nuevo desde
  // /agentes. Si el asistente no esta configurado o no responde, la pantalla
  // sigue sirviendo para agregar gente -- solo se queda sin el selector de area.
  let areas = [];
  /** La gente del sistema operativo a la que se le puede asignar trabajo. */
  let externos = [];
  let etiquetaExterna = '';
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (baseUrl && tenant) {
    try {
      const resp = await fetch(
        `${baseUrl}/agentes/asignaciones?tenant=${encodeURIComponent(tenant)}`,
        { headers: headersMotor() }
      );
      const datos = await resp.json();
      if (resp.ok) {
        areas = datos.agentes ?? [];
        externos = datos.candidatos_externos ?? [];
        etiquetaExterna = datos.sistema_externo ?? '';
      }
      else console.warn('[equipo] el asistente respondio', resp.status, datos?.error ?? '');
    } catch (/** @type {any} */ err) {
      // Visible a proposito: un catch mudo aca deja la pantalla sin selector
      // de area y sin ninguna pista de por que. Ya paso una vez.
      console.warn('[equipo] no se pudo leer las areas del asistente:', err?.message ?? err);
      areas = [];
    }
  } else {
    console.warn('[equipo] falta PRIVATE_ASISTENTE_URL o PRIVATE_ASISTENTE_TENANT');
  }
  return { ...equipo, areas, externos, etiquetaExterna };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Invite a new member: email + role. The server is the boundary. It gates
   * this to admins, rejects a duplicate within the org with a 400, and reuses
   * an account that already exists elsewhere instead of erroring.
   */
  invite: async ({ cookies, request, fetch }) => {
    const form = await request.formData();
    const email = form.get('email')?.toString().trim();
    const role = form.get('role')?.toString() || 'USER';
    const area = form.get('area')?.toString().trim() || '';
    const externo = form.get('externo')?.toString().trim() || '';
    const externoNombre = form.get('externo_nombre')?.toString().trim() || '';
    if (!email) return fail(400, { invite: { error: 'Ingresá un correo electrónico.' } });
    if (!ROLES.includes(role)) return fail(400, { invite: { error: 'Elegí un rol válido.' } });

    try {
      await inviteUser({ cookies }, { email, role });
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        invite: {
          error:
            err?.status === 403
              ? 'Solo un administrador puede agregar personas.'
              : readableError(err, 'No se pudo agregar a esa persona.')
        }
      });
    }
    // El area es opcional, y su fallo NO invalida el alta: la persona ya
    // quedo creada en el CRM. Devolver un error aca la dejaria pensando que
    // no se creo nadie, y al reintentar se choca con "ya existe". Se avisa
    // aparte para que pueda asignarla desde /agentes/asignaciones.
    let avisoArea = null;
    if (area || externo) {
      try {
        // 'POST /users/' no devuelve el perfil que creo -- hay que buscarlo.
        const profileId = await perfilPorCorreo({ cookies }, email);
        if (!profileId) {
          avisoArea = 'Se creó la persona, pero no se pudo ubicar su perfil para asignarle el área.';
        } else {
          const resp = await fetch(`/api/agentes/asignaciones/${encodeURIComponent(profileId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              roles: area ? [area] : [],
              identidad_externa: { identificador: externo, nombre_visible: externoNombre }
            })
          });
          if (!resp.ok) {
            const datos = await resp.json().catch(() => ({}));
            avisoArea = datos.error || 'Se creó la persona, pero no se pudo asignarle el área.';
          }
        }
      } catch (/** @type {any} */ err) {
        avisoArea = err?.message || 'Se creó la persona, pero no se pudo asignarle el área.';
      }
    }

    return { invited: email, area: area || null, avisoArea };
  },

  /**
   * Change someone's role. The page only shows this control for another
   * person's row and never for the last admin, mirroring the server's rules,
   * but the server is what enforces them: a member cannot promote themselves
   * and nobody can change their own role here.
   */
  setRole: async ({ cookies, request }) => {
    const form = await request.formData();
    const userId = form.get('userId')?.toString();
    const role = form.get('role')?.toString();
    if (!userId || !role || !ROLES.includes(role)) {
      return fail(400, { error: '¿Qué persona, y a qué rol?' });
    }
    try {
      await setRole({ cookies }, userId, role);
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error:
          err?.status === 403
            ? 'Eso no es tuyo para cambiarlo.'
            : readableError(err, 'No se pudo cambiar ese rol.')
      });
    }
    return { roleChanged: userId };
  },

  /**
   * Activate or deactivate a member. The server refuses to deactivate the last
   * active admin (a 400), so the org can never be stranded without one.
   */
  setStatus: async ({ cookies, request }) => {
    const form = await request.formData();
    const userId = form.get('userId')?.toString();
    const status = form.get('status')?.toString();
    if (!userId || (status !== 'Active' && status !== 'Inactive')) {
      return fail(400, { error: '¿Qué persona, y activa o no?' });
    }
    try {
      await setStatus({ cookies }, userId, status);
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error:
          err?.status === 403
            ? 'Solo un administrador puede cambiar quién está activo.'
            : readableError(err, 'No se pudo cambiar ese estado.')
      });
    }
    return { statusChanged: userId };
  }
};
