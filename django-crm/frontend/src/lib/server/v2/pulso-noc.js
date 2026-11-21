/**
 * EL PULSO DEL NOC, del lado del servidor  --  21/11/2026.
 *
 * Junta las cinco fuentes de la franja (ver lib/supervisor/pulso.js) en una
 * sola respuesta. NUNCA rechaza: una fuente que falla viaja como `null` y su
 * ficha dice «sin dato».
 *
 * SE RECUERDA UN MINUTO POR EMPRESA. La franja está en las siete subpantallas
 * y se refresca sola; sin esto, cada cambio de pestaña le costaría al backend
 * cinco lecturas —una de ellas la bandeja entera— para seis números que no
 * cambian a ese ritmo. Mismo criterio que las insignias del menú
 * (hoy-operacion.js), que se recuerdan por organización y rol.
 */
import { listarPropuestas, leerAutonomia } from '$lib/server/v2/supervisor-noc.js';
import { leerFallas } from '$lib/server/v2/fallas-de-red.js';
import { leerDiaPublicado } from '$lib/server/v2/dia-publicado.js';
import { leerMaterialDelDia } from '$lib/server/v2/material-del-dia.js';
import { hoyDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';
import { armarPulso } from '$lib/supervisor/pulso.js';

export const PULSO_FRESCO_MS = 60 * 1000;

/** @type {Map<string, { valor: any, en: number }>} */
const _pulsos = new Map();

/** Para las pruebas. */
export function _olvidarLosPulsos() {
  _pulsos.clear();
}

/**
 * @param {{ locals: any, cookies: any, fetch: typeof globalThis.fetch }} event
 * @param {number} [ahora]
 * @returns {Promise<{ fichas: import('$lib/supervisor/pulso.js').Ficha[], leido_en: string }>}
 */
export async function leerPulso(event, ahora = Date.now()) {
  const org = event.locals?.org?.id;
  const previo = org ? _pulsos.get(org) : null;
  if (previo && ahora - previo.en < PULSO_FRESCO_MS) return previo.valor;

  const { locals, cookies, fetch } = event;
  const hoy = await hoyDeLaEmpresa(locals, cookies).catch(() => null);
  const [prop, fallas, dia, material, autonomia] = await Promise.allSettled([
    listarPropuestas({ cookies }, { estado: 'propuesta', abiertas: true }),
    leerFallas({ cookies }),
    hoy ? leerDiaPublicado({ cookies }, hoy) : Promise.reject(new Error('sin día')),
    hoy ? leerMaterialDelDia({ cookies }, hoy) : Promise.reject(new Error('sin día')),
    leerAutonomia(locals, fetch)
  ]);
  /** @param {PromiseSettledResult<any>} r */
  const v = (r) => (r.status === 'fulfilled' ? r.value : null);

  const propuestas = v(prop);
  const valor = {
    fichas: armarPulso({
      //  `error` = no se pudo leer: null, no una bandeja vacía.
      propuestas: propuestas && !propuestas.error ? propuestas.resultados : null,
      fallas: Array.isArray(v(fallas)?.fallas) ? v(fallas).fallas : null,
      publicado: v(dia)?.error ? null : v(dia)?.publicado ?? null,
      material: v(material)?.error ? null : v(material)?.material ?? null,
      autonomia: v(autonomia)
    }),
    leido_en: new Date(ahora).toISOString()
  };
  if (org) _pulsos.set(org, { valor, en: ahora });
  return valor;
}
