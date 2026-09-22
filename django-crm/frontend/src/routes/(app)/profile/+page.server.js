import { fail, redirect } from '@sveltejs/kit';
import { apiRequest } from '$lib/api-helpers.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { getProfile } from '$lib/server/v2/profile.js';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies }) {
  return await getProfile({ cookies });
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Edit your own name and phone. Only those two are read out of the form. The
   * page shows role, org and access, but they are never posted, and the API
   * would refuse them anyway (ProfileSelfUpdateSerializer names only name and
   * phone). A field appended to the body by hand is not forwarded.
   */
  edit: async ({ cookies, request }) => {
    const form = await request.formData();
    /** @type {Record<string, string>} */
    const body = {};
    for (const field of ['name', 'phone']) {
      if (form.has(field)) body[field] = form.get(field)?.toString().trim() ?? '';
    }

    try {
      await apiRequest('/profile/', { method: 'PATCH', body }, { cookies });
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 400 ? 400 : 500, {
        values: body,
        message: readableError(err, 'No se pudo guardar tu perfil.')
      });
    }

    return { saved: true };
  },

  /**
   * Cambiar la propia contraseña.
   *
   * Pide la actual, y no por desconfiar de quien pregunta -- el token ya dijo
   * quien es -- sino porque una sesion abierta en un equipo prestado no
   * deberia alcanzar para quedarse con la cuenta.
   *
   * El refresco de ESTA sesion viaja en el cuerpo para que el servidor la
   * conserve: cambiar la clave cierra las demas, que es el punto, pero
   * echarte del navegador donde la acabas de cambiar seria castigarte por
   * hacer lo correcto.
   */
  clave: async ({ cookies, request }) => {
    const form = await request.formData();
    const actual = form.get('actual')?.toString() ?? '';
    const nueva = form.get('nueva')?.toString() ?? '';
    const repetida = form.get('repetida')?.toString() ?? '';

    if (!actual || !nueva) {
      return fail(400, { scope: 'clave', message: 'Escribí la actual y la nueva.' });
    }
    if (nueva !== repetida) {
      // Se compara aca y no en el servidor porque es un error de tipeo, no
      // una regla: el servidor no tiene por que saber que la escribiste dos
      // veces.
      return fail(400, { scope: 'clave', message: 'Las dos contraseñas nuevas no coinciden.' });
    }

    /** @type {any} */
    let resultado;
    try {
      resultado = await apiRequest(
        '/auth/password/',
        { method: 'POST', body: { actual, nueva, refresh: cookies.get('jwt_refresh') ?? '' } },
        { cookies }
      );
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 400 ? 400 : 500, {
        scope: 'clave',
        message: readableError(err, 'No se pudo cambiar tu contraseña.')
      });
    }

    return { claveCambiada: true, sesionesCerradas: resultado?.sesiones_cerradas ?? 0 };
  },

  /**
   * Switch to another organisation you belong to. This is not a field edit: the
   * backend re-issues the JWT with the new org claim (and only if you have an
   * active profile there, else 403), and we swap the httpOnly cookies the shell
   * reads so every later request is scoped to the new org. Mirrors the v1 /org
   * picker so the two behave the same.
   */
  switchOrg: async ({ cookies, request }) => {
    const form = await request.formData();
    const orgId = form.get('org_id')?.toString() ?? '';

    if (!UUID_RE.test(orgId)) {
      return fail(400, { scope: 'switch', message: 'Organización inválida.' });
    }

    // Sent so the backend retires the token we are replacing; it belongs to the
    // caller (the API checks) or is ignored.
    const outgoingRefresh = cookies.get('jwt_refresh');
    const payload = outgoingRefresh
      ? { org_id: orgId, refresh: outgoingRefresh }
      : { org_id: orgId };

    /** @type {any} */
    let result;
    try {
      result = await apiRequest(
        '/auth/switch-org/',
        { method: 'POST', body: payload },
        { cookies }
      );
    } catch (/** @type {any} */ err) {
      // 403 is the honest one: you asked for an org you are not a member of.
      const message =
        err?.status === 403
          ? 'No sos miembro de esa organización.'
          : readableError(err, 'No se pudo cambiar de organización.');
      return fail(err?.status === 403 ? 403 : 500, { scope: 'switch', message });
    }

    const secure = process.env.NODE_ENV === 'production';
    cookies.set('jwt_access', result.access_token, {
      path: '/',
      httpOnly: true,
      sameSite: 'lax',
      secure,
      maxAge: 60 * 60 * 24
    });
    cookies.set('jwt_refresh', result.refresh_token, {
      path: '/',
      httpOnly: true,
      sameSite: 'lax',
      secure,
      maxAge: 60 * 60 * 24 * 365
    });
    cookies.set('org', orgId, {
      path: '/',
      sameSite: 'strict',
      maxAge: 60 * 60 * 24 * 365
    });

    throw redirect(303, '/profile');
  }
};
