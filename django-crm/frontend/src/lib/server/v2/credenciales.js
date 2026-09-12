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


/**
 * Que credenciales pertenecen a una integracion CON PANTALLA PROPIA.
 *
 * La regla de producto es: un secreto tiene UN SOLO lugar de edicion. Si la
 * integracion tiene su pantalla --donde ademas se configura el subdominio, la
 * URL del webhook, y donde esta el boton de probar conexion-- ese es el lugar
 * oficial, y el inventario solo informa el estado.
 *
 * El motivo es concreto: SmartOLT no es una clave suelta, es subdominio + clave
 * + prueba. Dejar cambiar la clave desde el inventario permite guardarla sin
 * haber probado nunca la combinacion, y que todo PAREZCA bien hasta que un
 * cliente escribe y el asistente no puede consultar la ONU.
 *
 * Este mapa vive en el frontend y no en la config del tenant a proposito: dice
 * que PANTALLAS existen en esta aplicacion, que es conocimiento del frontend.
 * Lo que varia por empresa --que credenciales hacen falta-- lo sigue diciendo
 * el catalogo del asistente. Una credencial que no este aca simplemente no
 * tiene pantalla propia y se edita desde el inventario, que es lo correcto
 * para el proximo ISP: si declara MIKROTIK_API_KEY y nadie le hizo una
 * pantalla, igual se puede cargar.
 */
const PANTALLA_PROPIA = {
  SMARTOLT_API_KEY: { integracion: 'SmartOLT', href: '/settings/canales/smartolt' },
  WHATSAPP_PHONE_NUMBER_ID: { integracion: 'WhatsApp', href: '/settings/canales/whatsapp' },
  WHATSAPP_TOKEN: { integracion: 'WhatsApp', href: '/settings/canales/whatsapp' },
  WHATSAPP_APP_SECRET: { integracion: 'WhatsApp', href: '/settings/canales/whatsapp' },
  WHATSAPP_VERIFY_TOKEN: { integracion: 'WhatsApp', href: '/settings/canales/whatsapp' },
  WHATSAPP_WABA_ID: { integracion: 'WhatsApp', href: '/settings/canales/whatsapp' }
};

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
    const credenciales = (d.credenciales ?? []).map((c) => ({
      ...c,
      ...(PANTALLA_PROPIA[c.nombre] ?? { integracion: null, href: null })
    }));
    return { credenciales, disponible: true };
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
  // Un secreto tiene un solo lugar de edicion, y eso se hace cumplir ACA y no
  // solo escondiendo el formulario: una pantalla que oculta un boton sigue
  // aceptando el POST que alguien arme a mano.
  const propia = PANTALLA_PROPIA[nombre];
  if (propia) {
    return {
      ok: false,
      error: `'${nombre}' se configura en ${propia.integracion}, que además prueba la conexión antes de guardar.`
    };
  }
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
  const propia = PANTALLA_PROPIA[nombre];
  if (propia) {
    return { ok: false, error: `'${nombre}' se administra en ${propia.integracion}.` };
  }
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
