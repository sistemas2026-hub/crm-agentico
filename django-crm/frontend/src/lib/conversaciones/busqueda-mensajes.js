/**
 * BUSCAR EN LOS MENSAJES, DEL LADO DE LA PANTALLA  --  11/11/2026
 *
 * El buscador de la cola decía «Buscar conversación, cliente o mensaje…» y
 * del mensaje solo miraba el último de cada conversación ya cargada. Ahora,
 * con 3 letras o más, además del filtro local (que sigue igual e instantáneo)
 * se le pregunta al motor por TODOS los mensajes, y lo que encuentra se lista
 * debajo de la cola, en «En mensajes».
 *
 * Esto es la lógica sin DOM, para poder probarla:
 *   - cuándo se busca y cuándo no;
 *   - el que espera entre teclas y cancela el pedido anterior, para no
 *     mandar un pedido por letra ni pintar la respuesta de «pos» encima de
 *     la de «poste»;
 *   - cómo se parte un fragmento para resaltar lo buscado SIN `{@html}`:
 *     el fragmento es texto de un cliente, y meterlo como HTML sería darle
 *     a cualquiera que escriba por WhatsApp un lugar donde inyectar marcado.
 */

export const BUSQUEDA_MINIMO = 3;
export const BUSQUEDA_MAXIMO = 100;
/** Cuánto se espera después de la última tecla antes de preguntar. */
export const ESPERA_ENTRE_TECLAS_MS = 300;

/** Los espacios no cuentan: «  ab  » son 2 letras, no 6. */
export const normalizar = (/** @type {unknown} */ q) =>
  String(q ?? '').split(/\s+/).filter(Boolean).join(' ');

/** Si esto se le pregunta al motor. Por debajo de 3 letras coincide con
 *  media base; por encima de 100 no es una búsqueda, es un mensaje pegado. */
export function debeBuscarEnMensajes(/** @type {unknown} */ q) {
  const n = normalizar(q).length;
  return n >= BUSQUEDA_MINIMO && n <= BUSQUEDA_MAXIMO;
}

const escaparRegex = (/** @type {string} */ s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * El texto partido en trozos, marcando cuáles son la coincidencia. Sin
 * mayúsculas que importen, igual que la búsqueda del motor (ILIKE). La
 * pantalla dibuja cada trozo como texto y envuelve en `<mark>` los que
 * coinciden: nunca se arma HTML con lo que escribió el cliente.
 *
 * @param {string} texto
 * @param {string} q
 * @returns {{ texto: string, coincide: boolean }[]}
 */
export function partirPorCoincidencia(texto, q) {
  const t = String(texto ?? '');
  const buscado = normalizar(q);
  if (!t) return [];
  if (!buscado) return [{ texto: t, coincide: false }];
  // Un espacio de la búsqueda vale por cualquier blanco del texto: el motor
  // normaliza los blancos del fragmento, pero no los del mensaje original.
  const patron = new RegExp(buscado.split(' ').map(escaparRegex).join('\\s+'), 'giu');
  /** @type {{ texto: string, coincide: boolean }[]} */
  const partes = [];
  let desde = 0;
  for (const m of t.matchAll(patron)) {
    const i = m.index ?? 0;
    if (!m[0]) break;
    if (i > desde) partes.push({ texto: t.slice(desde, i), coincide: false });
    partes.push({ texto: m[0], coincide: true });
    desde = i + m[0].length;
  }
  if (desde < t.length) partes.push({ texto: t.slice(desde), coincide: false });
  return partes;
}

/** Las vistas de canales de la cola, las mismas que acepta el motor. */
export const VISTAS = Object.freeze(['operativo', 'pruebas', 'todos']);

/**
 * Los resultados que corresponden a la vista de canales que eligió quien
 * mira -- la MISMA regla que la cola (`base` en +layout.svelte): sin
 * `canal_operativo`, no se esconde nada.
 *
 * Desde el 11/11/2026 (auditoría H2) la vista viaja al motor y la BASE filtra
 * antes de cortar en 30: filtrar solo acá, después del tope, dejaba «Ningún
 * mensaje contiene X» cuando los 30 más recientes eran de prueba. Esto queda
 * como segunda mano para un motor que todavía no sabe de vistas (la ventana
 * del despliegue): con uno que sí, no esconde nada.
 *
 * @param {any[]} resultados
 * @param {string} vista 'operativo' | 'pruebas' | 'todos'
 */
export function resultadosDeLaVista(resultados, vista) {
  const lista = Array.isArray(resultados) ? resultados : [];
  if (vista === 'todos') return lista;
  const operativo = vista === 'operativo';
  return lista.filter((r) => (r?.canal_operativo === undefined ? true : r.canal_operativo === operativo));
}

/**
 * @typedef {{
 *   estado: 'inactivo' | 'buscando' | 'listo' | 'error',
 *   q: string,
 *   resultados: any[],
 *   tope: number | null,
 *   error: string
 * }} EstadoBusqueda
 */

/** @type {EstadoBusqueda} */
export const SIN_BUSQUEDA = Object.freeze({ estado: 'inactivo', q: '', resultados: [], tope: null, error: '' });

/**
 * El que espera entre teclas y cancela lo anterior.
 *
 * `buscar(q, signal, vista)` hace el pedido (en la pantalla, un fetch a la
 * ruta del servidor) y devuelve `{ resultados, tope }` o lanza. La vista de
 * canales es parte de lo pedido: si cambia con una búsqueda escrita, se
 * vuelve a preguntar -- los 30 de una vista no son los de otra. `alCambiar` recibe el
 * estado cada vez que cambia. Solo la ÚLTIMA búsqueda pedida puede escribir
 * el estado: una respuesta vieja que llega tarde se descarta aunque el
 * navegador no haya llegado a cancelarla.
 *
 * @param {{
 *   buscar: (q: string, signal: AbortSignal, vista: string) => Promise<{ resultados: any[], tope?: number | null }>,
 *   alCambiar: (estado: EstadoBusqueda) => void,
 *   espera?: number
 * }} opciones
 */
export function crearBuscadorMensajes({ buscar, alCambiar, espera = ESPERA_ENTRE_TECLAS_MS }) {
  /** @type {ReturnType<typeof setTimeout> | null} */
  let reloj = null;
  /** @type {AbortController | null} */
  let enCurso = null;
  let turno = 0;
  let ultima = '';
  let ultimaVista = '';

  const cortar = () => {
    if (reloj) clearTimeout(reloj);
    reloj = null;
    enCurso?.abort();
    enCurso = null;
  };

  return {
    /** Lo escrito, o la vista de canales, cambió. */
    pedir(/** @type {unknown} */ crudo, vista = 'todos') {
      const q = normalizar(crudo);
      if (q === ultima && vista === ultimaVista && reloj === null && enCurso === null && q) return;
      ultima = q;
      ultimaVista = vista;
      cortar();
      const miTurno = ++turno;
      if (!debeBuscarEnMensajes(q)) {
        alCambiar({ ...SIN_BUSQUEDA });
        return;
      }
      // «Buscando» desde la primera tecla: la sección aparece en el acto y
      // no salta de vacía a llena 300 ms después.
      alCambiar({ estado: 'buscando', q, resultados: [], tope: null, error: '' });
      reloj = setTimeout(async () => {
        reloj = null;
        const control = new AbortController();
        enCurso = control;
        try {
          const r = await buscar(q, control.signal, vista);
          if (miTurno !== turno) return;
          alCambiar({
            estado: 'listo',
            q,
            resultados: Array.isArray(r?.resultados) ? r.resultados : [],
            tope: r?.tope ?? null,
            error: ''
          });
        } catch (/** @type {any} */ e) {
          if (miTurno !== turno || e?.name === 'AbortError') return;
          alCambiar({
            estado: 'error',
            q,
            resultados: [],
            tope: null,
            error: e?.message || 'No se pudo buscar en los mensajes.'
          });
        } finally {
          if (enCurso === control) enCurso = null;
        }
      }, espera);
    },
    /** Al desmontar: nada queda corriendo ni escribe después. */
    cancelar() {
      turno++;
      cortar();
    }
  };
}
