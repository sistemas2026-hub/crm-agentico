import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { rolDeSesion } from '$lib/server/v2/operadores.js';

/**
 * Server load: lista las conversaciones del asistente con clientes finales
 * (WhatsApp real y el simulador de prueba, distinguidos por `canal`), leyendo
 * directo del motor -- mismo patron que agentes/+page.server.js. Es una
 * bandeja de solo lectura: no hay acciones que POSTear desde acá.
 *
 * POR QUE ES UN LAYOUT Y NO UN PAGE
 * La bandeja es master-detail: la columna de la izquierda acompaña siempre,
 * tambien mientras se lee una conversacion. Si esta carga viviera en el page
 * del indice, entrar a /conversaciones/<id> la desmontaria y habria que
 * volver atras para elegir la siguiente. Como layout, SvelteKit la carga una
 * sola vez y la comparte con la pantalla hija.
 *
 * depends('app:conversaciones'): +layout.svelte sondea cada pocos segundos
 * mientras la pestaña esta visible y llama a invalidate('app:conversaciones')
 * -- asi un chat nuevo (o un mensaje que actualiza el ultimo_mensaje de la
 * lista) aparece solo, sin recargar la pagina. Sin este depends(),
 * invalidate() no tendria que re-ejecutar.
 *
 * @type {import('./$types').LayoutServerLoad}
 */
export async function load({ fetch, depends, locals }) {
  depends('app:conversaciones');

  /* Quién está mirando. Sale del JWT ya verificado (`locals.user`), igual que
     en `[id]/+page.server.js` -- no es un dato nuevo ni una llamada nueva, es
     el mismo que la conversación ya usaba para decidir `esMia`. Acá lo
     necesita la barra de consola, que nombra al operador autenticado.
     `sondeadoEn` es la marca de tiempo de ESTA carga: como el layout se
     invalida cada 8s, es literalmente "cuándo se leyó la cola por última
     vez", y la barra lo muestra. */
  // 'rol' (29/10/2026): solo para mostrar el panel de carga del equipo a un
  // ADMIN. Mostrar no es autorizar: la ruta de operadores y la de reasignar
  // vuelven a mirar el rol de la sesión.
  const yo = { id: locals.user?.id ?? '', nombre: (locals.user?.name || locals.user?.email || '').trim(),
               rol: rolDeSesion(locals) };
  const sondeadoEn = new Date().toISOString();

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return {
      conversaciones: [],
      yo,
      sondeadoEn,
      error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)'
    };
  }

  try {
    /* `por_numero=1` (21/10/2026, contrato §4.5): cada fila operativa es un
       CHAT -- todas las conversaciones de un mismo número --, agrupado por el
       motor una sola vez. La pantalla no reimplementa la agrupación. */
    const resp = await fetch(
      `${baseUrl}/conversaciones?tenant=${encodeURIComponent(tenant)}&por_numero=1`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return { conversaciones: [], yo, sondeadoEn, error: datos.error || 'No se pudo cargar las conversaciones' };
    }
    /* `sla_toma_minutos` viaja con la cola: es uno solo para la empresa y el
       motor lo saca de su config (TenantConfig.sla_toma_minutos). 0 -- o
       ausente -- significa que no hay objetivo definido, y entonces la
       pantalla no dibuja ninguna cuenta regresiva. */
    return { conversaciones: datos.conversaciones, yo, sondeadoEn,
             sla_toma_minutos: datos.sla_toma_minutos ?? 0,
             /* Cómo se lee cada motivo, etiqueta y caso: uno solo para la
                empresa, como el plazo (ver lib/conversaciones/rotulos.js). */
             rotulos: datos.rotulos ?? {},
             /* Las áreas de la empresa {clave: etiqueta}, para escalar (T22) y
                para decir a cuál se escaló. */
             areas: datos.areas ?? {},
             /* Los tres numeros crudos de la salud del canal. El veredicto
                lo arma `lib/conversaciones/canal.js`, en un solo lugar. */
             canal_whatsapp: datos.canal_whatsapp ?? null };
  } catch (/** @type {any} */ err) {
    return { conversaciones: [], yo, sondeadoEn, error: err?.message || 'No se pudo contactar al asistente' };
  }
}
