/**
 * LA FICHA DE LA PROPUESTA, EN DOS LISTAS  --  01/11/2026
 *
 * El diseño aprobado separa «Qué va a pasar» de «Qué NO va a pasar». La
 * segunda lista es la que evita el malentendido más caro de la pantalla:
 * creer que aceptar ya mandó una cuadrilla o ya cerró el caso.
 *
 * Las ramas son las MISMAS tres que decide `siAcepto` (ejecuta / pasa a
 * Despacho / observación) y dicen lo mismo que su `efecto`, partido en
 * renglones. No hay una regla nueva acá: si `siAcepto` cambia de rama, la
 * lista cambia con ella.
 */

import { AUSENTE } from './supervisor-noc-detalle.js';

/**
 * @param {{ ejecuta?: boolean, pasaADespacho?: boolean } | null | undefined} aceptar
 *   lo que devuelve `siAcepto`
 */
export function efectosDeAceptar(aceptar) {
  if (!aceptar) return { si: [], no: [] };
  if (aceptar.ejecuta) {
    return {
      si: [
        'Se valida de nuevo que las condiciones sigan dándose.',
        'Si se cumplen, se cierra el caso en Dexter.',
        'Si alguna cambió, no se ejecuta y se te dice cuál.'
      ],
      no: ['No toca WispHub.']
    };
  }
  if (aceptar.pasaADespacho) {
    return {
      si: [
        'El caso pasa a la cola de Despacho a campo.',
        'Ahí una persona elige la plantilla y crea la orden.'
      ],
      no: ['No crea la orden ni manda a nadie todavía.', 'No cierra el caso.', 'No toca WispHub.']
    };
  }
  return {
    si: ['Queda registrado que estás de acuerdo.'],
    no: ['No cierra el caso.', 'No toca WispHub.', 'No ejecuta ninguna acción.']
  };
}

/** @param {any} v */
const conDato = (v) => typeof v === 'string' && v.trim() !== '' && v !== AUSENTE;

/**
 * Si una fila de la comparación Dexter / WispHub muestra una diferencia de
 * verdad. Un lado sin dato es un hueco, no una discrepancia: pintarlo de rojo
 * acusaría algo que nadie midió.
 *
 * @param {{ dexter?: string, wisphub?: string }} fila
 */
export function celdaDistinta(fila) {
  if (!conDato(fila?.dexter) || !conDato(fila?.wisphub)) return false;
  return String(fila.dexter).trim().toLowerCase() !== String(fila.wisphub).trim().toLowerCase();
}
