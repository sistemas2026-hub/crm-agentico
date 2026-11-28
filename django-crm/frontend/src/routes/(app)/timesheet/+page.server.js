import { fail } from '@sveltejs/kit';
import { getTimesheet, stopTimer } from '$lib/server/v2/timesheet.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { hoyDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';

/**
 * `?start=&end=` (YYYY-MM-DD) pick the week; absent, it defaults to this ISO
 * week. The week-nav buttons drive those params.
 *
 * «Hoy» is the company's day, not the server's (UTC): it picks the default
 * week and marks today's column (27/10/2026).
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ cookies, url, locals }) {
  const start = url.searchParams.get('start') || undefined;
  const end = url.searchParams.get('end') || undefined;
  const hoy = await hoyDeLaEmpresa(locals, cookies);
  return { ...(await getTimesheet({ cookies }, { start, end, hoy })), hoy };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async stop(event) {
    const form = await event.request.formData();
    const entryId = form.get('entry_id')?.toString() ?? '';

    try {
      await stopTimer(event, entryId);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo detener el cronómetro.') });
    }

    return { stopped: true };
  }
};
