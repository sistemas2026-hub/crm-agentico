import { fail } from '@sveltejs/kit';
import {
  leerIndicadores,
  listarPropuestas,
  leerPropuesta,
  leerAutonomia,
  correrCiclo,
  correrAsistente,
  revisarPropuesta,
  resumenOperativo
} from '$lib/server/v2/supervisor-noc.js';

/**
 * POR QUE ESTA RUTA VIVE EN (no-layout)
 * -------------------------------------
 * La pantalla trae su PROPIA navegacion lateral y su propia barra superior,
 * que es lo que la hace ser esta pantalla y no otra. Montada bajo (app)
 * quedaria con dos barras laterales, una encima de la otra.
 *
 * (no-layout) NO significa publica: 'hooks.server.js' gatea por lista blanca
 * (PUBLIC_ROUTES) y esta ruta no esta en ella, asi que sigue exigiendo sesion
 * como cualquier otra. El gate de ROL se agrega aca abajo, ademas del que el
 * backend ya aplica: dos capas, igual que el resto del CRM.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals, url }) {
  const rol = locals.profile?.role ?? null;
  const puedeVer = ROLES_GESTION.has(rol);

  // Sin rol de gestion no se pide nada: el backend responderia 403 a cada
  // llamada y la pantalla mostraria cinco errores en vez de un motivo.
  if (!puedeVer) {
    return {
      puedeVer: false,
      rol,
      org: locals.org?.name ?? null,
      usuario: locals.user?.email ?? null
    };
  }

  const dias = url.searchParams.get('dias');
  const senal = url.searchParams.get('senal');
  const seleccionada = url.searchParams.get('propuesta');

  const [indicadores, todas, pendientes, autonomia] = await Promise.all([
    leerIndicadores({ cookies }, dias ?? undefined),
    listarPropuestas({ cookies }, senal ? { tipo_senal: senal } : {}),
    listarPropuestas({ cookies }, { estado: 'propuesta' }),
    leerAutonomia()
  ]);

  // El detalle se pide solo si hay una seleccionada. La maqueta mostraba un
  // inspector siempre abierto sobre un hallazgo fijo; aca depende de la
  // seleccion real, y sin seleccion la seccion dice que no hay ninguna.
  const detalle = seleccionada ? await leerPropuesta({ cookies }, seleccionada) : { datos: null, error: null };

  return {
    puedeVer: true,
    rol,
    org: locals.org?.name ?? null,
    usuario: locals.user?.email ?? null,
    indicadores: indicadores.datos,
    errorIndicadores: indicadores.error,
    resumen: indicadores.datos ? resumenOperativo(indicadores.datos) : [],
    hallazgos: todas,
    pendientes,
    autonomia,
    detalle: detalle.datos,
    errorDetalle: detalle.error,
    filtroSenal: senal,
    seleccionada
  };
}

/**
 * NINGUNA DE ESTAS ACCIONES EJECUTA NADA CONTRA UN SISTEMA EXTERNO.
 *
 * 'ciclo' y 'asistente' escriben filas de PropuestaSupervisor y sus renglones
 * de auditoria. 'revisar' mueve el estado de una propuesta. Aceptar una
 * propuesta significa "el Jefe de Operaciones esta de acuerdo", nunca "se
 * hizo" -- el estado 'ejecutada' no existe en el modelo, y por eso la
 * ausencia es comprobable en vez de prometida.
 *
 * @type {import('./$types').Actions}
 */
export const actions = {
  async ciclo({ cookies, locals }) {
    if (!ROLES_GESTION.has(locals.profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr el ciclo.' });
    }
    try {
      const r = await correrCiclo({ cookies });
      return { ok: true, tipo: 'ciclo', resumen: r?.resumen ?? null, shadow_mode: r?.shadow_mode ?? null };
    } catch (/** @type {any} */ err) {
      return fail(err?.status ?? 500, { error: err?.message ?? 'No se pudo correr el ciclo.' });
    }
  },

  async asistente({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(locals.profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr un asistente.' });
    }
    const datos = await request.formData();
    const dominio = String(datos.get('dominio') ?? '');
    try {
      const r = await correrAsistente({ cookies }, dominio);
      return { ok: true, tipo: 'asistente', dominio, asistente: r };
    } catch (/** @type {any} */ err) {
      return fail(err?.status ?? 500, { error: err?.message ?? 'No se pudo correr el asistente.' });
    }
  },

  async revisar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(locals.profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede revisar una propuesta.' });
    }
    const datos = await request.formData();
    const id = String(datos.get('id') ?? '');
    const decision = String(datos.get('decision') ?? '');
    const comentario = String(datos.get('comentario') ?? '');

    // La misma regla que RevisionSerializer.validate, adelantada para que el
    // motivo se pida en la pantalla y no vuelva como un 400 sin contexto. El
    // backend la sigue aplicando: esta copia es comodidad, no la garantia.
    if ((decision === 'rechazada' || decision === 'modificada') && !comentario.trim()) {
      return fail(400, { error: 'Rechazar o modificar exige decir por qué.', id });
    }

    try {
      const r = await revisarPropuesta({ cookies }, id, { decision, comentario });
      return { ok: true, tipo: 'revision', id, decision, resultado: r };
    } catch (/** @type {any} */ err) {
      return fail(err?.status ?? 500, { error: err?.message ?? 'No se pudo registrar la revisión.', id });
    }
  }
};
