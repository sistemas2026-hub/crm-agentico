import { fail } from '@sveltejs/kit';
import { leerAutonomia, listarPropuestas } from '$lib/server/v2/supervisor-noc.js';
import {
  leerJornada,
  leerCapacidad,
  secuenciarJornada,
  publicarProgramacion,
  resumenProgramacion,
  SENALES_PROGRAMACION
} from '$lib/server/v2/programacion-noc.js';

/**
 * Programación — Supervisor NOC IA.
 *
 * Es la segunda vista del mismo modulo, no una pantalla suelta: cuelga de
 * /supervisor-noc para que las dos se alcancen con las pestañas de arriba y
 * ninguna quede escondida detras de una URL que haya que adivinar.
 *
 * EL DIA ES OBLIGATORIO, Y ESO VIENE DEL BACKEND
 * 'JornadaView' responde 400 FALTA_FILTRO sin 'dia' ni 'plan', con un motivo
 * que conviene respetar en vez de esquivar: "sin filtro, 'la jornada' no
 * significa nada". La pantalla abre en HOY y deja cambiarlo.
 *
 * LO QUE NO EXISTE ACA
 * Ninguna accion para reprogramar una orden, reasignar a alguien, despachar o
 * mover la autonomia. Las dos escrituras que hay --secuenciar y publicar--
 * tocan el ORDEN PROPUESTO y el ESTADO DE UN PLAN, y el propio backend lo
 * deja escrito: no reprograman, no reasignan y no llaman a ningun sistema
 * externo.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** Hoy, en YYYY-MM-DD y en la zona del servidor. */
function hoy() {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, '0');
  const dia = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mes}-${dia}`;
}

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals, url }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
  if (!ROLES_GESTION.has(rol)) {
    return { puedeVer: false, rol, org: locals.org?.name ?? null, dia: hoy() };
  }

  const pedido = url.searchParams.get('dia');
  // Un dia mal escrito no se manda al backend: se cae a hoy y se avisa.
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(pedido ?? '') ? /** @type {string} */ (pedido) : hoy();
  const diaInvalido = !!pedido && pedido !== dia;

  const [jornada, capacidad, propuestas, autonomia] = await Promise.all([
    leerJornada({ cookies }, dia),
    leerCapacidad({ cookies }, dia),
    listarPropuestas({ cookies }),
    leerAutonomia()
  ]);

  // Las recomendaciones de esta pantalla son las propuestas del dominio de
  // programacion. No hay un endpoint aparte y no hace falta: es la misma cola,
  // acotada a sus señales.
  const recomendaciones = (propuestas.resultados ?? []).filter((/** @type {any} */ p) =>
    SENALES_PROGRAMACION.includes(p.tipo_senal)
  );

  return {
    puedeVer: true,
    rol,
    org: locals.org?.name ?? null,
    dia,
    diaInvalido,
    jornada,
    capacidad,
    recomendaciones,
    errorPropuestas: propuestas.error,
    autonomia,
    resumen: resumenProgramacion(jornada, capacidad)
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Reordena la jornada entera en una transaccion. NO reprograma ninguna
   * orden ni toca su asignacion: solo el orden propuesto.
   */
  async secuenciar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede secuenciar la jornada.' });
    }
    const datos = await request.formData();
    const dia = String(datos.get('dia') ?? '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dia)) {
      return fail(400, { error: 'Falta el día de la jornada a secuenciar.' });
    }
    try {
      const r = await secuenciarJornada({ cookies }, { dia });
      return { ok: true, tipo: 'secuenciar', resultado: r };
    } catch (/** @type {any} */ err) {
      return fail(err?.status ?? 502, {
        error: err?.status === 403
          ? 'Solo el Jefe de Operaciones puede secuenciar la jornada.'
          : 'No fue posible secuenciar la jornada.'
      });
    }
  },

  /** Publica un plan semanal: borrador -> publicada, y nada mas. */
  async publicar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede publicar un plan.' });
    }
    const datos = await request.formData();
    const id = String(datos.get('programacion') ?? '');
    if (!id) return fail(400, { error: 'Falta el plan a publicar.' });
    try {
      const r = await publicarProgramacion({ cookies }, id);
      return { ok: true, tipo: 'publicar', resultado: r };
    } catch (/** @type {any} */ err) {
      return fail(err?.status ?? 502, { error: 'No fue posible publicar el plan.' });
    }
  }
};
