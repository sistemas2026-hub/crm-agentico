import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Server load: dos listas, las dos opcionales.
 *
 *   casos    (tenant_config.manual.casos) para marcar una respuesta como
 *            buen ejemplo -- ver MarcarEjemplo.svelte.
 *   agentes  para poder elegir a CUAL hablarle (02/11/2026). Hasta ese dia
 *            el simulador fijaba 'cliente_final' en su proxy, asi que un
 *            agente recien creado desde /agentes no se podia probar desde
 *            ninguna pantalla: habia que asignarselo al propio perfil.
 *
 * El resto de esta pagina es puramente client-side (habla con
 * /api/simulador-whatsapp por su cuenta) -- mismo criterio que /agentes: si
 * esto falla, el simulador sigue funcionando con menos opciones.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) return { casos: [] };

  //  Los dos en paralelo y cada uno con su propio fallo: si la lista de
  //  agentes no viene, el simulador sigue hablandole a 'cliente_final' como
  //  siempre, y si no vienen los casos, el boton de marcar no tiene opciones.
  //  Ninguna de las dos puede dejar la pantalla sin simulador.
  const [casos, agentes] = await Promise.all([
    fetch(`${baseUrl}/manual/casos?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.casos ?? [])
      .catch(() => []),
    fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() })
      .then((r) => (r.ok ? r.json() : null))
      //  Solo lo que hace falta para elegir: el nombre y como llamarlo en
      //  pantalla. Las herramientas y el prompt de cada agente no tienen por
      //  que viajar a una pantalla que solo quiere un <select>.
      .then((d) => (d?.agentes ?? []).map((/** @type {any} */ a) => ({
        nombre: a.nombre,
        area: a.area ?? '',
        cargo: a.cargo ?? '',
        orientado_a: a.orientado_a ?? ''
      })))
      .catch(() => [])
  ]);

  return { casos, agentes };
}
