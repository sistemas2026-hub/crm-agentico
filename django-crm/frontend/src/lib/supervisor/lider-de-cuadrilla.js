/**
 * QUIÉNES SE OFRECEN COMO LÍDER DE UNA CUADRILLA
 * ==============================================
 *
 * El líder es un `Profile`, no una persona de campo, y es correcto: lidera
 * quien tiene el celular y usa la aplicación, y es a quien le llega la orden
 * (`campo.cuadrillas.destinatarios`: «el LIDER DEL DIA la recibe siempre, este
 * o no anotado entre los integrantes»). Por eso el valor de cada opción es el
 * `profile` y no el id de la persona.
 *
 * EL DEFECTO, reportado por el usuario el 17/10/2026
 * --------------------------------------------------
 * «No deja seleccionar líder y después sale sin líder.» El selector ofrecía
 * solo las personas de campo con la cuenta enlazada, y en Rapilink no había
 * ninguna: la lista quedaba en «— sin líder —». El líder que la cuadrilla ya
 * tenía no estaba entre las opciones, así que el selector no podía mostrarlo,
 * y guardar la ficha —para marcarle las zonas habituales— le borró el suyo a
 * una cuadrilla.
 *
 * Por eso son TRES fuentes:
 *   1. el líder que ya tiene, SIEMPRE, aunque no esté en las otras dos;
 *   2. las personas de campo con cuenta;
 *   3. las cuentas del equipo que todavía no son persona de campo: el backend
 *      acepta cualquier cuenta activa de la empresa (`_perfil_de`).
 */

/** @typedef {{ profile: string, nombre: string }} Candidato */

/**
 * @param {any[] | null | undefined} personas  las personas de campo, como las
 *   devuelve `/campo/personas-de-campo/`
 * @param {any[] | null | undefined} cuentasSinPersona  las cuentas activas que
 *   todavía no son persona de campo, del mismo endpoint
 * @param {{ id?: string, nombre?: string } | null | undefined} actual  el
 *   líder que ya tiene (`{ id, nombre }`, con el id de la cuenta)
 * @returns {{ actual: Candidato | null, deCampo: Candidato[], cuentas: Candidato[] }}
 *   `actual` viene solo cuando NO está en las otras dos listas: si está, ya
 *   se ofrece ahí y repetirlo dibujaría a la misma persona dos veces.
 */
export function opcionesDeLider(personas, cuentasSinPersona, actual) {
  const deCampo = (personas ?? [])
    .filter((p) => p?.tiene_cuenta && p?.profile)
    .map((p) => ({ profile: String(p.profile), nombre: p.nombre || 'Sin nombre' }));
  const cuentas = (cuentasSinPersona ?? [])
    .filter((c) => c?.profile)
    .map((c) => ({ profile: String(c.profile), nombre: c.nombre || 'Sin nombre' }));

  const ofrecidos = new Set([...deCampo, ...cuentas].map((c) => c.profile));
  const id = actual?.id ? String(actual.id) : '';
  return {
    actual: id && !ofrecidos.has(id)
      ? { profile: id, nombre: actual?.nombre || 'Líder actual' }
      : null,
    deCampo,
    cuentas
  };
}
