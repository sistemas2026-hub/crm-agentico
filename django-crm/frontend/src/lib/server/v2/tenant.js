import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * De qué empresa son los datos que puede pedir quien inició sesión.
 *
 * EL ÚNICO LUGAR donde se decide eso. Hasta el 24/09/2026 la respuesta salía
 * de `PRIVATE_ASISTENTE_TENANT` en 70 archivos distintos, o sea que la
 * instalación entera servía a una sola empresa: con dos, cada una de esas
 * lecturas le habría servido a un ISP los datos del otro (PRD §8.13).
 *
 * Que se lea en un solo lugar no es prolijidad. El esquema del formulario de
 * Campo ya enseñó qué pasa cuando el mismo dato se interpreta en varios
 * archivos: cinco defectos distintos, y ninguna lectura estaba mal escrita —el
 * problema era que existieran varias—.
 *
 * NO HAY DEFAULT, y esa es la mitad del valor. Si no se sabe qué empresa es,
 * la respuesta es `null` y la pantalla se queda sin datos. Servir «el tenant
 * de siempre» ante la duda es exactamente la fuga que el aislamiento por
 * organización existe para impedir, y además silenciosa: nadie se entera de
 * que está mirando lo que no le corresponde.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @returns {Promise<string|null>}
 */
export async function tenantDeLaSesion(locals, fetch) {
  // Ya resuelto en este request.
  if (locals?.tenant) return locals.tenant;

  const orgId = locals?.org?.id;
  if (!orgId) return null;

  const base = env.PRIVATE_ASISTENTE_URL;
  if (!base) return null;

  // UNA SOLA PREGUNTA AL MOTOR POR REQUEST  --  04/11/2026
  // ------------------------------------------------------
  // El comentario de arriba decía que `hooks.server.js` dejaba el tenant en
  // `locals`; no lo hace (medido: cero referencias). Y el hub de Configuración
  // dispara nueve lecturas del motor EN PARALELO, cada una pasando por acá
  // antes de que la primera haya escrito `locals.tenant`: nueve veces la misma
  // pregunta, contra un motor de 8 hilos que además atiende los turnos de
  // WhatsApp. "Configuración demora o no muestra nada" (reportado dos veces,
  // 01/11 y 04/11). Las que llegan mientras la primera está en vuelo comparten
  // su promesa, en vez de abrir otra.
  if (locals && locals._tenantEnVuelo) return locals._tenantEnVuelo;

  // Y CON PLAZO. Sin él, cada tarjeta del hub tenía 4 s para el motor pero la
  // pregunta previa por el tenant no tenía ninguno: un motor ocupado dejaba
  // todo detrás de esta llamada, y el plazo de la tarjeta nunca corría.
  // Un AbortController propio y no `AbortSignal.timeout`: este obedece al
  // reloj del proceso (lo que permite probarlo con temporizadores falsos) y se
  // limpia al terminar, en vez de quedar un temporizador vivo por request.
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), PLAZO_TENANT_MS);
  const pregunta = (async () => {
    try {
      const r = await fetch(
        `${base}/tenant-de-organizacion/${encodeURIComponent(orgId)}`,
        { headers: headersMotor(), signal: control.signal }
      );
      // 404 es una respuesta legítima: esa empresa no tiene asistente todavía.
      // No es un error que haya que reintentar ni registrar como falla.
      if (!r.ok) return null;
      const datos = await r.json();
      const slug = datos?.tenant;
      if (!slug) return null;
      if (locals) locals.tenant = slug;
      return slug;
    } catch {
      // El motor caído o lento no puede convertirse en «servile los datos de
      // otra empresa». Sin respuesta no hay tenant.
      return null;
    } finally {
      clearTimeout(reloj);
      if (locals) delete locals._tenantEnVuelo;
    }
  })();
  if (locals) locals._tenantEnVuelo = pregunta;
  return pregunta;
}

/** Cuánto se espera al motor por el tenant. Una tarjeta del hub tiene 4 s
 *  (settings.js::PLAZO_MOTOR_MS): esto va DENTRO de ese presupuesto. */
export const PLAZO_TENANT_MS = 3000;

/**
 * A qué motor hablarle y de qué empresa son los datos, en una sola llamada.
 *
 * Reemplaza a **ocho copias byte a byte** de una función `destino()` que vivía
 * repetida en `asistente-config`, `bandeja-config`, `canal-whatsapp`,
 * `credenciales`, `guias-tv`, `oferta`, `planes-venta` y `smartolt`. Ocho
 * lecturas del mismo dato: exactamente la forma de defecto que el esquema del
 * formulario de Campo ya enseñó a reconocer —cinco síntomas distintos, ninguna
 * lectura mal escrita, el problema era que existieran varias—.
 *
 * Devuelve `null` si falta cualquiera de las dos cosas, y quien llama ya sabe
 * qué hacer con eso: todas las copias que reemplaza terminaban en
 * `if (!d) return ...`, así que el camino de la ausencia ya estaba escrito.
 * **No hay default**: sin saber de qué empresa es, no se pide nada.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @returns {Promise<{ baseUrl: string, tenant: string } | null>}
 */
export async function destinoDelAsistente(locals, fetch) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  if (!baseUrl) return null;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!tenant) return null;
  return { baseUrl, tenant };
}
