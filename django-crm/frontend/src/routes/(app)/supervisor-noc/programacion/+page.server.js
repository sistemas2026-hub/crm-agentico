import { fail } from '@sveltejs/kit';

import { leerDiaPublicado } from '$lib/server/v2/dia-publicado.js';
import { hoyDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';
import {
  guardarConfiguracionDeMaterial,
  leerConfiguracionDeMaterial,
  leerMaterialDelDia
} from '$lib/server/v2/material-del-dia.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';
import { cuerpoDeConfiguracion } from '$lib/supervisor/material-del-dia.js';

/**
 * Programación — lo que quedó publicado un día (28/10/2026).
 *
 * Pedido del usuario: «cuando el supervisor publique, salga en Programación lo
 * que publicó», con esta pantalla después de Despacho. Despacho es lo que
 * FALTA; esto es lo que QUEDÓ: por cuadrilla, cada orden con quién la asignó
 * (el Supervisor o una persona) y a qué hora, y si al técnico le llegó el
 * aviso.
 *
 * Y EL MATERIAL DEL DÍA (28/10/2026, SPEC/objetivos/material-del-dia.md): qué
 * kit le tocaría a cada cuadrilla, de qué bodega, y qué falta. Fase 1: solo
 * propone; lo único que se escribe desde acá es la configuración (qué kit
 * lleva cada labor y de qué bodega carga cada cuadrilla).
 *
 * La pantalla de antes —los planes semanales— vive en
 * /supervisor-noc/planes-semanales, enlazada desde acá.
 *
 * Solo quien gestiona: muestra el trabajo de todas las cuadrillas y el nombre
 * de cada técnico (el backend lo exige igual).
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies, locals }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
  if (!ROLES_GESTION.has(rol)) {
    return {
      puedeVer: false, dia: '', publicado: null, error: false,
      material: null, errorMaterial: false, configuracion: null
    };
  }

  //  Hoy en el reloj de la EMPRESA, no en el del servidor (UTC).
  const pedido = (url.searchParams.get('dia') ?? '').trim();
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(pedido) ? pedido : await hoyDeLaEmpresa(locals, cookies);
  const [dp, mat, conf] = await Promise.all([
    leerDiaPublicado({ cookies }, dia),
    leerMaterialDelDia({ cookies }, dia),
    leerConfiguracionDeMaterial({ cookies })
  ]);
  return {
    puedeVer: true,
    dia,
    publicado: dp.publicado,
    error: dp.error,
    material: mat.material,
    errorMaterial: mat.error,
    configuracion: conf.configuracion
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  material: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { error: 'Esto es para quien gestiona.' });
    try {
      await guardarConfiguracionDeMaterial({ cookies }, cuerpoDeConfiguracion(await request.formData()));
      return { hecho: 'Quedó guardado de dónde y qué carga cada cuadrilla.' };
    } catch (e) {
      return fail(400, { error: mensajeDeError(e) });
    }
  }
};
