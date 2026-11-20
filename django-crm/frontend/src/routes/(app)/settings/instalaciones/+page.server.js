/**
 * Ajustes → Instalaciones: los dos equipos de WispHub del flujo, y quién
 * decide la factibilidad.
 *
 * Uno recibe la solicitud nueva (valida si el servicio llega a esa dirección),
 * el otro la ejecuta. Se eligen de una lista traída de WispHub, no se
 * escriben: un id tipeado mal es un ticket a nombre de nadie.
 *
 * QUIÉN DECIDE (12/11/2026): las áreas de la empresa que pueden ver la bandeja,
 * decidir y abrir el expediente con la cédula, además de administración,
 * supervisión y operaciones. Ninguna elegida = solo esos tres roles. El
 * backend lo exige (solicitudes/permisos.py); esta pantalla solo lo edita, y
 * guardar es de ADMIN también en el servidor.
 */
import { fail } from '@sveltejs/kit';
import {
  guardarAjustes,
  guardarAjustesDecision,
  leerAjustes,
  leerAjustesDecision,
  leerTecnicos
} from '$lib/server/v2/solicitudes.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals }) {
  const [ajustes, tecnicos, decision] = await Promise.all([
    leerAjustes(cookies),
    leerTecnicos(cookies),
    leerAjustesDecision(cookies)
  ]);
  return { ajustes, tecnicos, decision, can_edit: locals.profile?.role === 'ADMIN' };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, cookies, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN });

    const form = await request.formData();
    const valores = {
      tecnico_solicitudes: form.get('tecnico_solicitudes')?.toString() ?? '',
      email_solicitudes: form.get('email_solicitudes')?.toString() ?? '',
      tecnico_aprobadas: form.get('tecnico_aprobadas')?.toString() ?? '',
      email_aprobadas: form.get('email_aprobadas')?.toString() ?? ''
    };
    if (!valores.tecnico_solicitudes || !valores.tecnico_aprobadas) {
      return fail(400, { error: 'Hay que elegir los dos equipos.' });
    }
    try {
      await guardarAjustes(cookies, valores);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar.' });
    }
    return { guardado: true };
  },

  async decision({ request, cookies, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN, de: 'decision' });

    const form = await request.formData();
    const metros = Number(form.get('precision_gps_maxima_m') ?? 200);
    if (!Number.isInteger(metros) || metros < 1 || metros > 5000) {
      return fail(400, { error: 'La precisión máxima va entre 1 y 5000 metros.', de: 'decision' });
    }
    try {
      await guardarAjustesDecision(cookies, {
        areas_que_deciden: form.getAll('areas_que_deciden').map((a) => a.toString()),
        // Un checkbox apagado no viaja en el formulario: ausente = apagada.
        prefactibilidad_activa: form.get('prefactibilidad_activa') === 'on',
        precision_gps_maxima_m: metros
      });
    } catch (/** @type {any} */ err) {
      return fail(400, { error: err?.message || 'No se pudo guardar.', de: 'decision' });
    }
    return { guardado: true, de: 'decision' };
  }
};
