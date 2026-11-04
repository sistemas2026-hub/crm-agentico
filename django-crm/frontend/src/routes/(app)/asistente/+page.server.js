import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Lo que la pantalla necesita saber ANTES de que alguien escriba, y todo
 * opcional: si algo de esto falla, el asistente sigue funcionando como
 * siempre, con menos opciones. Mismo criterio que /agentes y el simulador.
 *
 *   agentes       para poder elegir a cuál hablarle. Solo tiene sentido para
 *                 un ADMIN: el proxy rechaza el `rol` de cualquier otro, así
 *                 que a quien no lo es ni se le muestra el selector.
 *   puedeElegir   si esta persona es ADMIN. Se decide ACÁ y no en el
 *                 navegador: un `if` en el cliente es una sugerencia.
 *   fotoHabilitada  si esta empresa tiene habilitado que se miren las fotos
 *                 que un colaborador adjunta. Apagado = no se muestra el
 *                 botón de adjuntar, en vez de ofrecerlo y fallar después.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  const vacio = { agentes: [], puedeElegir: false, fotoHabilitada: false };
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) return vacio;

  const puedeElegir = locals.profile?.role === 'ADMIN';

  const [agentes, fotoHabilitada] = await Promise.all([
    puedeElegir
      ? fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`, {
          headers: headersMotor()
        })
          .then((r) => (r.ok ? r.json() : null))
          .then((d) =>
            (d?.agentes ?? []).map((/** @type {any} */ a) => ({
              nombre: a.nombre,
              area: a.area ?? '',
              cargo: a.cargo ?? ''
            }))
          )
          .catch(() => [])
      : Promise.resolve([]),
    fetch(
      `${baseUrl}/interno/vision/evidencias-habilitada?tenant=${encodeURIComponent(
        tenant
      )}&proposito=asistente_interno`,
      { headers: headersMotor() }
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.habilitada === true)
      .catch(() => false)
  ]);

  return { agentes, puedeElegir, fotoHabilitada };
}
