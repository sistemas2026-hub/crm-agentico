/**
 * Las variables de la empresa (12/11/2026): datos que cambian de un ISP a otro
 * y NO son secretos — un subdominio, un ID de cuenta, un link —. Viven en
 * `variables_tenant` de la configuración y las herramientas las nombran por
 * `base_url_ref`, `argumentos_desde_variables` o `entrega_variable`.
 *
 * El motor ya tenía `GET/PUT/DELETE /configuracion/variables`; la única
 * pantalla que los usaba era la de SmartOLT y la de Pagos, cada una para su
 * variable. Una `base_url_ref` nueva —la que trae un conector— no tenía dónde
 * cargarse sin una sesión de código (CLAUDE.md §3.3; auditoría del menú §2).
 *
 * Server-only. La empresa sale de la sesión. `leer` no lanza; `guardar` y
 * `borrar` sí, con el motivo del motor (que ya rechaza un valor con pinta de
 * credencial: eso va en Credenciales, cifrado).
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/** El mismo patrón que el motor (`schema.RE_NOMBRE_REF`). */
export const NOMBRE_VARIABLE = /^[A-Z][A-Z0-9_]{2,}$/;
/** Tope de la pantalla: un dato de empresa, no un documento. */
export const VALOR_MAXIMO = 2000;

/**
 * Lo que se va a guardar, o el motivo por el que no. Se valida acá para que el
 * error llegue en el idioma de quien escribe antes de ir al motor; el motor
 * vuelve a validar (la garantía es suya).
 * @param {string} nombreCrudo
 * @param {string} valorCrudo
 * @returns {{ ok: true, nombre: string, valor: string } | { ok: false, error: string }}
 */
export function validarVariable(nombreCrudo, valorCrudo) {
  const nombre = (nombreCrudo ?? '').trim().toUpperCase();
  const valor = (valorCrudo ?? '').trim();
  if (!NOMBRE_VARIABLE.test(nombre)) {
    return {
      ok: false,
      error: 'El nombre va en MAYÚSCULAS, empieza con letra y usa letras, números y guion bajo (por ejemplo SMARTOLT_SUBDOMINIO).'
    };
  }
  if (!valor) return { ok: false, error: 'Falta el valor. Para quitar una variable, usá «Quitar».' };
  if (valor.length > VALOR_MAXIMO) {
    return { ok: false, error: `El valor pasa de ${VALOR_MAXIMO} caracteres.` };
  }
  return { ok: true, nombre, valor };
}

/**
 * Las variables, con quién usa cada una y cuáles se piden y faltan, o `null`
 * si no hay asistente o no contesta.
 * @returns {Promise<{ variables: Record<string, string>, usos: Record<string, string[]>, faltan: Record<string, string[]> } | null>}
 */
export async function leerVariables(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/variables?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    const d = await resp.json();
    return { variables: d.variables ?? {}, usos: d.usos ?? {}, faltan: d.faltan ?? {} };
  } catch {
    return null;
  }
}

/** @param {string} nombre @param {string} valor */
export async function guardarVariable(locals, fetch, nombre, valor) {
  const v = validarVariable(nombre, valor);
  if (v.ok === false) throw new Error(v.error);
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('El asistente no está configurado para esta empresa.');
  const resp = await fetch(`${cfg.baseUrl}/configuracion/variables/${encodeURIComponent(v.nombre)}`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, valor: v.valor })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'El asistente rechazó el cambio.');
  return datos;
}

/** @param {string} nombre */
export async function borrarVariable(locals, fetch, nombre) {
  if (!NOMBRE_VARIABLE.test(nombre ?? '')) throw new Error('¿Qué variable?');
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('El asistente no está configurado para esta empresa.');
  const resp = await fetch(
    `${cfg.baseUrl}/configuracion/variables/${encodeURIComponent(nombre)}?tenant=${encodeURIComponent(cfg.tenant)}`,
    { method: 'DELETE', headers: headersMotor() }
  );
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'El asistente rechazó el cambio.');
  return datos;
}
