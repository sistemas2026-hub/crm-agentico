/**
 * Los textos del traspaso a una persona y el cierre por inactividad
 * (12/11/2026).
 *
 * Server-only, mismo puente que `bandeja-config.js`: habla con el motor y la
 * empresa sale de la sesión, nunca del navegador. Hasta este día estos datos
 * solo se cambiaban por YAML (CLAUDE.md §3.3; auditoría del menú, §2).
 *
 * LAS CLAVES VIAJAN TODAS, SIEMPRE. El motor rechaza un PUT al que le falta
 * una: «no vino» y «borralo» no son lo mismo. Por eso `armarTextos` y
 * `armarCierre` construyen el cuerpo completo desde el formulario y nunca
 * dejan una clave afuera; un campo vacío viaja vacío.
 *
 * `leer` no lanza (la pantalla dice «no contesta»); `guardar*` sí: alguien
 * apretó un botón y tiene que enterarse del motivo, que el motor ya escribe
 * en español.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/** Las cinco claves que el motor exige (editor.CLAVES_TEXTOS_TRASPASO). */
export const CLAVES_TEXTOS = [
  'mensaje',
  'mensajes_por_motivo',
  'mensaje_ya_escalada',
  'mensaje_si_falla',
  'frases_de_traspaso'
];

/**
 * @returns {Promise<{ textos: any, motivos: string[], cierre: any, sin_gestion_horas: number | null } | null>}
 */
export async function leerTraspaso(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/traspaso?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * El cuerpo de los textos, desde el formulario. Un motivo viaja como
 * `motivo:<clave>`; las frases, una por línea. Qué motivos existen lo vuelve
 * a validar el motor contra `activar_si`: uno inventado en el formulario se
 * rechaza allá, con su nombre.
 * @param {FormData} form
 */
export function armarTextos(form) {
  /** @type {Record<string, string>} */
  const porMotivo = {};
  for (const [clave, valor] of form.entries()) {
    if (clave.startsWith('motivo:')) porMotivo[clave.slice(7)] = valor.toString().trim();
  }
  return {
    mensaje: (form.get('mensaje')?.toString() ?? '').trim(),
    mensajes_por_motivo: porMotivo,
    mensaje_ya_escalada: (form.get('mensaje_ya_escalada')?.toString() ?? '').trim(),
    mensaje_si_falla: (form.get('mensaje_si_falla')?.toString() ?? '').trim(),
    frases_de_traspaso: (form.get('frases_de_traspaso')?.toString() ?? '')
      .split('\n')
      .map((f) => f.trim())
      .filter(Boolean)
  };
}

/**
 * El cuerpo del cierre, desde el formulario. Vacío en horas = `null` (no se
 * cierra por tiempo). Lo que no es un entero vuelve como error, no como 0.
 * @param {FormData} form
 * @returns {{ ok: true, cierre: any } | { ok: false, error: string }}
 */
export function armarCierre(form) {
  const crudoHoras = form.get('horas_inactividad_cierra')?.toString().trim() ?? '';
  const horas = crudoHoras === '' ? null : Number(crudoHoras);
  if (horas !== null && (!Number.isInteger(horas) || horas < 1)) {
    return { ok: false, error: 'Las horas tienen que ser un número entero mayor que cero, o quedar vacías.' };
  }
  const crudoLote = form.get('backfill_lote')?.toString().trim() ?? '';
  const lote = Number(crudoLote || '10');
  if (!Number.isInteger(lote) || lote < 1) {
    return { ok: false, error: 'El lote tiene que ser un número entero mayor que cero.' };
  }
  return {
    ok: true,
    cierre: {
      habilitado: form.get('habilitado') === 'on',
      horas_inactividad_cierra: horas,
      backfill_habilitado: form.get('backfill_habilitado') === 'on',
      backfill_lote: lote
    }
  };
}

/** @param {string} ruta @param {any} cuerpo */
async function enviar(locals, fetch, ruta, cuerpo) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('El asistente no está configurado para esta empresa.');
  const resp = await fetch(`${cfg.baseUrl}${ruta}`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, ...cuerpo })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'El asistente rechazó el cambio.');
  return datos;
}

/** @param {Record<string, any>} textos */
export async function guardarTextosTraspaso(locals, fetch, textos) {
  const faltan = CLAVES_TEXTOS.filter((c) => !(c in textos));
  if (faltan.length) throw new Error(`Faltan ${faltan.join(', ')}.`);
  return enviar(locals, fetch, '/configuracion/traspaso/textos', textos);
}

/** @param {{ habilitado: boolean, horas_inactividad_cierra: number|null, backfill_habilitado: boolean, backfill_lote: number }} cierre */
export async function guardarCierreInactividad(locals, fetch, cierre) {
  return enviar(locals, fetch, '/configuracion/traspaso/cierre', cierre);
}
