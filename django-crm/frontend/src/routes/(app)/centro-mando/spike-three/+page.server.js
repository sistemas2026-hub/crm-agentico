/**
 * EL SPIKE COME DEL MISMO PLATO.
 *
 * La carga es literalmente la de `/centro-mando`, reexportada y no copiada:
 * si el prototipo leyera los datos por su cuenta, la comparación mediría dos
 * lecturas distintas y no dos motores. Y una copia se desincronizaría el día
 * que la original cambie, que es cuando la comparación dejaría de valer sin
 * que nadie se entere.
 */
export { load } from '../+page.server.js';
