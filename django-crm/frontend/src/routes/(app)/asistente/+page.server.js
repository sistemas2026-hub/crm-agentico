import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { leerConPlazo } from '$lib/server/v2/plazo.js';

/** Cuánto se espera al motor para preparar la pantalla. Lo que no llega se
 *  queda sin su opción; la pantalla no se retiene por eso. */
export const PLAZO_ASISTENTE_MS = 4000;

/**
 * Lo que la pantalla necesita saber ANTES de que alguien escriba:
 *
 *   estado        si hay con quién hablar (12/11/2026). Hasta hoy la página
 *                 cargaba vacía igual con el motor caído o sin asistente, y la
 *                 persona se enteraba al escribir el primer mensaje. Ahora:
 *                   'listo'          el motor contestó
 *                   'sin_instalacion' no hay asistente desplegado acá
 *                   'sin_empresa'    no se pudo confirmar el asistente de
 *                                    esta empresa (no tiene uno, o el motor no
 *                                    contestó la pregunta de qué empresa es:
 *                                    `tenantDeLaSesion` no distingue, y la
 *                                    pantalla no inventa cuál de las dos)
 *                   'sin_respuesta'  se sabe la empresa y el motor no contestó
 *                 Nunca nombra una variable de entorno: a quien escribe no le
 *                 sirve (mismo criterio que /api/asistente).
 *   agentes       para poder elegir a cuál hablarle. Solo ADMIN: el proxy
 *                 rechaza el `rol` de cualquier otro.
 *   puedeElegir   si esta persona es ADMIN. Se decide ACÁ y no en el
 *                 navegador: un `if` en el cliente es una sugerencia.
 *   fotoHabilitada  si esta empresa habilitó mirar las fotos que adjunta un
 *                 colaborador.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  const vacio = { agentes: [], puedeElegir: false, fotoHabilitada: false };
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  if (!baseUrl) return { ...vacio, estado: 'sin_instalacion' };
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!tenant) return { ...vacio, estado: 'sin_empresa' };

  const puedeElegir = locals.profile?.role === 'ADMIN';
  const t = encodeURIComponent(tenant);

  const [agentes, vision] = await Promise.all([
    puedeElegir
      ? leerConPlazo(fetch, `${baseUrl}/agentes?tenant=${t}`, { headers: headersMotor() }, PLAZO_ASISTENTE_MS)
      : Promise.resolve(null),
    leerConPlazo(
      fetch,
      `${baseUrl}/interno/vision/evidencias-habilitada?tenant=${t}&proposito=asistente_interno`,
      { headers: headersMotor() },
      PLAZO_ASISTENTE_MS
    )
  ]);

  // `null` es «no contestó» (caído o fuera de plazo). Una respuesta con error
  // (un 404 de un motor viejo) SÍ es una respuesta: el motor está.
  const estado = vision === null ? 'sin_respuesta' : 'listo';

  return {
    agentes: agentes?.ok
      ? (agentes.cuerpo?.agentes ?? []).map((/** @type {any} */ a) => ({
          nombre: a.nombre,
          area: a.area ?? '',
          cargo: a.cargo ?? ''
        }))
      : [],
    puedeElegir,
    fotoHabilitada: vision?.ok === true && vision.cuerpo?.habilitada === true,
    estado
  };
}
