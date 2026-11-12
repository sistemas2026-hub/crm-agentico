/**
 * La bandeja de solicitudes de instalación.
 *
 * Acá alguien decide si el servicio puede llegar a esa dirección. Aprobar
 * mueve el ticket de WispHub al equipo que instala; rechazar exige un motivo,
 * porque el cliente va a preguntar y alguien va a tener que contestarle.
 */
import { fail } from '@sveltejs/kit';
import { decidir, leerBandeja, reintentar } from '$lib/server/v2/solicitudes.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, url }) {
  const estado = url.searchParams.get('estado') ?? '';
  const { solicitudes, error, sinPermiso } = await leerBandeja(cookies, estado);
  // 'sinPermiso' VIAJA HASTA LA PÁGINA (12/11/2026): sin él, un 403 se veía
  // como "No hay solicitudes esperando" y nadie sabía por qué.
  return { solicitudes, error, estado, sinPermiso: Boolean(sinPermiso) };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async decidir({ request, cookies }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    const aprueba = form.get('aprueba')?.toString() === 'true';
    const nota = form.get('nota')?.toString()?.trim() ?? '';

    if (!id) return fail(400, { error: 'Falta la solicitud.' });
    if (!aprueba && !nota) {
      return fail(400, { error: 'Para rechazar hace falta anotar el motivo.', id });
    }
    try {
      const r = await decidir(cookies, id, aprueba, nota);
      // El fallo de la reasignación NO invalida la decisión: se muestra para
      // que alguien lo reintente, pero la solicitud ya quedó resuelta.
      // 'aviso' y 'pendientes' (12/11/2026): al rechazar, si el WhatsApp al
      // cliente no salió la pantalla tiene que decir por qué.
      return {
        decidido: true,
        id,
        estado: r.estado,
        fallo: r.fallo || '',
        aviso: r.aviso_cliente ?? null,
        pendientes: r.pendientes ?? []
      };
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: err?.message || 'No se pudo guardar la decisión.',
        id
      });
    }
  },

  async reintentar({ request, cookies }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    if (!id) return fail(400, { error: 'Falta la solicitud.' });
    try {
      const r = await reintentar(cookies, id);
      return {
        reintentado: true,
        id,
        pendientes: r.pendientes ?? [],
        aviso: r.aviso_cliente ?? null,
        fallo: r.fallo || ''
      };
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: err?.message || 'No se pudo reintentar.',
        id
      });
    }
  }
};
