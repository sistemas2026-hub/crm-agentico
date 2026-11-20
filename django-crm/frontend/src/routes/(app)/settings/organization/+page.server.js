import { fail } from '@sveltejs/kit';
import { getOrgSettings, updateOrgSettings } from '$lib/server/v2/organization.js';
import { listPacks, applyPack, clearSampleData } from '$lib/server/packs.js';
import { readableError } from '$lib/server/v2/form-errors.js';

/**
 * Organization settings (read) + the "Vertical pack" section.
 *
 * Server load, so the JWT cookie stays server-side. GET is open to any member;
 * `can_edit` (from the JWT role claim) decides whether the page shows the edit
 * affordance, and the edit route + the backend PATCH are what actually enforce
 * admin-only. The same `can_edit` flag is reused below to decide whether the
 * pack list and its actions render at all. Vertical packs are admin-only for
 * the identical reason (`PackApplyView`/`PackSampleDataView` both 403 a
 * non-admin server-side), so there is no second admin check to invent.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ cookies }) {
  const settings = await getOrgSettings({ cookies });

  // GET /api/packs/ needs IsAuthenticated only, no org context, but a
  // reload of this page must never break over a transient failure here, so
  // this follows the same "empty list on error" fallback the org-creation
  // page already established for the identical call.
  let packs = [];
  try {
    packs = await listPacks(cookies);
  } catch (/** @type {any} */ err) {
    console.error('Could not load vertical packs:', err?.message, err?.status);
  }

  return { ...settings, packs };
}

/** @type {import('./$types').Actions} */
export const actions = {
  // Applying is additive-only and safe to repeat, a pack already applied
  // just reports everything as skipped. There is deliberately no guard here
  // against re-submitting the currently-applied pack.
  apply: async ({ cookies, request }) => {
    const packId = (await request.formData()).get('pack_id')?.toString();
    if (!packId) return fail(400, { error: 'Elegí un paquete para aplicar.' });

    try {
      const { report } = await applyPack(cookies, packId);
      return { appliedPackId: packId, report };
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) {
        return fail(403, { error: 'Solo un administrador puede aplicar un paquete de rubro.' });
      }
      return fail(400, { error: readableError(err, 'No se pudo aplicar este paquete.') });
    }
  },

  /**
   * Subir el logo de la empresa.
   *
   * Va acá y no en un archivo del repo a propósito: el logo es un dato que
   * cambia con cada empresa que se conecta, así que se sube desde la interfaz
   * y se guarda contra la org. La próxima no necesita que nadie toque código.
   *
   * Se imprime en el expediente de solicitud (las dos páginas) y está
   * disponible para las facturas, que leen el mismo `Org.logo`.
   */
  subirLogo: async ({ cookies, request }) => {
    const enviado = await request.formData();
    const archivo = enviado.get('logo');

    if (!(archivo instanceof File) || archivo.size === 0) {
      return fail(400, { error: 'Elegí un archivo de imagen.' });
    }
    // PNG con fondo transparente es lo que mejor queda sobre el papel blanco
    // del PDF. JPG sirve, pero arrastra su propio fondo.
    if (!/^image\/(png|jpeg|webp|gif)$/.test(archivo.type)) {
      return fail(400, { error: 'El logo tiene que ser PNG, JPG, WEBP o GIF.' });
    }
    // Se incrusta entero dentro de cada PDF: un archivo grande engorda todos
    // los expedientes, uno por uno, para siempre.
    if (archivo.size > 2 * 1024 * 1024) {
      return fail(400, { error: 'El logo no puede pesar más de 2 MB.' });
    }

    const cuerpo = new FormData();
    cuerpo.append('logo', archivo, archivo.name);
    try {
      await updateOrgSettings({ cookies }, cuerpo);
      return { logoSubido: true };
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) {
        return fail(403, { error: 'Solo un administrador puede cambiar el logo.' });
      }
      return fail(400, { error: readableError(err, 'No se pudo guardar el logo.') });
    }
  },

  quitarLogo: async ({ cookies }) => {
    try {
      // JSON y no multipart: es la única forma de mandar un null de verdad,
      // que es lo que vacía un ImageField. Una cadena vacía en multipart la
      // toma como "campo ausente" y no borra nada.
      await updateOrgSettings({ cookies }, { logo: null });
      return { logoQuitado: true };
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) {
        return fail(403, { error: 'Solo un administrador puede cambiar el logo.' });
      }
      return fail(400, { error: readableError(err, 'No se pudo quitar el logo.') });
    }
  },

  clearSampleData: async ({ cookies }) => {
    try {
      const { deleted, retained_by_type } = await clearSampleData(cookies);
      // Retained records are not a failure. They are demo rows the user has
      // since attached real work to, which the backend deliberately keeps.
      // Passing the count through lets the page say so instead of reporting a
      // smaller number than the user expected with no explanation.
      const retained = Object.values(retained_by_type ?? {}).reduce((a, b) => a + b, 0);
      return { cleared: deleted ?? 0, retained };
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) {
        return fail(403, { error: 'Solo un administrador puede borrar los datos de ejemplo.' });
      }
      return fail(400, { error: readableError(err, 'No se pudieron borrar los datos de ejemplo.') });
    }
  }
};
