import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

const ES_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TIPOS = new Set(['ejemplos', 'revisiones']);

/**
 * «Convertir en caso dorado» (12/11/2026). Proxy hacia
 * nucleo/canales/api.py:GET /manual/<ejemplos|revisiones>/<id>/caso-dorado,
 * que arma el caso desde la TRAZA guardada de la conversación, con el texto
 * del cliente redactado por patrón (nucleo/habilidades/casos_dorados.py).
 *
 * Producción no puede escribir el repositorio: el caso se muestra para
 * copiarlo o descargarlo, y `cli/importar_casos_dorados.py` trae todos los
 * marcados sin duplicar.
 *
 * ADMIN, como resolver una revisión: decidir qué entra a la evaluación es
 * decidir con qué se mide al agente. Y el YAML trae lo que escribió un
 * cliente, aunque redactado. El control vive acá, no en esconder el botón.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede generar un caso dorado.' }, { status: 403 });
  }
  const tipo = url.searchParams.get('tipo') ?? '';
  const id = url.searchParams.get('id') ?? '';
  // El id y el tipo viajan en la RUTA del motor: un valor libre cambiaría a
  // qué endpoint se le pega.
  if (!TIPOS.has(tipo) || !ES_UUID.test(id)) {
    return json({ error: 'Origen inválido.' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado' }, { status: 500 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/manual/${tipo}/${id}/caso-dorado?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    );
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo armar el caso dorado.' },
        { status: resp.status });
    }
    return json({
      caso_dorado: datos.caso_dorado,
      avisos: datos.avisos ?? [],
      origen: datos.origen ?? null
    });
  } catch (/** @type {any} */ err) {
    console.error('[manual] motor inalcanzable:', err?.name ?? 'error');
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
