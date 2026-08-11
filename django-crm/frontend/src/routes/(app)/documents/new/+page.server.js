import { fail, redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { getUploadOptions, uploadDocument, STATUS_CHOICES } from '$lib/server/v2/documents.js';
import { readableError } from '$lib/server/v2/form-errors.js';

/**
 * Uploading a document.
 *
 * Open to any org member: `POST /api/documents/` gates on auth + org context
 * only, so a rep can add their own file, not just an admin. `created_by` and
 * `org` are server-derived and never read from the body. The share pickers only
 * ever offer in-org people and teams, and the view re-scopes both to the
 * caller's org, so a share can never point at another tenant. (Editing and
 * deleting are the narrow writes, creator or admin, enforced server-side.)
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load(event) {
  const opciones = await getUploadOptions(event);

  // Los roles del asistente, para elegir quien puede recuperar el documento.
  // Se piden aca (server-side) y no desde el browser: la URL del motor no
  // sale nunca al cliente. Si el asistente no esta configurado o no responde,
  // la pagina sigue sirviendo para subir archivos comunes -- solo se oculta
  // la parte del asistente.
  let rolesAsistente = [];
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (baseUrl && tenant) {
    try {
      const r = await event.fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`);
      if (r.ok) {
        const datos = await r.json();
        rolesAsistente = (datos.agentes ?? []).map((a) => ({
          nombre: a.nombre,
          area: a.area,
          cargo: a.cargo,
          esCliente: a.orientado_a === 'cliente_final'
        }));
      }
    } catch {
      // Sin roles: la seccion del asistente no se dibuja.
    }
  }

  return { ...opciones, rolesAsistente };
}

/** @type {import('./$types').Actions} */
export const actions = {
  create: async (event) => {
    const form = await event.request.formData();

    const title = form.get('title')?.toString().trim() ?? '';
    const statusRaw = form.get('status')?.toString() ?? 'active';
    const status = STATUS_CHOICES.includes(statusRaw) ? statusRaw : 'active';
    const file = form.get('document_file');
    const shared_to = form.getAll('shared_to').map((v) => v.toString());
    const teams = form.getAll('teams').map((v) => v.toString());
    const usar_en_asistente = form.get('usar_en_asistente') === 'on';
    // Los roles solo cuentan si el documento entra al asistente.
    const rolesElegidos = usar_en_asistente
      ? form.getAll('roles_asistente').map((v) => v.toString())
      : [];
    const roles_asistente = rolesElegidos.join(', ');

    // What the form re-fills on a rejected submit. The file is never echoed.
    // A browser will not let us re-populate a file input, so a rejected upload
    // asks for the file again, which is the honest thing to do.
    const values = { title, status, shared_to, teams, usar_en_asistente, roles_asistente };

    // Mirror the server's required-field checks so an obvious miss does not cost
    // a round trip. The serializer enforces both regardless.
    if (!title) {
      return fail(400, { values, error: 'Ponele un título al documento.' });
    }
    if (!(file instanceof File) || file.size === 0) {
      return fail(400, { values, error: 'Elegí un archivo para subir.' });
    }

    // El fragmentador solo lee Word. Decirlo aca evita subir el archivo entero
    // para que lo rechace el servidor.
    if (usar_en_asistente && !file.name.toLowerCase().endsWith('.docx')) {
      return fail(400, {
        values,
        error: `El asistente solo puede leer archivos .docx, y "${file.name}" no lo es. ` +
          'Podés subirlo igual como documento, sin marcarlo para el asistente.'
      });
    }

    try {
      await uploadDocument(event.cookies, {
        title, status, file, shared_to, teams, usar_en_asistente, roles_asistente
      });
    } catch (/** @type {any} */ err) {
      if (err?.status === 401 || err?.status === 403) {
        return fail(err.status, { values, error: 'No tenés permiso para subir archivos acá.' });
      }
      return fail(400, {
        values,
        error: readableError(err, 'No se pudo subir este documento.')
      });
    }

    redirect(303, '/documents');
  }
};
