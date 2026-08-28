/**
 * La bandeja de solicitudes de instalación.
 *
 * Acá alguien decide si el servicio puede llegar a esa dirección. Aprobar
 * mueve el ticket de WispHub al equipo que instala; rechazar exige un motivo,
 * porque el cliente va a preguntar y alguien va a tener que contestarle.
 */
import { fail } from '@sveltejs/kit';
import { decidir, leerBandeja } from '$lib/server/v2/solicitudes.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, url }) {
  const estado = url.searchParams.get('estado') ?? '';
  const { solicitudes, error } = await leerBandeja(fetch, estado);
  return { solicitudes, error, estado };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async decidir({ request, fetch }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    const aprueba = form.get('aprueba')?.toString() === 'true';
    const nota = form.get('nota')?.toString()?.trim() ?? '';

    if (!id) return fail(400, { error: 'Falta la solicitud.' });
    if (!aprueba && !nota) {
      return fail(400, { error: 'Para rechazar hace falta anotar el motivo.', id });
    }
    try {
      const r = await decidir(fetch, id, aprueba, nota);
      // El fallo de la reasignación NO invalida la decisión: se muestra para
      // que alguien lo reintente, pero la solicitud ya quedó resuelta.
      return { decidido: true, id, estado: r.estado, fallo: r.fallo || '' };
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar la decisión.', id });
    }
  }
};
