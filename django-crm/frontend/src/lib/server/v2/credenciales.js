/**
 * Las credenciales que esta empresa necesita, y cuáles ya están cargadas.
 *
 * La lista no está escrita acá: la arma el motor leyendo los `auth_ref` que
 * declara el catálogo de herramientas del tenant. Por eso la pantalla sirve
 * para el ISP número dos sin que nadie toque código — si su configuración
 * declara `OTRO_PROVEEDOR_API_KEY`, aparece sola.
 *
 * Nunca viaja un valor: el motor devuelve nombre, para qué sirve, cuándo se
 * cargó y una pista de los últimos caracteres. Guardar va en un solo sentido.
 */
import { env } from '$env/dynamic/private';
import { headersMotor } from './motor-headers.js';

function destino() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/** @returns {Promise<{ credenciales: any[], disponible: boolean }>} */
export async function leerCredenciales() {
  const cfg = destino();
  if (!cfg) return { credenciales: [], disponible: false };
  try {
    const r = await fetch(
      `${cfg.baseUrl}/configuracion/credenciales?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) return { credenciales: [], disponible: false };
    const d = await r.json();
    return { credenciales: d.credenciales ?? [], disponible: true };
  } catch {
    // Que el asistente no responda no puede dejar la pantalla rota: se avisa
    // y se muestra vacía, igual que hace la cola de tickets con las áreas.
    return { credenciales: [], disponible: false };
  }
}

/** @returns {Promise<{ ok: boolean, error?: string }>} */
export async function guardarCredencial(nombre, valor, descripcion) {
  const cfg = destino();
  if (!cfg) return { ok: false, error: 'El asistente no está configurado.' };
  try {
    const r = await fetch(`${cfg.baseUrl}/secretos`, {
      method: 'POST',
      headers: { ...headersMotor(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenant: cfg.tenant, nombre, valor, descripcion })
    });
    if (r.ok) return { ok: true };
    const d = await r.json().catch(() => ({}));
    return { ok: false, error: d.error ?? `El asistente respondió ${r.status}.` };
  } catch (e) {
    return { ok: false, error: 'No se pudo hablar con el asistente.' };
  }
}

/** @returns {Promise<{ ok: boolean, error?: string }>} */
export async function borrarCredencial(nombre) {
  const cfg = destino();
  if (!cfg) return { ok: false, error: 'El asistente no está configurado.' };
  try {
    const r = await fetch(
      `${cfg.baseUrl}/secretos/${encodeURIComponent(nombre)}`,
      {
        method: 'DELETE',
        headers: { ...headersMotor(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant: cfg.tenant })
      }
    );
    if (r.ok) return { ok: true };
    return { ok: false, error: `El asistente respondió ${r.status}.` };
  } catch {
    return { ok: false, error: 'No se pudo hablar con el asistente.' };
  }
}
