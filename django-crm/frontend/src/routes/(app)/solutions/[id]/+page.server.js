import { fail } from '@sveltejs/kit';
import { getArticle, setPublished, updateArticle, agentesDelAsistente } from '$lib/server/v2/solutions.js';
import { readableError } from '$lib/server/v2/form-errors.js';

/** @type {import('./$types').PageServerLoad} */
export async function load(event) {
  const { cookies, locals, params } = event;
  const canRelease = /** @type {any} */ (locals).profile?.role === 'ADMIN';
  const [article, agentes] = await Promise.all([
    getArticle({ cookies }, params.id),
    // Solo quien puede elegirlos los necesita; a los demás no se les pregunta.
    canRelease ? agentesDelAsistente(event) : Promise.resolve([])
  ]);
  return {
    ...article,
    agentes,
    // See the list loader: this decides what renders, never what is allowed.
    canRelease
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Move the article along the review workflow.
   *
   * Only the status: the body is not in this form, so a PATCH carrying one
   * field is exactly what should go. `draft → reviewed` is anyone's to press;
   * anything → `approved` is an admin's, and the API is what says so.
   */
  setStatus: async ({ cookies, params, request }) => {
    const form = await request.formData();
    const status = form.get('status')?.toString() ?? '';
    if (!status) return fail(400, { error: 'No hay estado para asignar.' });

    try {
      await updateArticle({ cookies }, params.id, { status });
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo cambiar el estado.') });
    }
    return { status };
  },

  /**
   * Publish the article (which loads it into Dexter's corpus), or take it back.
   *
   * The two verbs are one action with a flag rather than two nearly identical
   * ones, because the thing they have in common. Both are admin-only, both
   * are the same switch, is the part worth keeping in one place.
   */
  /**
   * Qué agentes de Dexter pueden citar el artículo (12/11/2026). El servidor
   * lo trata como publicar: solo un administrador.
   */
  setRoles: async ({ cookies, params, request }) => {
    const form = await request.formData();
    const roles = form
      .getAll('roles_asistente')
      .map((v) => v.toString().trim())
      .filter(Boolean)
      .join(', ');
    try {
      await updateArticle({ cookies }, params.id, { roles_asistente: roles });
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: readableError(err, 'No se pudieron guardar los agentes.')
      });
    }
    return { roles };
  },

  setPublished: async ({ cookies, params, request }) => {
    const form = await request.formData();
    const published = form.get('published') === 'true';

    try {
      await setPublished({ cookies }, params.id, published);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: readableError(
          err,
          published ? 'No se pudo publicar este artículo.' : 'No se pudo despublicar este artículo.'
        )
      });
    }
    return { published };
  }
};
