import { fail } from '@sveltejs/kit';
import {
  leerPlantillasDeTrabajo,
  leerCasosDespachables,
  despacharACampo
} from '$lib/server/v2/despacho.js';

/**
 * Despacho a campo — Supervisor NOC.
 *
 * La pantalla que faltaba. `POST /campo/trabajos/crear/` existía y **nadie lo
 * llamaba**: las órdenes solo se podían crear por API directa, así que el ciclo
 * de la madrugada no tenía qué repartir y la clasificación no tenía dónde
 * ejercitarse.
 *
 * LA FICHA SE PIDE, NO VIENE SIEMPRE. Traer la evidencia de cada caso es una
 * llamada al motor por caso —que a su vez habla con WispHub y SmartOLT— y abrir
 * la lista no puede costar veinticinco viajes de red. Se piden con `?ficha=1`,
 * cuando quien mira ya decidió que va a despachar.
 */

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies }) {
  const conFicha = url.searchParams.get('ficha') === '1';

  const [plantillas, casos] = await Promise.all([
    leerPlantillasDeTrabajo({ cookies }),
    leerCasosDespachables({ cookies }, conFicha)
  ]);

  return {
    conFicha,
    plantillas: plantillas.plantillas,
    labores: plantillas.labores,
    plantillasSinClasificar: plantillas.sinClasificar,
    casos: casos.casos,
    tope: casos.tope,
    sinAprobados: casos.sinAprobados,
    // NO SE INVENTA UNA LISTA VACÍA CUANDO LA LECTURA FALLÓ. Una empresa sin
    // casos abiertos y una consulta que no respondió se dibujan distinto.
    error: plantillas.error || casos.error
  };
}

/** Traduce lo que devuelve el backend a una frase, sin inventar una. */
function mensajeDe(e) {
  const detalle = e?.data?.detalle || e?.data?.error || e?.message;
  return typeof detalle === 'string' && detalle.trim()
    ? detalle.trim()
    : 'No se pudo despachar.';
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Manda el caso a campo.
   *
   * La plantilla la elige quien despacha: la sugerencia viene marcada pero no
   * decide. Es el mismo corte que el resto del Supervisor NOC — observa,
   * analiza, propone.
   */
  despachar: async ({ request, cookies }) => {
    const f = await request.formData();
    const caseId = String(f.get('case_id') ?? '').trim();
    const plantilla = String(f.get('work_type_version_id') ?? '').trim();
    if (!plantilla) return fail(400, { error: 'Elegí con qué plantilla va.' });

    //  LA CLAVE DE IDEMPOTENCIA LA ARMA EL SERVIDOR, no el navegador: una
    //  clave nueva por intento es un identificador único, no una clave
    //  idempotente, y un doble clic crearía dos órdenes. Con el caso y la
    //  plantilla, el mismo despacho repetido es la misma clave; una segunda
    //  visita deliberada lleva otra plantilla, u otra fecha.
    const programada = String(f.get('programada_para') ?? '').trim();
    const clave = `despacho:${caseId || 'manual'}:${plantilla}:${programada}`;

    try {
      const r = await despacharACampo({ cookies }, {
        work_type_version_id: plantilla,
        case_id: caseId || undefined,
        cliente_nombre: String(f.get('cliente_nombre') ?? '').trim(),
        cliente_telefono: String(f.get('cliente_telefono') ?? '').trim(),
        cliente_direccion: String(f.get('cliente_direccion') ?? '').trim(),
        cliente_detalle_acceso: String(f.get('detalle_acceso') ?? '').trim(),
        prioridad: String(f.get('prioridad') ?? '').trim() || undefined,
        resumen: String(f.get('resumen') ?? '').trim() || undefined,
        programada_para: programada || undefined
      }, clave);

      const numero = r?.orden?.numero;
      return {
        hecho: numero
          ? `Orden #${numero} despachada.`
          : 'Orden despachada.',
        numero
      };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  }
};
