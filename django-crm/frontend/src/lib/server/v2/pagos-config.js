/**
 * Lo que un cliente puede usar para pagar: el link y los otros medios.
 *
 * Server-only, mismo puente que `bandeja-config.js`: habla con el motor, y la
 * empresa sale de la sesión -- nunca del cliente.
 *
 * POR QUE SON VARIABLES DE LA EMPRESA
 * -----------------------------------
 * Esto cambia de una empresa a otra, así que no vive en el código ni en el
 * prompt de un agente: son `LINK_DE_PAGO` y `MEDIOS_DE_PAGO` en
 * `variables_tenant`, el mismo lugar donde viven los demás datos que varían por
 * empresa. La herramienta `consultar_mi_cuenta` sabe de qué variable leer cada
 * uno (`cuenta.link_de_pago` y `cuenta.medios_de_pago` en su configuración) y se
 * los entrega al asistente solo a un cliente verificado y con algo que pagar.
 *
 * LOS OTROS MEDIOS: UN TEXTO, NO UN DATO POR CLIENTE
 * --------------------------------------------------
 * Un punto físico (Efecty con su convenio) identifica a la persona por su
 * cédula: el cliente la dice en caja, y ya la sabe. Por eso cada medio es un
 * texto fijo que escribe la empresa ("Convenio 12345, di tu cédula en caja") y
 * el motor no incrusta ningún dato del cliente. Se guarda como una lista JSON de
 * `{ nombre, instruccion }` en UNA variable.
 *
 * POR QUE SE VALIDA ACA Y TAMBIEN EN EL MOTOR
 * -------------------------------------------
 * El motor no entrega lo que no cumple las reglas
 * (`nucleo/herramientas/cuenta.py::link_de_pago` y `::medios_de_pago`): esa es
 * la garantía, y lo que no las cumple se descarta ENTERO (recortar un texto
 * podría cortar un número de convenio y dar un dato falso). Esta validación es
 * el aviso a quien lo escribe -- sin ella, un medio pasado del tope se guarda
 * sin error y el asistente simplemente nunca lo ofrece, y nadie se entera. Las
 * reglas son las mismas a propósito.
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

/** Idem para `cuenta.medios_de_pago`. */
export const VARIABLE_MEDIOS_DE_PAGO = 'MEDIOS_DE_PAGO';

/** Mismo tope que el motor (`LARGO_MAXIMO_DEL_LINK`). */
export const LARGO_MAXIMO_DEL_LINK = 500;

/** Mismos topes que el motor (`MAXIMO_MEDIOS_DE_PAGO`, `LARGO_MAXIMO_DEL_MEDIO`,
 *  `LARGO_MAXIMO_DE_LA_INSTRUCCION`). */
export const MAXIMO_MEDIOS_DE_PAGO = 10;
export const LARGO_MAXIMO_DEL_MEDIO = 60;
export const LARGO_MAXIMO_DE_LA_INSTRUCCION = 300;

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
 * Un texto de una sola línea: los caracteres de control y los saltos pasan a ser
 * espacios y los espacios se juntan. Igual que el motor (`_limpio`).
 * @param {unknown} valor
 */
function aplanar(valor) {
  if (typeof valor !== 'string') return '';
  // eslint-disable-next-line no-control-regex
  return valor.replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ').split(/\s+/).filter(Boolean).join(' ');
}

/**
 * Las filas que escribió la persona, listas para guardar, o el motivo por el que
 * no se puede. Una fila vacía por completo se ignora (es la que quedó al apretar
 * "Agregar"); una a medias es un error con su número, no algo que se descarte
 * callado. Una lista vacía es válida y significa "quitar todos".
 * @param {Array<{ nombre?: unknown, instruccion?: unknown }>} filas
 * @returns {{ ok: true, medios: Array<{ nombre: string, instruccion: string }> } | { ok: false, error: string }}
 */
export function validarMediosDePago(filas) {
  /** @type {Array<{ nombre: string, instruccion: string }>} */
  const medios = [];
  for (const [i, fila] of (filas ?? []).entries()) {
    const nombre = aplanar(fila?.nombre);
    const instruccion = aplanar(fila?.instruccion);
    if (!nombre && !instruccion) continue;
    const n = i + 1;
    if (!nombre) return { ok: false, error: `Al medio ${n} le falta el nombre (por ejemplo "Efecty").` };
    if (!instruccion) {
      return { ok: false, error: `Al medio "${nombre}" le falta decir cómo se paga (por ejemplo el convenio).` };
    }
    if (nombre.length > LARGO_MAXIMO_DEL_MEDIO) {
      return { ok: false, error: `El nombre "${nombre.slice(0, 20)}…" pasa de ${LARGO_MAXIMO_DEL_MEDIO} caracteres.` };
    }
    if (instruccion.length > LARGO_MAXIMO_DE_LA_INSTRUCCION) {
      return {
        ok: false,
        error: `Lo que dice "${nombre}" pasa de ${LARGO_MAXIMO_DE_LA_INSTRUCCION} caracteres. Acortalo: no se recorta solo, porque podría cortar un número.`
      };
    }
    medios.push({ nombre, instruccion });
  }
  if (medios.length > MAXIMO_MEDIOS_DE_PAGO) {
    return { ok: false, error: `Hay más de ${MAXIMO_MEDIOS_DE_PAGO} medios. El asistente no ofrece más que eso.` };
  }
  return { ok: true, medios };
}

/**
 * Lo guardado en la variable, leído con las mismas reglas que el motor. Lo que
 * el motor descartaría no se muestra como si estuviera vigente.
 * @param {unknown} crudo
 * @returns {{ medios: Array<{ nombre: string, instruccion: string }>, ilegible: boolean }}
 */
export function leerMediosGuardados(crudo) {
  if (typeof crudo !== 'string' || crudo.trim() === '') return { medios: [], ilegible: false };
  /** @type {unknown} */
  let lista;
  try {
    lista = JSON.parse(crudo);
  } catch {
    return { medios: [], ilegible: true };
  }
  if (!Array.isArray(lista)) return { medios: [], ilegible: true };
  /** @type {Array<{ nombre: string, instruccion: string }>} */
  const medios = [];
  for (const e of lista) {
    const nombre = aplanar(e?.nombre);
    const instruccion = aplanar(e?.instruccion);
    if (!nombre || !instruccion) continue;
    if (nombre.length > LARGO_MAXIMO_DEL_MEDIO || instruccion.length > LARGO_MAXIMO_DE_LA_INSTRUCCION) continue;
    medios.push({ nombre, instruccion });
    if (medios.length >= MAXIMO_MEDIOS_DE_PAGO) break;
  }
  return { medios, ilegible: false };
}

/**
 * Lo cargado (link `''` y lista vacía si no hay), o `null` si no hay asistente o
 * no contesta. Una sola lectura al motor trae las dos cosas.
 * @returns {Promise<{ link: string, medios: Array<{ nombre: string, instruccion: string }>, medios_ilegibles: boolean } | null>}
 */
export async function leerAjustesDePago(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/variables?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    const datos = await resp.json();
    const link = datos?.variables?.[VARIABLE_LINK_DE_PAGO];
    const { medios, ilegible } = leerMediosGuardados(datos?.variables?.[VARIABLE_MEDIOS_DE_PAGO]);
    return {
      link: typeof link === 'string' ? link : '',
      medios,
      medios_ilegibles: ilegible
    };
  } catch {
    return null;
  }
}

/**
 * Guarda una variable de la empresa, o la quita si el valor viene vacío (el
 * motor no acepta guardar un valor vacío).
 * @param {string} nombreVariable
 * @param {string} valor
 */
async function escribirVariable(locals, fetch, nombreVariable, valor) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) {
    throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  }

  const nombre = encodeURIComponent(nombreVariable);
  const resp =
    valor === ''
      ? await fetch(`${cfg.baseUrl}/configuracion/variables/${nombre}?tenant=${encodeURIComponent(cfg.tenant)}`, {
          method: 'DELETE',
          headers: headersMotor()
        })
      : await fetch(`${cfg.baseUrl}/configuracion/variables/${nombre}`, {
          method: 'PUT',
          headers: headersMotor({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ tenant: cfg.tenant, valor })
        });

  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(datos.error || 'El asistente rechazó el cambio.');
  }
  return datos;
}

/**
 * Guarda el link, o lo quita si viene vacío. Valida antes de salir: lo que no
 * es https limpio no llega al motor.
 * @param {string} crudo
 */
export async function guardarLinkDePago(locals, fetch, crudo) {
  const v = validarLinkDePago(crudo);
  if (v.ok === false) throw new Error(v.error);
  return escribirVariable(locals, fetch, VARIABLE_LINK_DE_PAGO, v.link);
}

/**
 * Guarda los otros medios de pago, o los quita todos si no queda ninguno.
 * Valida antes de salir: lo que el motor descartaría no llega.
 * @param {Array<{ nombre?: unknown, instruccion?: unknown }>} filas
 */
export async function guardarMediosDePago(locals, fetch, filas) {
  const v = validarMediosDePago(filas);
  if (v.ok === false) throw new Error(v.error);
  return escribirVariable(
    locals,
    fetch,
    VARIABLE_MEDIOS_DE_PAGO,
    v.medios.length === 0 ? '' : JSON.stringify(v.medios)
  );
}
