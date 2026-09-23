import { fail } from '@sveltejs/kit';
import {
  leerIndicadores,
  listarPropuestas,
  leerAutonomia,
  correrCiclo,
  correrAsistente,
  revisarPropuesta,
  cancelarPropuesta,
  resumenOperativo,
  traducirError
} from '$lib/server/v2/supervisor-noc.js';
import { leerCapacidad } from '$lib/server/v2/programacion-noc.js';

/**
 * POR QUE ESTA RUTA VIVE EN (app)
 * -------------------------------
 * Primero se monto en (no-layout), para que la pantalla conservara la barra
 * lateral y la cabecera que traia su diseno. El efecto fue el que
 * Sidebar.svelte ya dejo escrito sobre /instalaciones: una pantalla sin
 * entrada en el menu no esta terminada, esta escondida.
 *
 * El gate de ROL va aca ademas del que aplica el backend: dos capas, igual
 * que el resto del CRM. Ocultar un boton no es una barrera -- la barrera es
 * 'EsJefeDeOperaciones' en cada vista de operaciones, y sigue estando.
 *
 * LO QUE ESTA PANTALLA NO PUEDE HACER, POR DISENO
 * Mover el interruptor de autonomia, cambiar el techo, ejecutar una
 * herramienta o aplicar una propuesta. No hay accion para nada de eso: no es
 * que esten ocultas, es que no existen en este archivo.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals, url }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
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

  // Las propuestas se traen ENTERAS y una sola vez. El filtro por tipo de
  // señal se aplica despues, en el navegador: el backend ya devuelve el
  // conjunto completo (corta en 200 y hoy hay 92), asi que pedirle una
  // consulta por cada pildora seria una vuelta al servidor para reordenar
  // datos que ya estan en pantalla.
  // La capacidad EXIGE un dia (el backend responde 400 sin el), asi que el
  // tablero abre con hoy. Es una lectura mas, no una pantalla nueva: el
  // bloque de tecnicos necesita quien trabaja hoy y cuanto tiene encima.
  const hoy = new Date().toISOString().slice(0, 10);

  const [indicadores, todas, autonomia, capacidad] = await Promise.all([
    leerIndicadores({ cookies }, dias ?? undefined),
    listarPropuestas({ cookies }),
    leerAutonomia(),
    leerCapacidad({ cookies }, hoy)
  ]);

  return {
    puedeVer: true,
    rol,
    org: locals.org?.name ?? null,
    usuario: locals.user?.email ?? null,
    indicadores: indicadores.datos,
    errorIndicadores: indicadores.error,
    resumen: resumenOperativo(indicadores.datos),
    hallazgos: todas,
    autonomia,
    dia: hoy,
    capacidad
  };
}

/**
 * NINGUNA DE ESTAS ACCIONES EJECUTA NADA CONTRA UN SISTEMA EXTERNO.
 *
 * 'ciclo' y 'asistente' escriben filas de PropuestaSupervisor y sus renglones
 * de auditoria. 'revisar' y 'cancelar' mueven el estado de una propuesta.
 * Aceptar significa "el Jefe de Operaciones esta de acuerdo", nunca "se hizo":
 * el contrato del backend devuelve `ejecutada: false` en las dos, y el estado
 * 'ejecutada' no existe en el modelo.
 *
 * @type {import('./$types').Actions}
 */
export const actions = {
  async ciclo({ cookies, locals }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr el ciclo.' });
    }
    try {
      const r = await correrCiclo({ cookies });
      return {
        ok: true,
        tipo: 'ciclo',
        resumen: r?.resumen ?? null,
        shadow_mode: r?.shadow_mode ?? null,
        acciones_ejecutadas: r?.acciones_ejecutadas ?? 0
      };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'el ciclo de análisis');
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  },

  async asistente({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr un asistente.' });
    }
    const datos = await request.formData();
    const dominio = String(datos.get('dominio') ?? '');
    try {
      const r = await correrAsistente({ cookies }, dominio);
      return { ok: true, tipo: 'asistente', dominio, asistente: r };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'el asistente de ' + dominio);
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  },

  async revisar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
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
      return {
        ok: true,
        tipo: 'revision',
        id,
        decision,
        // Viaja tal cual lo devuelve el backend. Es la prueba, en la propia
        // respuesta, de que revisar no ejecuto nada.
        ejecutada: r?.ejecutada ?? false,
        aviso: r?.aviso ?? null
      };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'la revisión');
      return fail(e.status ?? 502, { error: e.mensaje, id });
    }
  },

  async cancelar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede cancelar una propuesta.' });
    }
    const datos = await request.formData();
    const id = String(datos.get('id') ?? '');
    const motivo = String(datos.get('motivo') ?? '');

    // Obligatorio en el backend (CancelacionSerializer) y con razon: cancelar
    // sin decir por que deja una auditoria que no explica nada.
    if (!motivo.trim()) {
      return fail(400, { error: 'Cancelar exige decir por qué la condición ya no aplica.', id });
    }

    try {
      const r = await cancelarPropuesta({ cookies }, id, motivo);
      return { ok: true, tipo: 'cancelacion', id, ejecutada: r?.ejecutada ?? false };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'la cancelación');
      return fail(e.status ?? 502, { error: e.mensaje, id });
    }
  }
};
