/**
 * El link con el que un cliente puede pagar.
 *
 * Server-only, mismo puente que `bandeja-config.js`: habla con el motor, y la
 * empresa sale de la sesión -- nunca del cliente.
 *
 * POR QUE ES UNA VARIABLE DE LA EMPRESA
 * -------------------------------------
 * El link de pago cambia de una empresa a otra, así que no vive en el código ni
 * en el prompt de un agente: es `LINK_DE_PAGO` en `variables_tenant`, el mismo
 * lugar donde viven los demás datos que varían por empresa. La herramienta
 * `consultar_mi_cuenta` sabe de qué variable leerlo (`cuenta.link_de_pago` en su
 * configuración) y se lo entrega al asistente solo a un cliente verificado y
 * con algo que pagar.
 *
 * POR QUE SE VALIDA ACA Y TAMBIEN EN EL MOTOR
 * -------------------------------------------
 * El motor no le da al cliente un valor que no sea una dirección https limpia
 * (`nucleo/herramientas/cuenta.py::link_de_pago`): esa es la garantía. Esta
 * validación es el aviso a quien lo escribe -- sin ella, un link mal pegado se
 * guarda sin error y el asistente simplemente nunca lo ofrece, y nadie se
 * entera. Las dos reglas son la misma a propósito.
 *
 * POR QUE `leer` NO LANZA
 * -----------------------
 * Mismo motivo que `bandeja-config.js`: el asistente es otro servicio y la
 * pantalla tiene que poder decir "no contesta" en vez de caerse. `guardar` sí
 * lanza: ahí alguien apretó un botón y tiene que enterarse.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/** El nombre de la variable de la empresa. Lo declara `cuenta.link_de_pago` en
 *  la herramienta `consultar_mi_cuenta`; los dos tienen que decir lo mismo. */
export const VARIABLE_LINK_DE_PAGO = 'LINK_DE_PAGO';

/** Mismo tope que el motor (`LARGO_MAXIMO_DEL_LINK`). */
export const LARGO_MAXIMO_DEL_LINK = 500;

/**
 * Una dirección https limpia, o el motivo por el que no lo es. Vacío es válido
 * y significa "quitar el link".
 * @param {string} crudo
 * @returns {{ ok: true, link: string } | { ok: false, error: string }}
 */
export function validarLinkDePago(crudo) {
  const link = (crudo ?? '').trim();
  if (link === '') return { ok: true, link: '' };
  if (link.length > LARGO_MAXIMO_DEL_LINK) {
    return { ok: false, error: `El link es demasiado largo (máximo ${LARGO_MAXIMO_DEL_LINK} caracteres).` };
  }
  if (/\s/.test(link)) {
    return { ok: false, error: 'El link no puede tener espacios.' };
  }
  /** @type {URL} */
  let url;
  try {
    url = new URL(link);
  } catch {
    return { ok: false, error: 'Eso no es una dirección completa. Tiene que empezar con https://' };
  }
  if (url.protocol !== 'https:') {
    return { ok: false, error: 'El link tiene que empezar con https:// (por seguridad no se aceptan otros).' };
  }
  if (!url.hostname) {
    return { ok: false, error: 'Al link le falta el sitio (por ejemplo https://pagos.miempresa.co).' };
  }
  if (url.username || url.password) {
    return { ok: false, error: 'El link no puede llevar usuario ni clave incrustados.' };
  }
  return { ok: true, link };
}

/**
 * El link cargado (`''` si no hay), o `null` si no hay asistente o no contesta.
 * @returns {Promise<{ link: string } | null>}
 */
export async function leerLinkDePago(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/variables?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    const datos = await resp.json();
    const valor = datos?.variables?.[VARIABLE_LINK_DE_PAGO];
    return { link: typeof valor === 'string' ? valor : '' };
  } catch {
    return null;
  }
}

/**
 * Guarda el link, o lo quita si viene vacío. Valida antes de salir: lo que no
 * es https limpio no llega al motor.
 * @param {string} crudo
 */
export async function guardarLinkDePago(locals, fetch, crudo) {
  const v = validarLinkDePago(crudo);
  if (!v.ok) throw new Error(v.error);

  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) {
    throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  }

  const nombre = encodeURIComponent(VARIABLE_LINK_DE_PAGO);
  const resp =
    v.link === ''
      ? await fetch(`${cfg.baseUrl}/configuracion/variables/${nombre}?tenant=${encodeURIComponent(cfg.tenant)}`, {
          method: 'DELETE',
          headers: headersMotor()
        })
      : await fetch(`${cfg.baseUrl}/configuracion/variables/${nombre}`, {
          method: 'PUT',
          headers: headersMotor({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ tenant: cfg.tenant, valor: v.link })
        });

  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(datos.error || 'El asistente rechazó el cambio.');
  }
  return datos;
}
