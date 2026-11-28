/**
 * LOS AVISOS DEL SUPERVISOR NOC  --  21/11/2026.
 *
 * El resultado de una acción («Orden despachada», «Publicada», «Rechazada»)
 * se mostraba en una caja en la cabecera de la página, a varias pantallas de
 * distancia del botón que se tocó: guardar un nivel al fondo de Plantillas
 * parecía no hacer nada. Ahora sale abajo a la izquierda, a la vista, y se va
 * solo. Lo dibuja Avisos.svelte, montado una vez en el layout.
 *
 * Los errores NO se van solos: un error que desaparece antes de leerlo es
 * peor que no avisar.
 */

/** @typedef {{ id: number, texto: string, tono: 'ok' | 'error', enlace?: { texto: string, href: string } }} Aviso */

const DURA_MS = 6000;
let siguiente = 1;

/** @type {{ lista: Aviso[] }} */
export const avisos = $state({ lista: [] });

/** @param {number} id */
export function quitarAviso(id) {
  avisos.lista = avisos.lista.filter((a) => a.id !== id);
}

/**
 * @param {string} texto
 * @param {{ tono?: 'ok' | 'error', enlace?: { texto: string, href: string } }} [opciones]
 */
export function avisar(texto, opciones = {}) {
  if (!texto) return;
  const id = siguiente++;
  const tono = opciones.tono ?? 'ok';
  //  No más de tres a la vez: el más viejo se va.
  avisos.lista = [...avisos.lista.slice(-2), { id, texto, tono, enlace: opciones.enlace }];
  if (tono !== 'error' && typeof setTimeout === 'function') {
    setTimeout(() => quitarAviso(id), DURA_MS);
  }
}

/**
 * El resultado de un formulario de SvelteKit (`form`) convertido en aviso.
 * `hecho` y `error` son los nombres que usan las acciones del Supervisor.
 *
 * @param {{ hecho?: string, error?: string } | null | undefined} form
 */
export function avisarDelFormulario(form) {
  if (form?.error) avisar(form.error, { tono: 'error' });
  else if (form?.hecho) avisar(form.hecho);
}
