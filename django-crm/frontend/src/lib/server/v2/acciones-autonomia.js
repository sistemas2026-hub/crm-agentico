import { fail } from '@sveltejs/kit';
import { cambiarAutonomia, cambiarCriticidad } from '$lib/server/v2/capacidad.js';

/**
 * QUE UN AGENTE HAGA SOLA UNA ACCION, O QUE VUELVA A PEDIR APROBACION
 * (02/11/2026, PRD §2 y §8.18). Lo decide una persona ADMIN; el autor y su rol
 * salen de la SESION, nunca del navegador, y el motor los vuelve a exigir.
 * Sin 'rol' vale para todos los agentes que usan la herramienta.
 *
 * Vivian en routes/(app)/agentes/+page.server.js. Desde el 13/11/2026 la
 * palanca esta en la pagina de cada agente (/agentes/[nombre]), y las dos
 * paginas exportan ESTAS acciones -- una sola implementacion, no dos que un
 * dia digan cosas distintas. AutonomiaDeAccion.svelte postea a '?/promover' y
 * '?/retirar' de la pagina en la que esta.
 */

const NOMBRE = /^[a-z0-9_]{1,64}$/;

/** Lo que el motor rechaza a proposito, dicho para quien decide (409, no 502). */
const RECHAZOS = /** @type {Record<string, string>} */ ({
  SIN_EVIDENCIA: 'Todavía no alcanza: mirá lo que le falta.',
  AGENTE_SIN_ESA_HERRAMIENTA: 'Este agente no usa esa herramienta.',
  YA_ES_AUTONOMA: 'Este agente ya la hace solo.',
  CONFIG_SIN_CONFIRMAR: 'No se pudo confirmar la configuración de la empresa desde la base. Probá de nuevo en un minuto.',
  NO_CANDIDATA: 'Esa acción no tiene en código las comprobaciones que hacen falta para hacerse sola.',
  NO_ES_UNA_ACCION_CON_APROBACION: 'Esa acción no pide aprobación: no hay nada que cambiar.'
});

export const accionesDeAutonomia = {
  /** @param {any} event */
  async promover({ locals, fetch, request }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { autonomia: { error: 'Solo un administrador puede cambiar lo que un agente hace solo.' } });
    }
    const form = await request.formData();
    const accion = form.get('accion')?.toString().trim() ?? '';
    const rol = form.get('rol')?.toString().trim() ?? '';
    if (!NOMBRE.test(accion) || (rol && !NOMBRE.test(rol))) {
      return fail(400, { autonomia: { error: 'Esa acción o ese agente no se reconocen.' } });
    }
    if (form.get('confirmo') !== 'si') {
      return fail(400, { autonomia: { accion, rol, error: 'Marcá que entendés que la acción va a hacerse sola.' } });
    }
    try {
      await cambiarAutonomia(locals, fetch, 'promover', { accion, ...(rol ? { rol } : {}) });
    } catch (/** @type {any} */ e) {
      const conocido = RECHAZOS[e?.codigo];
      return fail(conocido ? 409 : 502,
        { autonomia: { accion, rol, error: conocido || e?.message || 'No se pudo cambiar.', faltan: e?.faltan ?? [] } });
    }
    return { autonomia: { accion, rol, ok: 'promovida' } };
  },

  /** @param {any} event */
  async retirar({ locals, fetch, request }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { autonomia: { error: 'Solo un administrador puede cambiar lo que un agente hace solo.' } });
    }
    const form = await request.formData();
    const accion = form.get('accion')?.toString().trim() ?? '';
    const rol = form.get('rol')?.toString().trim() ?? '';
    const motivo = form.get('motivo')?.toString().trim() ?? '';
    if (!NOMBRE.test(accion) || (rol && !NOMBRE.test(rol))) {
      return fail(400, { autonomia: { error: 'Esa acción o ese agente no se reconocen.' } });
    }
    if (!motivo) return fail(400, { autonomia: { accion, rol, error: 'Decí por qué vuelve a pedir aprobación.' } });
    try {
      await cambiarAutonomia(locals, fetch, 'retirar', { accion, motivo, ...(rol ? { rol } : {}) });
    } catch (/** @type {any} */ e) {
      return fail(502, { autonomia: { accion, rol, error: e?.message || 'No se pudo cambiar.' } });
    }
    return { autonomia: { accion, rol, ok: 'retirada' } };
  },

  /**
   * Si una accion es critica en esta empresa (04/11/2026). Declararla no
   * critica habilita darle autonomia sin evidencia: pide la casilla.
   * @param {any} event
   */
  async criticidad({ locals, fetch, request }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { autonomia: { error: 'Solo un administrador puede decidir si una acción es crítica.' } });
    }
    const form = await request.formData();
    const accion = form.get('accion')?.toString().trim() ?? '';
    const critica = form.get('critica')?.toString();
    if (!NOMBRE.test(accion) || (critica !== 'si' && critica !== 'no')) {
      return fail(400, { autonomia: { error: 'Esa acción o ese valor no se reconocen.' } });
    }
    if (critica === 'no' && form.get('confirmo') !== 'si') {
      return fail(400, { autonomia: { accion, criticidad: true,
        error: 'Marcá que entendés que va a poder hacerse sola sin evidencia previa.' } });
    }
    try {
      await cambiarCriticidad(locals, fetch, { accion, critica: critica === 'si' });
    } catch (/** @type {any} */ e) {
      return fail(e?.codigo === 'SOLO_ADMIN' ? 403 : 400,
        { autonomia: { accion, criticidad: true, error: e?.message || 'No se pudo cambiar.' } });
    }
    return { autonomia: { accion, criticidad: true, ok: critica === 'si' ? 'critica' : 'no_critica' } };
  }
};
