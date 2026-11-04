/**
 * Lo que el panel del cliente decide sobre cómo se lee un dato, fuera de
 * Svelte para poder probarlo (04/11/2026).
 *
 * Son dos decisiones chicas pero con consecuencia: si el aviso de la fecha de
 * corte se equivoca de día, quien atiende le promete al cliente algo que el
 * sistema del ISP no va a cumplir; y si un teléfono local sale con un `+`
 * delante, se lee como un número internacional que no existe.
 */
import { diasHasta, telefonoLegible } from '../formato.js';

/** Hasta cuántos días antes del corte vale la pena avisar. Más lejos que eso
    no cambia lo que se le contesta al cliente hoy, y un aviso permanente deja
    de leerse. */
export const DIAS_DE_AVISO_DE_CORTE = 3;

/**
 * La marca que va al lado de la fecha de corte, o null si no hay nada que
 * avisar. Sale de `diasHasta`: sin fecha reconocible no hay «faltan N días»,
 * y antes que adivinar se muestra sólo el texto del ISP.
 *
 * @param {unknown} fecha  la fecha tal como la manda el ISP
 * @param {Date} [hoy]
 * @returns {string|null}
 */
export function avisoDeCorte(fecha, hoy = new Date()) {
  const dias = diasHasta(fecha, hoy);
  if (dias === null) return null;
  if (dias < 0) return `venció hace ${-dias} ${-dias === 1 ? 'día' : 'días'}`;
  if (dias === 0) return 'hoy';
  if (dias === 1) return 'mañana';
  if (dias <= DIAS_DE_AVISO_DE_CORTE) return `en ${dias} días`;
  return null;
}

/**
 * El teléfono del canal, legible. `telefonoLegible` reconoce el plan
 * colombiano con su 57 y a cualquier otro número le antepone `+`; con diez
 * cifras locales (`3001234567`) eso daría `+3001234567`, que no es un número
 * de ningún país. Por eso las diez cifras sueltas se agrupan como el panel lo
 * hacía hasta hoy, y el resto pasa por `telefonoLegible`.
 *
 * @param {unknown} valor
 * @returns {string}
 */
export function telefonoDelCanal(valor) {
  const texto = String(valor ?? '').trim();
  if (/^\d{10}$/.test(texto)) {
    return `${texto.slice(0, 3)} ${texto.slice(3, 6)} ${texto.slice(6)}`;
  }
  return telefonoLegible(texto);
}
