/**
 * Los rangos de IP de cada servidor (25/11/2026).
 *
 * Son los /24 de donde se le ofrecen direcciones al técnico en el contrato, y
 * los que el alta comprueba antes de crear un cliente: sin rangos, el técnico
 * no ve ninguna IP libre y el alta se niega. Son una decisión de la empresa
 * (CLAUDE.md §3.3): se cargan acá, no en un archivo.
 *
 * Viven en la configuración del asistente (`pools_de_ip`), así que el puente
 * es el motor, como los planes de venta. Ver GET/PUT /configuracion/rangos-de-ip
 * y POST /configuracion/ocupacion-ip/sincronizar en nucleo/canales/api.py.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * @typedef {{ zona_id: number, zona_nombre: string, prefijos: string[] }} Rango
 * @typedef {{ prefijo: string, clientes: number }} Sugerido
 */

/**
 * Lo guardado, lo sugerido y el uso de cada prefijo. No le pega al proveedor.
 * `null` si el motor no contesta: la pantalla lo dice en vez de mostrar vacío.
 * @param {any} locals @param {typeof fetch} fetch
 */
export async function leerRangos(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const r = await fetch(
      `${cfg.baseUrl}/configuracion/rangos-de-ip?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/**
 * Reemplaza entera la lista de rangos. `contarMalEscritas` es la opción de la
 * empresa de no ofrecer la IP que podría ser la de un cliente con la suya mal
 * escrita en el proveedor; `undefined` la deja como está.
 * @param {any} locals @param {typeof fetch} fetch @param {Rango[]} pools
 * @param {boolean} [contarMalEscritas]
 */
export async function guardarRangos(locals, fetch, pools, contarMalEscritas) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('El asistente no está configurado.');
  const r = await fetch(`${cfg.baseUrl}/configuracion/rangos-de-ip`, {
    method: 'PUT',
    headers: { ...headersMotor(), 'Content-Type': 'application/json' },
    body: JSON.stringify(
      contarMalEscritas === undefined
        ? { tenant: cfg.tenant, pools }
        : { tenant: cfg.tenant, pools, contar_ip_mal_escritas: contarMalEscritas }
    )
  });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos?.error || 'No se pudieron guardar los rangos.');
  return datos;
}

/**
 * Vuelve a leer del proveedor qué direcciones están tomadas. Tarda: recorre
 * todos los clientes (un minuto o más). Solo con un botón de quien gestiona.
 * @param {any} locals @param {typeof fetch} fetch
 */
export async function leerOcupacion(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('El asistente no está configurado.');
  const r = await fetch(`${cfg.baseUrl}/configuracion/ocupacion-ip/sincronizar`, {
    method: 'POST',
    headers: { ...headersMotor(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenant: cfg.tenant })
  });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos?.error || 'No se pudo leer el proveedor.');
  return datos;
}

/**
 * Del formulario a la lista de rangos. Pura: se prueba sin red.
 *
 * Cada servidor viaja con `rango_zona_<i>`, `rango_nombre_<i>` y
 * `rango_prefijos_<i>`: los prefijos separados por comas, espacios o renglones.
 * Se mandan tal como se escribieron: el motor los normaliza y rechaza lo que no
 * es un /24, con su porqué. Un número de zona con letras viaja como texto, para
 * que el 400 diga qué está mal en vez de volverse NaN.
 *
 * LO QUE NO SE VE NO SE BORRA. La pantalla muestra los servidores del contrato;
 * un rango guardado para otra zona (cargado antes por archivo, por ejemplo) se
 * conserva: `anteriores` son los guardados, y los de zonas que el formulario no
 * trae se agregan al final tal cual.
 *
 * @param {FormData} f
 * @param {Rango[]} [anteriores]
 * @returns {Array<{ zona_id: number | string, zona_nombre: string, prefijos: string[] }>}
 */
export function cuerpoDeRangos(f, anteriores = []) {
  /** @type {Array<{ zona_id: number | string, zona_nombre: string, prefijos: string[] }>} */
  const pools = [];
  const indices = [...f.keys()]
    .map((k) => /^rango_zona_(\d+)$/.exec(k)?.[1])
    .filter((i) => i !== undefined)
    .map(Number)
    .sort((a, b) => a - b);
  for (const i of indices) {
    const zona = String(f.get(`rango_zona_${i}`) ?? '').trim();
    if (!zona) continue;
    const prefijos = String(f.get(`rango_prefijos_${i}`) ?? '')
      .split(/[\s,;]+/)
      .map((p) => p.trim())
      .filter(Boolean);
    pools.push({
      zona_id: /^\d+$/.test(zona) ? Number(zona) : zona,
      zona_nombre: String(f.get(`rango_nombre_${i}`) ?? '').trim(),
      prefijos
    });
  }
  const enElFormulario = new Set(pools.map((p) => String(p.zona_id)));
  for (const p of anteriores ?? []) {
    if (!enElFormulario.has(String(p.zona_id))) pools.push({ ...p, prefijos: [...(p.prefijos ?? [])] });
  }
  return pools;
}
