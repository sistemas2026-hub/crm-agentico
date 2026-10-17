import { error, fail, redirect } from '@sveltejs/kit';
import { getGoalForEdit, updateGoal, deleteGoal, EDITABLE_FIELDS } from '$lib/server/v2/goals.js';
import { readableError } from '$lib/server/v2/form-errors.js';

/**
 * Editing a goal.
 *
 * Admin-only. `getGoalForEdit` returns `can_edit: false` for a non-admin without
 * ever fetching the goal, so a non-admin sees an "admins only" state, not the
 * form. Both writes are gated again by the backend (403 for a non-admin), and
 * the detail fetch is org-scoped, so a bad or foreign id 404s here.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load(event) {
  try {
    return await getGoalForEdit(event, event.params.id);
  } catch (/** @type {any} */ err) {
    if (err?.status === 404) {
      error(404, 'Esa meta no existe, o pertenece a otra organización.');
    }
    throw err;
  }
}

/** @type {import('./$types').Actions} */
export const actions = {
  save: async (event) => {
    const form = await event.request.formData();

    /** @type {Record<string, any>} */
    const values = {};
    for (const field of [...EDITABLE_FIELDS, 'target']) {
      if (form.has(field)) values[field] = form.get(field)?.toString().trim() ?? '';
    }
    // The one switch submits an explicit 'true'/'false', so "paused" is a real
    // value rather than the "absent → leave alone" convention above.
    if (form.has('is_active')) values.is_active = form.get('is_active') === 'true';

    try {
      await updateGoal(event, event.params.id, values);
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) {
        return fail(403, { values, error: 'Solo un administrador puede cambiar metas.' });
      }
      return fail(400, {
        values,
        error: readableError(err, 'No se pudo guardar esta meta.')
      });
    }

    redirect(303, '/goals');
  },

  delete: async (event) => {
    try {
      await deleteGoal(event, event.params.id);
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) {
        return fail(403, { error: 'Solo un administrador puede eliminar metas.' });
      }
      // Already gone is the outcome the caller wanted; treat 404 as done.
      if (err?.status === 404) redirect(303, '/goals');
      return fail(400, { error: readableError(err, 'No se pudo eliminar esta meta.') });
    }

    redirect(303, '/goals');
  }
};
