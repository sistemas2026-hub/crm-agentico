/**
 * Abrir la Bandeja en la pestaña o banda que pide un enlace  --  12/11/2026
 *
 * `/conversaciones?pestana=<valor>` (auditoría del menú §4, ítem 13). Hasta
 * hoy el layout no leía la URL: las bandas de Hoy («N escaladas sin
 * asignar», «N para revisar») mandaban a `/conversaciones` a secas, que abre
 * en «Por atender», y la persona tenía que buscar de nuevo lo que Hoy ya le
 * había contado.
 *
 * VALORES QUE SE ACEPTAN (los emite Hoy, `lib/v2/hoy-operacion.js`):
 *
 *   pestañas    por-atender · en-atencion · lleva-ia · resueltas · todas
 *               (los mismos ids de `PREDICADOS` en pestanas.js y de QueueTabs)
 *   bandas      cliente_espera · sin_asignar · revisar
 *               (las tres que Hoy cuenta: `c.banda` 1, 2 y 3 del motor,
 *               nucleo/relevo/proyeccion.py)
 *
 * Una banda abre «Todos» filtrado por esa banda, y no una pestaña: la banda
 * la calcula el motor y la pestaña la pantalla, y no coinciden (una banda 1
 * —el cliente respondió— tiene dueño y vive en «En atención»). Filtrar por la
 * misma columna que contó Hoy es lo único que garantiza ver las mismas filas
 * que prometía el número.
 *
 * Un valor desconocido no hace nada: la Bandeja abre como siempre. Un enlace
 * viejo o mal escrito no puede vaciar la cola.
 */

export const PESTANAS_DEL_ENLACE = ['por-atender', 'en-atencion', 'lleva-ia', 'resueltas', 'todas'];

/** Banda del motor (número) y cómo se nombra en el filtro. */
export const BANDAS_DEL_ENLACE = {
  cliente_espera: { banda: 1, etiqueta: 'El cliente espera' },
  sin_asignar: { banda: 2, etiqueta: 'Escaladas sin asignar' },
  revisar: { banda: 3, etiqueta: 'Para revisar' }
};

/**
 * @param {URLSearchParams | null | undefined} params
 * @returns {{ pestana: string, banda: number | null, etiqueta: string } | null}
 *   null si el enlace no pide nada reconocible.
 */
export function intencionDelEnlace(params) {
  const valor = (params?.get('pestana') ?? '').trim().toLowerCase();
  if (!valor) return null;
  if (PESTANAS_DEL_ENLACE.includes(valor)) return { pestana: valor, banda: null, etiqueta: '' };
  // Propiedad PROPIA y no un acceso directo: `?pestana=__proto__` o
  // `constructor` encontraban algo en el prototipo y abrían «Todos» con una
  // banda indefinida (lo cazó enlace.test.js, 12/11/2026).
  if (!Object.prototype.hasOwnProperty.call(BANDAS_DEL_ENLACE, valor)) return null;
  const b = BANDAS_DEL_ENLACE[/** @type {keyof typeof BANDAS_DEL_ENLACE} */ (valor)];
  return { pestana: 'todas', banda: b.banda, etiqueta: b.etiqueta };
}

/**
 * Las filas de esa banda. Mira la banda de la FILA, que es la de la abierta
 * más urgente del chat (contrato §4.5, regla 2): la misma que cuenta Hoy.
 *
 * @param {any[]} lista
 * @param {number | null} banda
 */
export function deLaBanda(lista, banda) {
  return banda == null ? lista : lista.filter((c) => c?.banda === banda);
}
