import { fail } from '@sveltejs/kit';
import {
  leerAutonomia,
  listarPropuestas,
  correrAsistente,
  traducirError
} from '$lib/server/v2/supervisor-noc.js';
import {
  leerJornada,
  leerCapacidad,
  secuenciarJornada,
  publicarProgramacion,
  reprogramarOrden,
  cambiarSecuencia,
  programarOrden,
  resumenProgramacion,
  SENALES_PROGRAMACION,
  CAUSAS
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
 * LAS CINCO ESCRITURAS, Y LO QUE CADA UNA PUEDE TOCAR
 *   secuenciar   -> el orden propuesto de la jornada entera
 *   secuencia    -> el orden propuesto de UNA linea
 *   publicar     -> el estado de un plan (borrador -> publicada)
 *   reprogramar  -> la fecha de una orden QUE YA ESTA EN UN PLAN
 *   analizar     -> corre el asistente, que escribe propuestas en la cola
 *
 * Ninguna reasigna a nadie, ninguna despacha y ninguna llama a un sistema
 * externo. Todas piden confirmacion en la pantalla antes de salir.
 *
 * LO QUE SIGUE SIN EXISTIR
 * Programar una orden que NO esta en ningun plan. El endpoint del backend
 * existe, pero exige 'programacion_semanal_id' y no hay ninguna ruta que
 * liste los planes semanales -- elegirlo seria pedirle un UUID a una persona.
 * Falta 'GET /api/operaciones/programacion/'. No se resuelve desde el
 * frontend.
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
    causas: CAUSAS,
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
  },


  /**
   * Programa una orden dentro de un plan elegido de la lista real.
   *
   * Las reglas siguen siendo del backend: que el plan admita lineas, que la
   * fecha caiga en su semana y que una adicion a un plan ya publicado exija
   * causa las valida 'programar_orden'. Aca solo se comprueba que los dos
   * campos obligatorios vengan, para no gastar un viaje.
   */
  async programar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede programar una orden.' });
    }
    const datos = await request.formData();
    const orden = String(datos.get('orden') ?? '');
    const plan = String(datos.get('plan') ?? '');
    const cuando = String(datos.get('programada_para') ?? '');
    const causa = String(datos.get('causa') ?? '');
    const motivo = String(datos.get('motivo') ?? '');

    if (!orden) return fail(400, { error: 'Falta la orden a programar.' });
    if (!plan) return fail(400, { error: 'Elegí un plan semanal.' });
    if (!cuando) return fail(400, { error: 'Falta la fecha y hora.' });

    try {
      const r = await programarOrden({ cookies }, orden, {
        programacion_semanal_id: plan,
        programada_para: cuando,
        causa,
        motivo
      });
      return { ok: true, tipo: 'programar', orden, resultado: r };
    } catch (/** @type {any} */ err) {
      // El backend es la autoridad: si rechaza por su propia regla -- plan
      // cerrado, fecha fuera de la semana, causa faltante en un plan
      // publicado -- ese texto es mas util que uno generico nuestro.
      const detalle = err?.body?.detalle ?? err?.body?.error ?? null;
      const e = traducirError(err, 'la programación');
      return fail(e.status ?? 502, { error: detalle ? String(detalle) : e.mensaje });
    }
  },

  /**
   * Reprograma una orden que YA esta en un plan.
   *
   * El id del plan lo manda la pantalla desde la linea de la jornada, que ya
   * lo trae. NO se busca ni se deduce: una orden sin plan no se puede
   * reprogramar desde aca, porque elegir plan exige listarlos y no existe
   * ningun endpoint que lo haga.
   */
  async reprogramar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede reprogramar una orden.' });
    }
    const datos = await request.formData();
    const orden = String(datos.get('orden') ?? '');
    const plan = String(datos.get('plan') ?? '');
    const cuando = String(datos.get('programada_para') ?? '');
    const causa = String(datos.get('causa') ?? '');
    const motivo = String(datos.get('motivo') ?? '');

    if (!orden || !plan) {
      return fail(400, {
        error: 'Esa orden no tiene plan asociado: no se puede reprogramar desde esta pantalla.'
      });
    }
    if (!cuando) return fail(400, { error: 'Falta la fecha y hora nuevas.' });
    if (!causa) return fail(400, { error: 'Reprogramar exige declarar la causa.' });

    try {
      const r = await reprogramarOrden({ cookies }, orden, {
        programacion_semanal_id: plan,
        // El <input type="datetime-local"> entrega "YYYY-MM-DDTHH:mm", que
        // DRF acepta como DateTimeField.
        programada_para: cuando,
        causa,
        motivo
      });
      return { ok: true, tipo: 'reprogramar', orden, resultado: r };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'la reprogramación');
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  },

  /**
   * Cambia el orden propuesto de UNA linea. No reprograma: el backend lo dice
   * y su serializer solo declara 'secuencia'.
   */
  async secuencia({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede cambiar la secuencia.' });
    }
    const datos = await request.formData();
    const linea = String(datos.get('linea') ?? '');
    const bruto = String(datos.get('secuencia') ?? '');
    const causa = String(datos.get('causa') ?? '');
    const motivo = String(datos.get('motivo') ?? '');

    const secuencia = Number(bruto);
    if (!linea) return fail(400, { error: 'Falta la línea.' });
    if (!Number.isInteger(secuencia) || secuencia < 0) {
      // Mismo limite que el CHECK de la base, dicho a tiempo: la base
      // contesta IntegrityError, que nadie puede leer en pantalla.
      return fail(400, { error: 'La secuencia tiene que ser un entero de 0 o más.' });
    }

    try {
      const r = await cambiarSecuencia({ cookies }, linea, { secuencia, causa, motivo });
      return { ok: true, tipo: 'secuencia', linea, secuencia, resultado: r };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'el cambio de secuencia');
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  },

  /**
   * Una pasada del asistente de programacion. Lee sus señales y escribe
   * propuestas en la cola que ya existe: no programa, no asigna y no llama a
   * ningun sistema externo.
   */
  async analizar({ cookies, locals }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr el asistente.' });
    }
    try {
      const r = await correrAsistente({ cookies }, 'programacion');
      return { ok: true, tipo: 'analizar', asistente: r };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'el asistente de programación');
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  }
};
